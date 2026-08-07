from datetime import timedelta

from accounts.models import Department
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db.models import Count, ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ai import suggest_nc_description
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
    ChecklistTemplate,
    Inspection,
    InspectionItemResult,
    InspectionSectionResult,
    InspectionStatus,
    ItemResult,
    NCStatus,
    NonConformity,
    NonConformityPhoto,
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
    """AJAX: zwraca osoby z danej zmiany - do automatycznego uzupełnienia
    przedstawicieli obszaru podczas inspekcji."""
    shift = request.GET.get("shift", "")
    qs = User.objects.filter(shift=shift, is_active=True).order_by("last_name", "first_name") if shift else User.objects.none()
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
                            if not description:
                                continue
                            responsible_id = request.POST.get(f"item_{item.id}_responsible") or None
                            nc = NonConformity.objects.create(
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
                                location_detail=request.POST.get(f"item_{item.id}_location", "").strip(),
                                description=description,
                                responsible_person_id=responsible_id,
                            )
                            for photo in request.FILES.getlist(f"item_{item.id}_photos"):
                                NonConformityPhoto.objects.create(nonconformity=nc, image=photo)

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
                    checklist_point_label=point_label or "brak punktu",
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
    nonconformities = inspection.nonconformities.select_related("responsible_person").all()
    return render(request, "audits/inspection_detail.html", {
        "inspection": inspection,
        "section_results": section_results,
        "nonconformities": nonconformities,
    })


@login_required
def inspection_edit(request, pk):
    if not _require_admin(request):
        return redirect("inspection_detail", pk=pk)

    inspection = get_object_or_404(Inspection, pk=pk)
    if request.method == "POST":
        form = InspectionAdminEditForm(request.POST, instance=inspection)
        if form.is_valid():
            form.save()
            messages.success(request, "Inspekcja zaktualizowana.")
            return redirect("inspection_detail", pk=inspection.pk)
    else:
        form = InspectionAdminEditForm(instance=inspection, initial={
            "inspected_at": timezone.localtime(inspection.inspected_at).strftime("%Y-%m-%dT%H:%M"),
        })

    return render(request, "audits/inspection_edit.html", {"form": form, "inspection": inspection})


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
    nonconformities = inspection.nonconformities.prefetch_related("photos").all()
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
