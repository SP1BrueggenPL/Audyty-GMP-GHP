import re
from datetime import timedelta

from accounts.models import Department, eligible_area_users
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, Count, ProtectedError, Q, When
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ai import suggest_inspection_summary, suggest_nc_description
from .email_acs import send_report_email
from .pdf import render_inspection_pdf
from .forms import (
    WED_LOCATION_CHOICES,
    AuditorReviewForm,
    InspectionAdminEditForm,
    InspectionSummaryForm,
    ResponsibleActionForm,
    StandaloneNonConformityForm,
    derive_department,
)
from .models import (
    AreaCode,
    ChecklistItem,
    ChecklistTemplate,
    Inspection,
    InspectionItemResult,
    InspectionSectionResult,
    InspectionStatus,
    ItemResult,
    NCStatus,
    NonConformity,
    NC_PLACEHOLDER_DESCRIPTION,
    NCPhotoKind,
    NonConformityPhoto,
    PhotoArchive,
    Shift,
    nc_deducts_points,
)

User = get_user_model()


def _scoped_nonconformities(user):
    qs = NonConformity.objects.select_related("inspector", "responsible_person")
    scope = user.department_scope
    if scope is None:
        return qs
    query = Q(department__in=scope) | Q(responsible_person=user)
    if user.is_shift_user:
        # Zespół zmiany: niezgodności swojej zmiany (w obrębie działów użytkownika, o ile je ma).
        shift_query = Q(shift=user.shift)
        if scope:
            shift_query &= Q(department__in=scope)
        query |= shift_query
    return qs.filter(query)


def _user_on_nc_shift(user, nc):
    """Czy użytkownik pracuje na tej samej zmianie, do której przypisana jest niezgodność."""
    return bool(user.shift) and nc.shift == user.shift


def _scoped_inspections(user):
    # Wersje robocze (DRAFT) nie pojawiają się tu ani w rejestrze/dashboardzie -
    # widoczne są tylko dla ich autora, na ekranie "Moje niedokończone inspekcje".
    qs = Inspection.objects.exclude(status=InspectionStatus.DRAFT).select_related("template", "inspector")
    if not user.is_admin_role:
        qs = qs.filter(is_hidden=False)
    scope = user.department_scope
    if scope is None:
        return qs
    if user.is_shift_user:
        # Użytkownik zmianowy widzi wszystkie inspekcje swojej zmiany (w obrębie swoich działów,
        # o ile je ma), niezależnie od tego, kto z tej zmiany był na inspekcji przypisany.
        return [
            i for i in qs.filter(shift=user.shift)
            if not scope or derive_department(i.template.area_code, i.area_detail) in scope
        ]
    return [i for i in qs if derive_department(i.template.area_code, i.area_detail) in scope]


def _require_admin(request):
    if request.user.is_admin_role:
        return True
    messages.error(request, "Tylko administrator może edytować lub usuwać ten wpis.")
    return False


def _require_inspection_editor(request):
    if request.user.has_full_access:
        return True
    messages.error(request, "Edycja inspekcji jest dostępna dla Audytora, QualityAdmin i Helpdesku.")
    return False


def _create_item_nc(inspection, item, section, department, area_rep_text, location, description, responsible_id):
    return NonConformity.objects.create(
        inspection=inspection,
        checklist_item=item,
        inspection_date=inspection.inspected_at.date(),
        department=department,
        inspector=inspection.inspector,
        shift=inspection.shift,
        area_representative=area_rep_text,
        gmp_category=section.name,
        checklist_point_label=item.number,
        point_description=item.description[:400],
        location_detail=location,
        description=description,
        responsible_person_id=responsible_id,
    )


def _resolve_extra_point(all_items, item_id):
    """Dla "dodatkowej" niezgodności zwraca (item_id, numer punktu, opis punktu, kategoria);
    gdy punktu nie wskazano lub nie istnieje - item_id None i pusta etykieta."""
    if item_id:
        chosen = next((it for it in all_items if str(it.id) == str(item_id)), None)
        if chosen:
            return chosen.id, chosen.number, chosen.description[:400], chosen.subsection.section.name
    return None, "", "", ""


def _create_extra_nc(inspection, department, area_rep_text, all_items, item_id, location, description, responsible_id):
    item_id, point_label, point_desc, category = _resolve_extra_point(all_items, item_id)
    return NonConformity.objects.create(
        inspection=inspection, checklist_item_id=item_id, is_extra=True,
        inspection_date=inspection.inspected_at.date(),
        department=department, inspector=inspection.inspector, shift=inspection.shift,
        area_representative=area_rep_text,
        gmp_category=category, checklist_point_label=point_label or "Brak punktu odniesienia",
        point_description=point_desc, location_detail=location, description=description,
        responsible_person_id=responsible_id,
    )


def _missing_required_labels(description, location, responsible):
    """Wymagane pola niezgodności: lokalizacja, osoba odpowiedzialna, opis (zdjęcie jest opcjonalne).
    Opis zastępczy (niezgodność utworzona od samego zdjęcia) liczy się jako brak opisu."""
    missing = []
    if not location:
        missing.append("lokalizacja")
    if not responsible:
        missing.append("osoba odpowiedzialna")
    if not description or description == NC_PLACEHOLDER_DESCRIPTION:
        missing.append("opis")
    return missing


def _missing_required_nc_fields(post, sections):
    """Lista komunikatów o brakujących wymaganych polach niezgodności w wysyłanym formularzu.
    Sprawdzane tylko przy zapisie końcowym (autozapis wersji roboczej nie wymaga kompletności).
    Dla punktu z wynikiem NC pierwsza niezgodność jest zawsze wymagana; dodatkowe bloki
    (przycisk "+") i niezgodności "dodatkowe" - tylko jeśli ktokolwiek zaczął je wypełniać."""
    problems = []
    for section in sections:
        for subsection in section.subsections.all():
            for item in subsection.items.all():
                if post.get(f"item_{item.id}_result", ItemResult.OK) != ItemResult.NC:
                    continue
                total = int(post.get(f"item_{item.id}_nc-TOTAL_FORMS", 0) or 0)
                for i in range(max(total, 1)):
                    prefix = f"item_{item.id}_nc-{i}-"
                    description = post.get(prefix + "description", "").strip()
                    location = post.get(prefix + "location", "").strip()
                    responsible = post.get(prefix + "responsible", "")
                    started = description or location or responsible or post.get(prefix + "id")
                    if i > 0 and not started:
                        continue
                    missing = _missing_required_labels(description, location, responsible)
                    if missing:
                        label = f"Punkt {item.number}" + (f" (niezgodność {i + 1})" if total > 1 else "")
                        problems.append(f"{label}: brak {', '.join(missing)}")
    for i in range(int(post.get("extra-TOTAL_FORMS", 0) or 0)):
        prefix = f"extra-{i}-"
        description = post.get(prefix + "description", "").strip()
        location = post.get(prefix + "location", "").strip()
        responsible = post.get(prefix + "responsible", "")
        if not (description or location or responsible or post.get(prefix + "id")):
            continue
        missing = _missing_required_labels(description, location, responsible)
        if missing:
            problems.append(f"Dodatkowa niezgodność {i + 1}: brak {', '.join(missing)}")
    return problems


def _flash_missing_required(request, problems, saved_as_draft):
    head = (
        "Inspekcja NIE została zakończona (zapisano wersję roboczą) - uzupełnij wymagane pola niezgodności"
        if saved_as_draft else
        "Nie zapisano zmian - uzupełnij wymagane pola niezgodności"
    )
    messages.error(request, f"{head} (lokalizacja, osoba odpowiedzialna, opis; zdjęcie jest opcjonalne):")
    for line in problems[:15]:
        messages.error(request, line)
    if len(problems) > 15:
        messages.error(request, f"…i {len(problems) - 15} kolejnych.")


def _recalculate_section_points(inspection):
    """Punkty sekcji: każda niezgodność na punkcie checklisty odlicza wagę tego punktu,
    chyba że jest przypisana do osoby z rolą "Użytkownik obszaru" (patrz nc_deducts_points).
    Zapisuje też odjęcie za "dodatkowe" niezgodności, żeby wynik był trwały."""
    for section in inspection.template.sections.all():
        section_ncs = NonConformity.objects.filter(
            inspection=inspection, is_extra=False, checklist_item__subsection__section=section,
        ).select_related("checklist_item", "responsible_person")
        weight_sum = sum(
            nc.checklist_item.penalty_weight for nc in section_ncs
            if nc_deducts_points(nc.responsible_person)
        )
        InspectionSectionResult.objects.update_or_create(
            inspection=inspection, section=section,
            defaults={"points_awarded": max(0, section.max_points - weight_sum)},
        )
    inspection.extra_penalty = inspection.compute_extra_nc_penalty()
    inspection.save(update_fields=["extra_penalty"])


def _ordered_nonconformities(qs):
    """Sortuje niezgodności wg pozycji w checkliście (sekcja/podsekcja/punkt);
    te bez punktu ("Brak punktu odniesienia") trafiają na sam koniec."""
    return qs.annotate(
        _no_point=Case(When(checklist_item__isnull=True, then=1), default=0),
    ).order_by(
        "_no_point",
        "checklist_item__subsection__section__order",
        "checklist_item__subsection__order",
        "checklist_item__order",
    )


def _my_open_tasks(user):
    """Sekcja "Zadania" na panelu: niezgodności przypisane do użytkownika (jak dotychczas),
    dla użytkownika zmianowego także niezgodności jego zmiany, a dla audytora dodatkowo jego
    niezgodności ze statusem "W toku" - użytkownik zmiany zaczął nad nimi pracę."""
    query = Q(responsible_person=user)
    if user.is_shift_user:
        query |= Q(shift=user.shift)
    if user.can_run_inspections:
        query |= Q(inspector=user, status=NCStatus.W_TOKU)
    open_ncs = NonConformity.objects.filter(query).exclude(status=NCStatus.WDROZONE)
    return list(open_ncs.select_related("responsible_person").order_by("-updated_at")[:10])


@login_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    base_qs = _scoped_nonconformities(request.user)

    inspections_this_month = Inspection.objects.filter(inspected_at__date__gte=month_start).count()
    open_ncs = base_qs.exclude(status=NCStatus.WDROZONE)
    overdue_ncs = [nc for nc in open_ncs if nc.is_due_for_reminder]

    by_department = (
        base_qs.filter(inspection_date__gte=today - timedelta(days=90))
        .values("department").annotate(total=Count("id")).order_by("-total")
    )

    context = {
        "inspections_this_month": inspections_this_month,
        "open_ncs_count": open_ncs.count(),
        "overdue_ncs_count": len(overdue_ncs),
        "by_department": by_department,
        "recent_inspections": sorted(
            _scoped_inspections(request.user), key=lambda i: i.inspected_at, reverse=True,
        )[:8],
        "my_open_tasks": _my_open_tasks(request.user),
        "templates": ChecklistTemplate.objects.filter(is_active=True),
        "my_drafts_count": (
            Inspection.objects.filter(inspector=request.user, status=InspectionStatus.DRAFT).count()
            if request.user.can_run_inspections else 0
        ),
    }
    return render(request, "audits/dashboard.html", context)


@login_required
def inspection_type_select(request):
    if not request.user.can_run_inspections:
        messages.error(request, "Twoja rola nie pozwala na przeprowadzanie inspekcji.")
        return redirect("dashboard")
    templates = ChecklistTemplate.objects.filter(is_active=True)
    return render(request, "audits/inspection_type_select.html", {"templates": templates})


@login_required
def inspection_drafts(request):
    if not request.user.can_run_inspections:
        messages.error(request, "Twoja rola nie pozwala na przeprowadzanie inspekcji.")
        return redirect("dashboard")
    drafts = Inspection.objects.filter(
        inspector=request.user, status=InspectionStatus.DRAFT,
    ).select_related("template").order_by("-updated_at")
    return render(request, "audits/inspection_drafts.html", {"drafts": drafts})


@login_required
def users_by_shift(request):
    """AJAX: zwraca kandydatów na przedstawiciela obszaru/odpowiedzialnego za
    niezgodność - patrz accounts.models.eligible_area_users. Obejmuje osoby
    pasujące do działu (rola "Użytkownik obszaru" z dopasowanym Działem albo
    rola działowa typu Pakownia/Produkcja, Techniczny, Logistyka) ORAZ
    KAŻDĄ osobę przypisaną do wskazanej zmiany, niezależnie od jej roli -
    na inspekcji może pomagać dowolna osoba z tej samej zmiany. Dla działów
    bez zmian (Techniczny/WED, zmiana zawsze "n/d") filtr zmiany po prostu
    nic nie dokłada (żadna osoba nie ma shift="n/d")."""
    area_code = request.GET.get("area_code", "")
    area_detail = request.GET.get("area_detail", "")
    shift = request.GET.get("shift", "")

    if not area_code and not shift:
        return JsonResponse({"users": []})

    department = derive_department(area_code, area_detail) if area_code else None
    effective_shift = shift if shift and shift != Shift.ND else None
    qs = eligible_area_users(department, effective_shift).filter(is_active=True).order_by("last_name", "first_name")
    return JsonResponse({"users": [{"id": u.pk, "name": str(u)} for u in qs]})


@login_required
def suggest_nonconformity(request):
    """AJAX: podpowiedź opisu niezgodności (Azure OpenAI GPT-4o) na bazie zdjęcia,
    treści aktualnego punktu checklisty (sekcja/podsekcja/opis) i wcześniej
    zapisanych niezgodności dla tego punktu. Dodatkowo AI dostaje pełną listę
    punktów tego szablonu, żeby wykryć niedopasowanie zdjęcia do punktu i
    zasugerować właściwy (pole mismatch_point/mismatch_reason w odpowiedzi)."""
    item_id = request.POST.get("item_id")
    photo = request.FILES.get("photo")

    item = (
        ChecklistItem.objects.select_related("subsection__section__template").filter(pk=item_id).first()
        if item_id else None
    )
    past_examples = list(
        NonConformity.objects.filter(checklist_item_id=item_id)
        .order_by("-id").values_list("description", flat=True)[:5]
    ) if item_id else []
    all_points = []
    if item is not None:
        template = item.subsection.section.template
        template_items = list(
            ChecklistItem.objects.filter(subsection__section__template=template)
            .select_related("subsection__section").order_by(
                "subsection__section__order", "subsection__order", "order",
            )
        )
        all_points = [
            (f"P{it.pk}", f"[{it.subsection.section.label}] {it.number} {it.description}")
            for it in template_items
        ]
        items_by_id = {it.pk: it for it in template_items}

    result = suggest_nc_description(photo=photo, past_examples=past_examples, item=item, all_points=all_points)

    # AI wskazuje punkt kodem "P<id>" - zamieniamy go na konkretny punkt (albo odrzucamy, jeśli
    # kod jest nieczytelny lub wskazuje ten sam punkt, przy którym audytor już jest).
    result["mismatch_item_id"] = None
    if result.get("mismatch_point") and item is not None:
        m = re.match(r"\s*P(\d+)(?!\d)", result["mismatch_point"], re.IGNORECASE)
        target = items_by_id.get(int(m.group(1))) if m else None
        if target is not None and target.pk == item.pk:
            result["mismatch_point"] = result["mismatch_reason"] = None
        elif target is not None:
            result["mismatch_item_id"] = target.pk
            result["mismatch_point"] = f"{target.subsection.section.label}. {target.number} - {target.description[:90]}"
        else:
            result["mismatch_point"] = None  # niejednoznaczna odpowiedź - nie proponujemy przeniesienia
    return JsonResponse(result)


def _generate_inspection_summary(inspection):
    """Woła AI z zanonimizowanymi danymi (WYŁĄCZNIE punkt checklisty i opis
    niezgodności - bez nazwisk, działów ani lokalizacji). Zwraca dict
    {available, summary_good, summary_to_fix, error}."""
    ncs = inspection.nonconformities.all()
    nc_points = [(nc.checklist_point_label, nc.description) for nc in ncs]
    total_count = len(ChecklistItem.objects.filter(subsection__section__template=inspection.template))
    ok_count = max(0, total_count - len({nc.checklist_item_id for nc in ncs if nc.checklist_item_id}))
    return suggest_inspection_summary(nc_points, ok_count, total_count)


@login_required
def suggest_inspection_summary_view(request):
    """AJAX: propozycja podsumowania inspekcji (używane na ekranie raportu -
    wypełnia pola formularza, nic nie zapisuje samo z siebie)."""
    inspection_id = request.POST.get("inspection_id")
    inspection = get_object_or_404(Inspection, pk=inspection_id)
    result = _generate_inspection_summary(inspection)
    return JsonResponse(result)


@require_POST
@login_required
def inspection_generate_summary(request, pk):
    """Generuje i od razu zapisuje podsumowanie AI z poziomu widoku inspekcji
    (bez przechodzenia przez ekran raportu)."""
    inspection = get_object_or_404(Inspection, pk=pk)
    if not _require_inspection_editor(request):
        return redirect("inspection_detail", pk=pk)

    result = _generate_inspection_summary(inspection)
    if result.get("summary_good") or result.get("summary_to_fix"):
        if result.get("summary_good"):
            inspection.summary_good = result["summary_good"]
        if result.get("summary_to_fix"):
            inspection.summary_to_fix = result["summary_to_fix"]
        inspection.save(update_fields=["summary_good", "summary_to_fix", "updated_at"])
        messages.success(request, "Podsumowanie AI wygenerowane i zapisane.")
    elif not result.get("available"):
        messages.error(request, "Funkcja AI nie jest skonfigurowana (brak danych dostępowych Azure OpenAI).")
    else:
        messages.error(request, result.get("error") or "Nie udało się wygenerować podsumowania.")
    return redirect("inspection_detail", pk=inspection.pk)


@login_required
def inspection_new(request, template_id):
    """Rozpoczyna nową inspekcję: od razu tworzy wersję roboczą (status DRAFT)
    w bazie i przekierowuje do jej wypełniania (inspection_edit) - dzięki temu
    praca jest zapisywana na bieżąco (autozapis) od pierwszej sekundy, a nie
    dopiero po ukończeniu całego formularza. Jeśli audytor ma już świeżo
    rozpoczętą (w ciągu ostatnich 12h) wersję roboczą tego samego szablonu,
    wznawia ją zamiast tworzyć kolejną pustą."""
    if not request.user.can_run_inspections:
        messages.error(request, "Twoja rola nie pozwala na przeprowadzanie inspekcji.")
        return redirect("dashboard")
    template = get_object_or_404(ChecklistTemplate, pk=template_id, is_active=True)

    recent_cutoff = timezone.now() - timedelta(hours=12)
    draft = Inspection.objects.filter(
        template=template, inspector=request.user, status=InspectionStatus.DRAFT,
        updated_at__gte=recent_cutoff,
    ).order_by("-updated_at").first()
    if not draft:
        draft = Inspection.objects.create(
            template=template, inspector=request.user, status=InspectionStatus.DRAFT,
            inspected_at=timezone.now(),
        )
    return redirect("inspection_edit", pk=draft.pk)


@login_required
def inspection_list(request):
    if not (request.user.can_run_inspections or request.user.is_shift_user):
        messages.error(request, "Rejestr inspekcji jest dostępny dla Audytora, QualityAdmin, Helpdesku i użytkowników zmianowych.")
        return redirect("dashboard")

    inspections = _scoped_inspections(request.user)

    status = request.GET.get("status", "")
    department = request.GET.get("department", "")
    if status:
        inspections = [i for i in inspections if i.status == status]
    if department:
        inspections = [
            i for i in inspections if derive_department(i.template.area_code, i.area_detail) == department
        ]
    inspections = sorted(inspections, key=lambda i: i.inspected_at, reverse=True)

    scope = request.user.department_scope
    department_choices = [(c, l) for c, l in Department.choices if scope is None or c in scope]

    return render(request, "audits/inspection_list.html", {
        "inspections": inspections,
        "status_choices": InspectionStatus.choices,
        "department_choices": department_choices,
        "current_status": status,
        "current_department": department,
    })


@login_required
def inspection_detail(request, pk):
    inspection = get_object_or_404(
        Inspection.objects.select_related("template", "inspector").prefetch_related("area_representatives"), pk=pk,
    )
    section_results = inspection.section_results.select_related("section").order_by("section__order")
    nonconformities = _ordered_nonconformities(
        inspection.nonconformities.select_related("responsible_person")
    )
    return render(request, "audits/inspection_detail.html", {
        "inspection": inspection,
        "section_results": section_results,
        "nonconformities": nonconformities,
    })


@login_required
def inspection_edit(request, pk):
    if not _require_inspection_editor(request):
        return redirect("inspection_detail", pk=pk)

    inspection = get_object_or_404(Inspection, pk=pk)
    template = inspection.template
    sections = list(template.sections.prefetch_related("subsections__items").all())
    all_items = [it for s in sections for sub in s.subsections.all() for it in sub.items.all()]
    was_draft = inspection.status == InspectionStatus.DRAFT

    if request.method == "POST":
        autosave = request.POST.get("autosave") == "1"
        form = InspectionAdminEditForm(request.POST, instance=inspection)
        missing_required = [] if autosave else _missing_required_nc_fields(request.POST, sections)
        if missing_required and not was_draft:
            # Edycja zapisanej inspekcji z brakami: nic nie zapisujemy, pokazujemy błędy.
            _flash_missing_required(request, missing_required, saved_as_draft=False)
            form = InspectionAdminEditForm(instance=inspection, initial={
                "inspected_at": timezone.localtime(inspection.inspected_at).strftime("%Y-%m-%dT%H:%M"),
            })
        elif form.is_valid():
            item_nc_ids = {}
            extra_nc_ids = {}
            with transaction.atomic():
                inspection = form.save(commit=False)
                if not autosave and not missing_required and was_draft and inspection.status == InspectionStatus.DRAFT:
                    inspection.status = InspectionStatus.SUBMITTED
                inspection.save()
                department = derive_department(template.area_code, inspection.area_detail)

                rep_ids = [v for v in request.POST.getlist("area_rep_ids") if v]
                inspection.area_representatives.set(User.objects.filter(pk__in=rep_ids))
                area_rep_text = ", ".join(str(u) for u in inspection.area_representatives.all())

                for section in sections:
                    for subsection in section.subsections.all():
                        for item in subsection.items.all():
                            result = request.POST.get(f"item_{item.id}_result", ItemResult.OK)
                            note = request.POST.get(f"item_{item.id}_note", "").strip()
                            InspectionItemResult.objects.update_or_create(
                                inspection=inspection, item=item, defaults={"result": result, "note": note},
                            )

                            nc_total = int(request.POST.get(f"item_{item.id}_nc-TOTAL_FORMS", 0) or 0)
                            kept_ids = set()
                            for i in range(nc_total):
                                prefix = f"item_{item.id}_nc-{i}-"
                                existing_id = request.POST.get(prefix + "id") or None
                                description = request.POST.get(prefix + "description", "").strip()
                                if result != ItemResult.NC:
                                    continue
                                nc = (
                                    NonConformity.objects.filter(pk=existing_id, inspection=inspection).first()
                                    if existing_id else None
                                )
                                if not description:
                                    if not nc:
                                        continue
                                    # Niezgodność już istnieje (np. powstała od zdjęcia) - nie kasujemy jej
                                    # tylko dlatego, że opis jest jeszcze pusty.
                                    description = NC_PLACEHOLDER_DESCRIPTION
                                location = request.POST.get(prefix + "location", "").strip()
                                responsible_id = request.POST.get(prefix + "responsible") or None
                                if nc:
                                    nc.department = department
                                    nc.location_detail = location
                                    nc.description = description
                                    nc.responsible_person_id = responsible_id
                                    nc.save()
                                else:
                                    nc = _create_item_nc(
                                        inspection, item, section, department, area_rep_text,
                                        location, description, responsible_id,
                                    )
                                kept_ids.add(nc.pk)
                                item_nc_ids.setdefault(str(item.id), {})[str(i)] = nc.pk
                                for photo in request.FILES.getlist(prefix + "photos"):
                                    NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

                            if not autosave:
                                NonConformity.objects.filter(
                                    inspection=inspection, checklist_item=item, is_extra=False,
                                ).exclude(pk__in=kept_ids).delete()

                # --- dodatkowe niezgodności (bez konkretnego punktu / dowolny wybrany punkt) ---
                extra_total = int(request.POST.get("extra-TOTAL_FORMS", 0) or 0)
                kept_extra_ids = set()
                for i in range(extra_total):
                    prefix = f"extra-{i}-"
                    description = request.POST.get(prefix + "description", "").strip()
                    existing_id = request.POST.get(prefix + "id") or None
                    nc = (
                        NonConformity.objects.filter(pk=existing_id, inspection=inspection, is_extra=True).first()
                        if existing_id else None
                    )
                    if not description:
                        if not nc:
                            continue
                        description = NC_PLACEHOLDER_DESCRIPTION
                    item_id = request.POST.get(prefix + "item") or None
                    responsible_id = request.POST.get(prefix + "responsible") or None
                    location = request.POST.get(prefix + "location", "").strip()
                    item_id, point_label, point_desc, category = _resolve_extra_point(all_items, item_id)

                    if nc:
                        nc.checklist_item_id = item_id
                        nc.department = department
                        nc.gmp_category = category
                        nc.checklist_point_label = point_label or "Brak punktu odniesienia"
                        nc.point_description = point_desc
                        nc.location_detail = location
                        nc.description = description
                        nc.responsible_person_id = responsible_id
                        nc.save()
                    else:
                        nc = _create_extra_nc(
                            inspection, department, area_rep_text, all_items,
                            item_id, location, description, responsible_id,
                        )
                    kept_extra_ids.add(nc.pk)
                    extra_nc_ids[str(i)] = nc.pk
                    for photo in request.FILES.getlist(prefix + "photos"):
                        NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

                if autosave:
                    # Autozapis nigdy nie kasuje "z domysłu" - usuwa tylko niezgodności, które
                    # użytkownik jawnie usunął przyciskiem (ich id wysyła JS w delete_nc_ids).
                    explicit = [int(v) for v in request.POST.get("delete_nc_ids", "").split(",") if v.strip().isdigit()]
                    inspection.nonconformities.filter(pk__in=explicit).delete()
                else:
                    inspection.nonconformities.filter(is_extra=True).exclude(pk__in=kept_extra_ids).delete()

                _recalculate_section_points(inspection)

            if autosave:
                return JsonResponse({
                    "saved": True, "saved_at": timezone.localtime().strftime("%H:%M:%S"),
                    "item_nc_ids": item_nc_ids, "extra_nc_ids": extra_nc_ids,
                    "nonconformity_count": inspection.nonconformity_count,
                })
            if missing_required:
                # Wersja robocza zapisana (nic nie przepadło), ale NIE zakończona.
                _flash_missing_required(request, missing_required, saved_as_draft=True)
                return redirect("inspection_edit", pk=inspection.pk)
            messages.success(request, "Inspekcja zakończona i zapisana." if was_draft else "Inspekcja zaktualizowana.")
            without_description = inspection.nonconformities.filter(description=NC_PLACEHOLDER_DESCRIPTION).count()
            if without_description:
                messages.warning(
                    request,
                    f"{without_description} niezgodności nie ma jeszcze opisu (same zdjęcia) - "
                    "uzupełnij je w edycji inspekcji.",
                )
            return redirect("inspection_detail", pk=inspection.pk)
        elif autosave:
            return JsonResponse({"saved": False, "errors": form.errors})
    else:
        form = InspectionAdminEditForm(instance=inspection, initial={
            "inspected_at": timezone.localtime(inspection.inspected_at).strftime("%Y-%m-%dT%H:%M"),
        })

    if template.area_code == AreaCode.MIX:
        # Formularz Miksowanie ma w nagłówku stoły zamiast linii produkcyjnych.
        form.fields["lines_working"].label = 'Ilość stołów "pracujących" (oraz info o rodzaju miksu - ile rodzajów FERT do jednego kartonu)'
        form.fields["lines_not_working_cleaning"].label = "Ilość stołów niepracujących"

    if was_draft:
        # Nowa/robocza inspekcja: status i inspektor ustawiają się automatycznie
        # (patrz wyżej) - nie pokazujemy ich jako edytowalnych pól zwykłemu audytorowi.
        form.fields["status"].widget = forms.HiddenInput()
        form.fields["inspector"].widget = forms.HiddenInput()

    item_results = {r.item_id: r for r in InspectionItemResult.objects.filter(inspection=inspection)}
    item_ncs = {}
    for nc in inspection.nonconformities.filter(is_extra=False, checklist_item__isnull=False).select_related("responsible_person").prefetch_related("photos"):
        item_ncs.setdefault(nc.checklist_item_id, []).append(nc)
    extra_ncs = list(
        inspection.nonconformities.filter(is_extra=True)
        .select_related("checklist_item", "responsible_person").prefetch_related("photos")
    )
    area_rep_ids_csv = ",".join(str(i) for i in inspection.area_representatives.values_list("pk", flat=True))

    return render(request, "audits/inspection_edit.html", {
        "form": form,
        "inspection": inspection,
        "sections": sections,
        "all_items": all_items,
        "item_results": item_results,
        "item_ncs": item_ncs,
        "extra_ncs": extra_ncs,
        "area_rep_ids_csv": area_rep_ids_csv,
        "wed_location_choices": WED_LOCATION_CHOICES,
        "is_draft": was_draft,
    })


MAX_PHOTOS_PER_NC = 10
MAX_PHOTO_BYTES = 40 * 1024 * 1024


@require_POST
@login_required
def inspection_photo_upload(request, pk):
    """Zapisuje JEDNO zdjęcie od razu po jego zrobieniu (osobne, małe żądanie zamiast
    wysyłania wszystkich zdjęć razem z całym formularzem). Jeśli niezgodność, do której
    należy zdjęcie, jeszcze nie istnieje (audytor zrobił zdjęcie przed wpisaniem opisu),
    jest tworzona z opisem zastępczym - zdjęcie nigdy nie jest odrzucane."""
    inspection = get_object_or_404(Inspection, pk=pk)
    if not request.user.has_full_access:
        return JsonResponse({"ok": False, "error": "Brak uprawnień do tej inspekcji."}, status=403)

    photo = request.FILES.get("photo")
    if not photo:
        return JsonResponse({"ok": False, "error": "Nie otrzymano pliku zdjęcia."}, status=400)
    if photo.size > MAX_PHOTO_BYTES:
        return JsonResponse({"ok": False, "error": "Zdjęcie jest zbyt duże (limit 40 MB)."}, status=413)
    looks_like_image = (photo.content_type or "").startswith("image/") or \
        photo.name.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"))
    if not looks_like_image:
        return JsonResponse({"ok": False, "error": "To nie jest plik zdjęcia."}, status=400)

    template = inspection.template
    kind = request.POST.get("kind")
    nc_id = request.POST.get("nc_id") or None
    nc = NonConformity.objects.filter(pk=nc_id, inspection=inspection).first() if nc_id else None

    with transaction.atomic():
        if nc is None:
            sections = list(template.sections.prefetch_related("subsections__items").all())
            all_items = [it for sec in sections for sub in sec.subsections.all() for it in sub.items.all()]
            department = derive_department(template.area_code, inspection.area_detail)
            area_rep_text = ", ".join(str(u) for u in inspection.area_representatives.all())
            description = request.POST.get("description", "").strip() or NC_PLACEHOLDER_DESCRIPTION
            location = request.POST.get("location", "").strip()
            responsible_id = request.POST.get("responsible") or None
            if responsible_id and not str(responsible_id).isdigit():
                responsible_id = None

            if kind == "item":
                item = get_object_or_404(
                    ChecklistItem, pk=request.POST.get("item_id"), subsection__section__template=template,
                )
                nc = _create_item_nc(
                    inspection, item, item.subsection.section, department, area_rep_text,
                    location, description, responsible_id,
                )
                InspectionItemResult.objects.update_or_create(
                    inspection=inspection, item=item, defaults={"result": ItemResult.NC},
                )
            else:
                nc = _create_extra_nc(
                    inspection, department, area_rep_text, all_items,
                    request.POST.get("item_id") or None, location, description, responsible_id,
                )

        if nc.photos.count() >= MAX_PHOTOS_PER_NC:
            return JsonResponse(
                {"ok": False, "error": f"Maksymalnie {MAX_PHOTOS_PER_NC} zdjęć do jednej niezgodności."}, status=400,
            )
        saved = NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

    return JsonResponse({"ok": True, "nc_id": nc.pk, "photo_id": saved.pk, "url": saved.image.url})


@require_POST
@login_required
def nc_photo_delete(request, pk):
    photo = get_object_or_404(NonConformityPhoto.objects.select_related("nonconformity__inspection"), pk=pk)
    # Zdjęcie niezgodności może usunąć każdy, kto może edytować inspekcję (pomyłka przy
    # robieniu zdjęcia); zdjęcia "dowód działań" (dodane przez osobę odpowiedzialną) - tylko administrator.
    can_delete = request.user.is_admin_role or (
        request.user.has_full_access and photo.kind == NCPhotoKind.NIEZGODNOSC
    )
    if not can_delete:
        return JsonResponse({"ok": False, "error": "Brak uprawnień do usunięcia tego zdjęcia."}, status=403)
    name = photo.image.name
    photo.delete()
    PhotoArchive.objects.filter(image=name).delete()
    photo.image.storage.delete(name)
    return JsonResponse({"ok": True})


@require_POST
@login_required
def inspection_move_nc(request, pk):
    """Przenosi niezgodność (opis, lokalizację, osobę odpowiedzialną i WSZYSTKIE jej zdjęcia)
    do innego punktu checklisty - np. gdy AI wskazało, że zdjęcie dotyczy innego punktu."""
    inspection = get_object_or_404(Inspection, pk=pk)
    if not request.user.has_full_access:
        return JsonResponse({"ok": False, "error": "Brak uprawnień do tej inspekcji."}, status=403)
    nc = get_object_or_404(NonConformity, pk=request.POST.get("nc_id"), inspection=inspection, is_extra=False)
    target = get_object_or_404(
        ChecklistItem.objects.select_related("subsection__section"),
        pk=request.POST.get("target_item_id"), subsection__section__template=inspection.template,
    )
    source = nc.checklist_item
    description = request.POST.get("description", "").strip()

    if source is None or source.pk != target.pk:
        with transaction.atomic():
            nc.checklist_item = target
            nc.gmp_category = target.subsection.section.name
            nc.checklist_point_label = target.number
            nc.point_description = target.description[:400]
            if description:
                nc.description = description
            nc.save()
            InspectionItemResult.objects.update_or_create(
                inspection=inspection, item=target, defaults={"result": ItemResult.NC},
            )
            # Punkt, z którego przeniesiono jedyną niezgodność, wraca do "zgodny".
            if source is not None and not NonConformity.objects.filter(
                inspection=inspection, checklist_item=source, is_extra=False,
            ).exists():
                InspectionItemResult.objects.filter(inspection=inspection, item=source).update(result=ItemResult.OK)
            _recalculate_section_points(inspection)
    return JsonResponse({"ok": True, "target_item_id": target.pk})


@login_required
def photo_gallery(request):
    """Galeria wszystkich zdjęć zapisanych w aplikacji (w zakresie działów użytkownika).
    Czyta z archiwum (PhotoArchive), do którego zdjęcie trafia w chwili zapisu - czyli
    także zdjęcia z wersji roboczych i takie, których niezgodność/inspekcję usunięto."""
    photos = PhotoArchive.objects.select_related("nonconformity", "inspection")
    scope = request.user.department_scope
    if scope is not None:
        photos = photos.filter(department__in=scope)

    department = request.GET.get("department", "")
    if department:
        photos = photos.filter(department=department)
    year = request.GET.get("year", "")
    if year.isdigit():
        photos = photos.filter(inspection_date__year=int(year))

    page = Paginator(photos, 48).get_page(request.GET.get("page"))
    return render(request, "audits/photo_gallery.html", {
        "page": page,
        "current_department": department,
        "current_year": year,
        "department_choices": [(c, l) for c, l in Department.choices if scope is None or c in scope],
        "years": sorted(
            {d.year for d in PhotoArchive.objects.exclude(inspection_date=None).values_list("inspection_date", flat=True)},
            reverse=True,
        ),
        "can_delete": request.user.is_admin_role,
    })


@require_POST
@login_required
def gallery_photo_delete(request, pk):
    """Jedyny sposób na usunięcie zdjęcia z galerii "na stałe" (administrator)."""
    if not _require_admin(request):
        return redirect("photo_gallery")
    archived = get_object_or_404(PhotoArchive, pk=pk)
    name = archived.image.name
    NonConformityPhoto.objects.filter(image=name).delete()
    PhotoArchive.objects.filter(image=name).delete()
    archived.image.storage.delete(name)
    messages.success(request, "Zdjęcie zostało usunięte z galerii i z inspekcji.")
    return redirect(request.META.get("HTTP_REFERER") or "photo_gallery")


@require_POST
@login_required
def inspection_delete(request, pk):
    inspection = get_object_or_404(Inspection, pk=pk)
    is_own_draft = (
        inspection.status == InspectionStatus.DRAFT and inspection.inspector_id == request.user.id
    )
    if not is_own_draft and not _require_admin(request):
        return redirect("inspection_detail", pk=pk)

    try:
        inspection.delete()
        messages.success(request, "Inspekcja i powiązane z nią niezgodności zostały usunięte.")
    except ProtectedError:
        messages.error(request, "Nie można usunąć tej inspekcji - jest powiązana z innymi danymi.")
        return redirect("inspection_detail", pk=pk)

    return redirect("inspection_list")


@require_POST
@login_required
def inspection_toggle_hidden(request, pk):
    if not _require_admin(request):
        return redirect("inspection_detail", pk=pk)

    inspection = get_object_or_404(Inspection, pk=pk)
    inspection.is_hidden = not inspection.is_hidden
    inspection.save(update_fields=["is_hidden"])
    if inspection.is_hidden:
        messages.success(request, "Inspekcja ukryta z rejestru inspekcji (widoczna nadal dla QualityAdmin/Helpdesku).")
    else:
        messages.success(request, "Inspekcja przywrócona do rejestru inspekcji.")
    return redirect("inspection_detail", pk=pk)


@login_required
def inspection_report(request, pk):
    inspection = get_object_or_404(Inspection.objects.select_related("template", "inspector"), pk=pk)
    if request.method == "POST":
        form = InspectionSummaryForm(request.POST)
        if form.is_valid():
            inspection.summary_good = form.cleaned_data["summary_good"]
            inspection.summary_to_fix = form.cleaned_data["summary_to_fix"]
            inspection.comment = form.cleaned_data["comment"]
            inspection.report_recipients = form.cleaned_data["report_recipients"]
            inspection.status = "REPORT_SENT"
            inspection.report_sent_at = timezone.now()
            inspection.save()

            recipients = [r.strip() for r in inspection.report_recipients.split(",") if r.strip()]
            if recipients:
                app_link = request.build_absolute_uri(reverse("inspection_detail", args=[inspection.pk]))
                section_results = inspection.section_results.select_related("section").order_by("section__order")
                nonconformities = _ordered_nonconformities(
                    inspection.nonconformities.prefetch_related("photos")
                )
                pdf_bytes = render_inspection_pdf(inspection, section_results, nonconformities, app_link=app_link)
                body = render_to_string("audits/email_report.txt", {"inspection": inspection, "app_link": app_link})
                result = send_report_email(
                    subject=f"Raport inspekcji GMP/GHP - {inspection.template.get_area_code_display()} - {inspection.inspected_at:%d.%m.%Y}",
                    body_text=body,
                    recipients=recipients,
                    pdf_bytes=pdf_bytes,
                    pdf_filename=f"raport_inspekcji_{inspection.pk}.pdf",
                )
                if result["sent"]:
                    messages.success(request, f"Raport wysłany do: {', '.join(recipients)}")
                else:
                    messages.warning(
                        request,
                        f"Raport zapisany, ale wysyłka e-mail się nie powiodła: {result['error']}",
                    )
            else:
                messages.success(request, "Raport zapisany.")
            return redirect("inspection_detail", pk=inspection.pk)
    else:
        form = InspectionSummaryForm(initial={
            "summary_good": inspection.summary_good,
            "summary_to_fix": inspection.summary_to_fix,
            "comment": inspection.comment,
            "report_recipients": inspection.report_recipients,
        })

    section_results = inspection.section_results.select_related("section").order_by("section__order")
    nonconformities = _ordered_nonconformities(
        inspection.nonconformities.prefetch_related("photos")
    )
    return render(request, "audits/inspection_report.html", {
        "inspection": inspection,
        "section_results": section_results,
        "nonconformities": nonconformities,
        "form": form,
    })


@login_required
def inspection_report_pdf(request, pk):
    inspection = get_object_or_404(Inspection.objects.select_related("template", "inspector"), pk=pk)
    section_results = inspection.section_results.select_related("section").order_by("section__order")
    nonconformities = _ordered_nonconformities(
        inspection.nonconformities.prefetch_related("photos")
    )
    app_link = request.build_absolute_uri(reverse("inspection_detail", args=[inspection.pk]))
    pdf_bytes = render_inspection_pdf(inspection, section_results, nonconformities, app_link=app_link)
    if pdf_bytes is None:
        messages.error(request, "Nie udało się wygenerować PDF-a raportu.")
        return redirect("inspection_report", pk=inspection.pk)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="raport_inspekcji_{inspection.pk}.pdf"'
    return response


@login_required
def nonconformity_list(request):
    qs = _scoped_nonconformities(request.user)

    status = request.GET.get("status")
    department = request.GET.get("department")
    scope = request.GET.get("scope")

    if status:
        qs = qs.filter(status=status)
    if department:
        qs = qs.filter(department=department)
    if scope == "mine":
        qs = qs.filter(responsible_person=request.user)
    elif scope == "overdue":
        qs = [nc for nc in qs if nc.is_due_for_reminder]

    if not isinstance(qs, list):
        qs = list(qs)

    return render(request, "audits/nonconformity_list.html", {
        "nonconformities": qs,
        "status_choices": NCStatus.choices,
        "current_status": status or "",
        "current_department": department or "",
        "current_scope": scope or "",
        "department_choices": [
            (c, l) for c, l in Department.choices
            if request.user.department_scope is None or c in request.user.department_scope
        ],
    })


@login_required
def nonconformity_detail(request, pk):
    nc = get_object_or_404(NonConformity.objects.select_related("inspector", "responsible_person", "inspection"), pk=pk)
    is_admin = request.user.is_admin_role
    can_edit_responsible = (
        request.user == nc.responsible_person or _user_on_nc_shift(request.user, nc)
        or is_admin or request.user.is_staff
    )
    can_edit_auditor = request.user == nc.inspector or is_admin or request.user.is_staff

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_responsible" and can_edit_responsible:
            form = ResponsibleActionForm(request.POST, instance=nc)
            if form.is_valid():
                nc = form.save()
                evidence = request.FILES.getlist("evidence_photos")
                for photo in evidence:
                    NonConformityPhoto.objects.create(nonconformity=nc, image=photo, kind="DOWOD")
                # Samo otwarcie rekordu nie zmienia statusu - dopiero zapis z wpisanymi danymi.
                entered = evidence or any(form.cleaned_data.get(f) for f in form.fields)
                if nc.status == NCStatus.ZAREJESTROWANA and entered:
                    nc.status = NCStatus.W_TOKU
                    nc.save(update_fields=["status", "updated_at"])
                messages.success(request, "Działania zapisane. Dziękujemy za uzupełnienie.")
                return redirect("nonconformity_detail", pk=nc.pk)
        elif action == "save_auditor" and can_edit_auditor:
            form = AuditorReviewForm(request.POST, instance=nc)
            if form.is_valid():
                form.save()
                messages.success(request, "Status niezgodności zaktualizowany.")
                return redirect("nonconformity_detail", pk=nc.pk)
        elif action == "save_admin_fields" and is_admin:
            admin_form = StandaloneNonConformityForm(request.POST, instance=nc)
            if admin_form.is_valid():
                admin_form.save()
                messages.success(request, "Dane niezgodności zaktualizowane.")
                return redirect("nonconformity_detail", pk=nc.pk)
        else:
            messages.error(request, "Nie masz uprawnień do edycji tej części formularza.")

    responsible_form = ResponsibleActionForm(instance=nc)
    auditor_form = AuditorReviewForm(instance=nc)
    admin_form = StandaloneNonConformityForm(instance=nc)

    return render(request, "audits/nonconformity_detail.html", {
        "nc": nc,
        "responsible_form": responsible_form,
        "auditor_form": auditor_form,
        "admin_form": admin_form,
        "can_edit_responsible": can_edit_responsible,
        "can_edit_auditor": can_edit_auditor,
        "is_admin": is_admin,
    })


@require_POST
@login_required
def nonconformity_delete(request, pk):
    if not _require_admin(request):
        return redirect("nonconformity_detail", pk=pk)

    nc = get_object_or_404(NonConformity, pk=pk)
    number = nc.number
    nc.delete()
    messages.success(request, f"Niezgodność {number} została usunięta.")
    return redirect("nonconformity_list")


@login_required
def nonconformity_new(request):
    if request.method == "POST":
        form = StandaloneNonConformityForm(request.POST)
        if form.is_valid():
            nc = form.save(commit=False)
            nc.inspector = request.user
            nc.save()
            for photo in request.FILES.getlist("photos"):
                NonConformityPhoto.objects.create(nonconformity=nc, image=photo)
            messages.success(request, f"Niezgodność {nc.number} została zapisana w rejestrze.")
            return redirect("nonconformity_detail", pk=nc.pk)
    else:
        form = StandaloneNonConformityForm(initial={"inspection_date": timezone.localdate()})
    return render(request, "audits/nonconformity_form.html", {"form": form})
