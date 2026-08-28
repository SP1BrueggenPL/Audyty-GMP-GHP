from datetime import timedelta

from accounts.models import Department, Role
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Case, Count, ProtectedError, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ai import suggest_inspection_summary, suggest_nc_description
from .forms import (
    AuditorReviewForm,
    InspectionAdminEditForm,
    InspectionHeaderForm,
    InspectionSummaryForm,
    ResponsibleActionForm,
    StandaloneNonConformityForm,
    derive_department,
)
from .models import (
    ChecklistItem,
    ChecklistTemplate,
    Inspection,
    InspectionItemResult,
    InspectionSectionResult,
    InspectionStatus,
    ItemResult,
    NCStatus,
    NonConformity,
    NonConformityPhoto,
    Shift,
)

User = get_user_model()


def _scoped_nonconformities(user):
    qs = NonConformity.objects.select_related("inspector", "responsible_person")
    scope = user.department_scope
    if scope is not None:
        qs = qs.filter(department__in=scope)
    return qs


def _scoped_inspections(user):
    qs = Inspection.objects.select_related("template", "inspector")
    scope = user.department_scope
    if scope is None:
        return qs
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
        "my_open_tasks": NonConformity.objects.filter(
            responsible_person=request.user,
        ).exclude(status=NCStatus.WDROZONE)[:10],
        "templates": ChecklistTemplate.objects.filter(is_active=True),
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
def users_by_shift(request):
    """AJAX: zwraca Użytkowników obszaru pasujących do działu inspekcji (wyznaczonego
    z area_code/area_detail), dodatkowo zawężonych po zmianie gdy ta ma zastosowanie.
    Filtrowanie wyłącznie po zmianie nie działało dla działów bez zmian (np. Techniczny/
    WED, gdzie zmiana to zawsze "n/d") - stąd dział jako podstawowe kryterium."""
    area_code = request.GET.get("area_code", "")
    area_detail = request.GET.get("area_detail", "")
    shift = request.GET.get("shift", "")

    if not area_code and not shift:
        return JsonResponse({"users": []})

    qs = User.objects.filter(role=Role.UZYTKOWNIK_OBSZARU, is_active=True)
    if area_code:
        qs = qs.filter(department=derive_department(area_code, area_detail))
    if shift and shift != Shift.ND:
        qs = qs.filter(shift=shift)
    qs = qs.order_by("last_name", "first_name")
    return JsonResponse({"users": [{"id": u.pk, "name": str(u)} for u in qs]})


@login_required
def suggest_nonconformity(request):
    """AJAX: podpowiedź opisu niezgodności (Azure OpenAI GPT-4o) na bazie zdjęcia
    oraz wcześniej zapisanych niezgodności dla tego samego punktu checklisty."""
    item_id = request.POST.get("item_id")
    photo = request.FILES.get("photo")
    past_examples = list(
        NonConformity.objects.filter(checklist_item_id=item_id)
        .order_by("-id").values_list("description", flat=True)[:5]
    ) if item_id else []
    result = suggest_nc_description(photo=photo, past_examples=past_examples)
    return JsonResponse(result)


@login_required
def suggest_inspection_summary_view(request):
    """AJAX: propozycja podsumowania inspekcji metodą hamburgera (Azure OpenAI).
    Do promptu trafiają WYŁĄCZNIE punkt checklisty i opis niezgodności - bez
    nazwisk, działów ani lokalizacji (dane zanonimizowane)."""
    inspection_id = request.POST.get("inspection_id")
    inspection = get_object_or_404(Inspection, pk=inspection_id)
    ncs = inspection.nonconformities.all()
    nc_points = [(nc.checklist_point_label, nc.description) for nc in ncs]
    total_count = len(ChecklistItem.objects.filter(subsection__section__template=inspection.template))
    ok_count = max(0, total_count - len({nc.checklist_item_id for nc in ncs if nc.checklist_item_id}))
    result = suggest_inspection_summary(nc_points, ok_count, total_count)
    return JsonResponse(result)


@login_required
def inspection_new(request, template_id):
    if not request.user.can_run_inspections:
        messages.error(request, "Twoja rola nie pozwala na przeprowadzanie inspekcji.")
        return redirect("dashboard")
    template = get_object_or_404(ChecklistTemplate, pk=template_id, is_active=True)
    sections = list(
        template.sections.prefetch_related("subsections__items").all()
    )

    if request.method == "POST":
        header_form = InspectionHeaderForm(request.POST, area_code=template.area_code)
        summary_form = InspectionSummaryForm(request.POST)
        if header_form.is_valid() and summary_form.is_valid():
            hc = header_form.cleaned_data
            inspection = Inspection.objects.create(
                template=template,
                inspected_at=hc["inspected_at"],
                area_detail=hc["area_detail"],
                shift=hc["shift"],
                inspector=request.user,
                lines_working=hc["lines_working"],
                lines_not_working_cleaning=hc["lines_not_working_cleaning"],
                lines_not_working_stopped=hc["lines_not_working_stopped"],
                rooms_checked=hc["rooms_checked"],
                summary_good=summary_form.cleaned_data["summary_good"],
                summary_to_fix=summary_form.cleaned_data["summary_to_fix"],
            )

            rep_ids = [v for v in request.POST.getlist("area_rep_ids") if v]
            reps = list(User.objects.filter(pk__in=rep_ids))
            if reps:
                inspection.area_representatives.set(reps)
            area_rep_text = ", ".join(str(u) for u in reps)

            department = derive_department(template.area_code, hc["area_detail"])

            for section in sections:
                for subsection in section.subsections.all():
                    for item in subsection.items.all():
                        result = request.POST.get(f"item_{item.id}_result", ItemResult.OK)
                        note = request.POST.get(f"item_{item.id}_note", "").strip()
                        InspectionItemResult.objects.create(
                            inspection=inspection, item=item, result=result, note=note,
                        )
                        if result == ItemResult.NC:
                            description = request.POST.get(f"item_{item.id}_description", "").strip() or note
                            if description:
                                responsible_id = request.POST.get(f"item_{item.id}_responsible") or None
                                nc = _create_item_nc(
                                    inspection, item, section, department, area_rep_text,
                                    request.POST.get(f"item_{item.id}_location", "").strip(),
                                    description, responsible_id,
                                )
                                for photo in request.FILES.getlist(f"item_{item.id}_photos"):
                                    NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

                            # Dodatkowe niezgodności dodane przyciskiem "+" bezpośrednio przy tym punkcie.
                            item_extra_total = int(request.POST.get(f"item_{item.id}_extra-TOTAL_FORMS", 0) or 0)
                            for ei in range(item_extra_total):
                                eprefix = f"item_{item.id}_extra-{ei}-"
                                edescription = request.POST.get(eprefix + "description", "").strip()
                                if not edescription:
                                    continue
                                eresponsible_id = request.POST.get(eprefix + "responsible") or None
                                enc = _create_item_nc(
                                    inspection, item, section, department, area_rep_text,
                                    request.POST.get(eprefix + "location", "").strip(),
                                    edescription, eresponsible_id,
                                )
                                for photo in request.FILES.getlist(eprefix + "photos"):
                                    NonConformityPhoto.objects.create(nonconformity=enc, image=photo)

            # Punkty sekcji: każda niezgodność na punkcie checklisty odlicza 1 pkt
            # (minimum 0 - jeśli liczba NC >= max punktów sekcji, sekcja ma 0 pkt).
            for section in sections:
                nc_count = NonConformity.objects.filter(
                    inspection=inspection, is_extra=False, checklist_item__subsection__section=section,
                ).count()
                points = max(0, section.max_points - nc_count)
                InspectionSectionResult.objects.create(inspection=inspection, section=section, points_awarded=points)

            extra_total = int(request.POST.get("extra-TOTAL_FORMS", 0) or 0)
            for i in range(extra_total):
                prefix = f"extra-{i}-"
                description = request.POST.get(prefix + "description", "").strip()
                if not description:
                    continue
                item_id = request.POST.get(prefix + "item") or None
                responsible_id = request.POST.get(prefix + "responsible") or None
                point_label = ""
                point_desc = ""
                category = ""
                if item_id:
                    try:
                        chosen_item = next(
                            it for s in sections for sub in s.subsections.all() for it in sub.items.all()
                            if str(it.id) == item_id
                        )
                        point_label = chosen_item.number
                        point_desc = chosen_item.description[:400]
                        category = chosen_item.subsection.section.name
                    except StopIteration:
                        item_id = None
                nc = NonConformity.objects.create(
                    inspection=inspection,
                    checklist_item_id=item_id,
                    is_extra=True,
                    inspection_date=inspection.inspected_at.date(),
                    department=department,
                    inspector=inspection.inspector,
                    shift=inspection.shift,
                    area_representative=area_rep_text,
                    gmp_category=category,
                    checklist_point_label=point_label or "Brak punktu odniesienia",
                    point_description=point_desc,
                    location_detail=request.POST.get(prefix + "location", "").strip(),
                    description=description,
                    responsible_person_id=responsible_id,
                )
                for photo in request.FILES.getlist(prefix + "photos"):
                    NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

            inspection.status = "SUBMITTED"
            inspection.save()
            messages.success(request, f"Inspekcja zapisana. Utworzono {inspection.nonconformity_count} niezgodności.")
            return redirect("inspection_detail", pk=inspection.pk)
        else:
            messages.error(request, "Uzupełnij wymagane pola w nagłówku inspekcji.")
    else:
        header_form = InspectionHeaderForm(area_code=template.area_code, initial={
            "inspected_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
        })
        summary_form = InspectionSummaryForm()

    all_items = [it for s in sections for sub in s.subsections.all() for it in sub.items.all()]

    return render(request, "audits/inspection_form.html", {
        "template_obj": template,
        "sections": sections,
        "header_form": header_form,
        "summary_form": summary_form,
        "all_items": all_items,
        "item_results": ItemResult.choices,
    })


@login_required
def inspection_list(request):
    if not request.user.can_run_inspections:
        messages.error(request, "Rejestr inspekcji jest dostępny dla Audytora, QualityAdmin i Helpdesku.")
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

    if request.method == "POST":
        form = InspectionAdminEditForm(request.POST, instance=inspection)
        if form.is_valid():
            with transaction.atomic():
                inspection = form.save()
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
                                if result != ItemResult.NC or not description:
                                    continue
                                nc = (
                                    NonConformity.objects.filter(pk=existing_id, inspection=inspection).first()
                                    if existing_id else None
                                )
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
                                for photo in request.FILES.getlist(prefix + "photos"):
                                    NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

                            NonConformity.objects.filter(
                                inspection=inspection, checklist_item=item, is_extra=False,
                            ).exclude(pk__in=kept_ids).delete()

                # --- dodatkowe niezgodności (bez konkretnego punktu / dowolny wybrany punkt) ---
                extra_total = int(request.POST.get("extra-TOTAL_FORMS", 0) or 0)
                kept_extra_ids = set()
                for i in range(extra_total):
                    prefix = f"extra-{i}-"
                    description = request.POST.get(prefix + "description", "").strip()
                    if not description:
                        continue
                    existing_id = request.POST.get(prefix + "id") or None
                    item_id = request.POST.get(prefix + "item") or None
                    responsible_id = request.POST.get(prefix + "responsible") or None
                    location = request.POST.get(prefix + "location", "").strip()

                    point_label, point_desc, category = "", "", ""
                    if item_id:
                        chosen_item = next((it for it in all_items if str(it.id) == item_id), None)
                        if chosen_item:
                            point_label = chosen_item.number
                            point_desc = chosen_item.description[:400]
                            category = chosen_item.subsection.section.name
                        else:
                            item_id = None

                    nc = (
                        NonConformity.objects.filter(pk=existing_id, inspection=inspection, is_extra=True).first()
                        if existing_id else None
                    )
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
                        nc = NonConformity.objects.create(
                            inspection=inspection, checklist_item_id=item_id, is_extra=True,
                            inspection_date=inspection.inspected_at.date(),
                            department=department, inspector=inspection.inspector, shift=inspection.shift,
                            area_representative=area_rep_text,
                            gmp_category=category, checklist_point_label=point_label or "Brak punktu odniesienia",
                            point_description=point_desc, location_detail=location, description=description,
                            responsible_person_id=responsible_id,
                        )
                    kept_extra_ids.add(nc.pk)
                    for photo in request.FILES.getlist(prefix + "photos"):
                        NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

                inspection.nonconformities.filter(is_extra=True).exclude(pk__in=kept_extra_ids).delete()

                # Punkty sekcji: każda niezgodność na punkcie checklisty odlicza 1 pkt.
                for section in sections:
                    nc_count = NonConformity.objects.filter(
                        inspection=inspection, is_extra=False, checklist_item__subsection__section=section,
                    ).count()
                    points = max(0, section.max_points - nc_count)
                    InspectionSectionResult.objects.update_or_create(
                        inspection=inspection, section=section, defaults={"points_awarded": points},
                    )

            messages.success(request, "Inspekcja zaktualizowana.")
            return redirect("inspection_detail", pk=inspection.pk)
    else:
        form = InspectionAdminEditForm(instance=inspection, initial={
            "inspected_at": timezone.localtime(inspection.inspected_at).strftime("%Y-%m-%dT%H:%M"),
        })

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
    })


@require_POST
@login_required
def inspection_delete(request, pk):
    if not _require_admin(request):
        return redirect("inspection_detail", pk=pk)

    inspection = get_object_or_404(Inspection, pk=pk)
    try:
        inspection.delete()
        messages.success(request, "Inspekcja i powiązane z nią niezgodności zostały usunięte.")
    except ProtectedError:
        messages.error(request, "Nie można usunąć tej inspekcji - jest powiązana z innymi danymi.")
        return redirect("inspection_detail", pk=pk)

    return redirect("inspection_list")


@login_required
def inspection_report(request, pk):
    inspection = get_object_or_404(Inspection.objects.select_related("template", "inspector"), pk=pk)
    if request.method == "POST":
        form = InspectionSummaryForm(request.POST)
        if form.is_valid():
            inspection.summary_good = form.cleaned_data["summary_good"]
            inspection.summary_to_fix = form.cleaned_data["summary_to_fix"]
            inspection.report_recipients = form.cleaned_data["report_recipients"]
            inspection.status = "REPORT_SENT"
            inspection.report_sent_at = timezone.now()
            inspection.save()

            recipients = [r.strip() for r in inspection.report_recipients.split(",") if r.strip()]
            if recipients:
                body = render_to_string("audits/email_report.txt", {"inspection": inspection})
                send_mail(
                    subject=f"Raport inspekcji GMP/GHP - {inspection.template.get_area_code_display()} - {inspection.inspected_at:%d.%m.%Y}",
                    message=body,
                    from_email=None,
                    recipient_list=recipients,
                    fail_silently=True,
                )
                messages.success(request, f"Raport wysłany do: {', '.join(recipients)}")
            else:
                messages.success(request, "Raport zapisany.")
            return redirect("inspection_detail", pk=inspection.pk)
    else:
        form = InspectionSummaryForm(initial={
            "summary_good": inspection.summary_good,
            "summary_to_fix": inspection.summary_to_fix,
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
    })


@login_required
def nonconformity_detail(request, pk):
    nc = get_object_or_404(NonConformity.objects.select_related("inspector", "responsible_person", "inspection"), pk=pk)
    is_admin = request.user.is_admin_role
    can_edit_responsible = request.user == nc.responsible_person or is_admin or request.user.is_staff
    can_edit_auditor = request.user == nc.inspector or is_admin or request.user.is_staff

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_responsible" and can_edit_responsible:
            form = ResponsibleActionForm(request.POST, instance=nc)
            if form.is_valid():
                form.save()
                for photo in request.FILES.getlist("evidence_photos"):
                    NonConformityPhoto.objects.create(nonconformity=nc, image=photo, kind="DOWOD")
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
