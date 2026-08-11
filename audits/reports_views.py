import json
from collections import defaultdict

from accounts.models import Department
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import derive_department
from .models import Inspection, NCStatus, NonConformity

MONTH_LABELS = ["Sty", "Lut", "Mar", "Kwi", "Maj", "Cze", "Lip", "Sie", "Wrz", "Paź", "Lis", "Gru"]
SHIFT_ORDER = ["A", "B", "C", "D", "n/d"]


def _quarter_of(month):
    return (month - 1) // 3 + 1


def _dept_label(code):
    return dict(Department.choices).get(code, code)


def _in_scope_departments(scope, department_filter):
    codes = [c for c, _ in Department.choices]
    if scope is not None:
        codes = [c for c in codes if c in scope]
    if department_filter:
        codes = [c for c in codes if c == department_filter]
    return codes


def _score_css(value):
    if value is None:
        return ""
    if value >= 85:
        return "score-good"
    if value >= 70:
        return "score-mid"
    return "score-bad"


def _score_cell(value):
    return {"value": value, "css": _score_css(value)}


def _report_filters(request):
    """Wspólna logika filtrów (dział/rok/zakres uprawnień) dla widoku i eksportu."""
    scope = request.user.department_scope
    department = request.GET.get("department", "")

    all_years = sorted(set(NonConformity.objects.values_list("inspection_date__year", flat=True)))
    default_year = timezone.localdate().year
    if not all_years:
        all_years = [default_year]
    try:
        year = int(request.GET.get("year", max(all_years)))
    except (TypeError, ValueError):
        year = max(all_years)

    base_qs = NonConformity.objects.all()
    if scope is not None:
        base_qs = base_qs.filter(department__in=scope)

    year_qs = base_qs.filter(inspection_date__year=year)
    filtered_qs = year_qs.filter(department=department) if department else year_qs

    return {
        "scope": scope, "department": department, "year": year, "all_years": all_years,
        "base_qs": base_qs, "year_qs": year_qs, "filtered_qs": filtered_qs,
    }


def _build_all_tabs(f):
    """Buduje dane wszystkich czterech zakładek naraz - używane przy eksporcie do Excela."""
    return {
        "przeglad": _build_overview_tab(f["year_qs"], f["year"]),
        "wyniki": _build_results_tab(f["base_qs"], f["scope"], f["department"], f["year"]),
        "grupy": _build_groups_tab(f["filtered_qs"], f["scope"], f["department"], f["year"]),
        "punkty": _build_points_tab(f["filtered_qs"], f["scope"], f["department"], f["year"]),
    }


@login_required
def reports_dashboard(request):
    if not request.user.can_view_reports:
        messages.error(request, "Raporty są dostępne tylko dla QualityAdmin i Helpdesku.")
        return redirect("dashboard")

    tab = request.GET.get("tab", "przeglad")
    f = _report_filters(request)

    context = {
        "tab": tab,
        "current_department": f["department"],
        "current_year": f["year"],
        "available_years": f["all_years"],
        "department_choices": [(c, _dept_label(c)) for c in _in_scope_departments(f["scope"], "")],
    }

    if tab == "wyniki":
        context.update(_build_results_tab(f["base_qs"], f["scope"], f["department"], f["year"]))
    elif tab == "grupy":
        context.update(_build_groups_tab(f["filtered_qs"], f["scope"], f["department"], f["year"]))
    elif tab == "punkty":
        context.update(_build_points_tab(f["filtered_qs"], f["scope"], f["department"], f["year"]))
    else:
        tab = "przeglad"
        context["tab"] = tab
        context.update(_build_overview_tab(f["year_qs"], f["year"]))

    if "chart_data" in context:
        context["chart_data_json"] = json.dumps(context.pop("chart_data"))

    return render(request, "audits/reports.html", context)


# ---------------------------------------------------------------------------
# Tab: Przegląd
# ---------------------------------------------------------------------------

def _build_overview_tab(qs, year):
    total_ncs = qs.count()
    by_status = list(qs.values("status").annotate(total=Count("id")).order_by("-total"))
    by_department = list(qs.values("department").annotate(total=Count("id")).order_by("-total"))
    by_category = list(
        qs.exclude(gmp_category="").values("gmp_category").annotate(total=Count("id")).order_by("-total")[:10]
    )
    top_locations = list(
        qs.exclude(location_detail="").values("location_detail").annotate(total=Count("id")).order_by("-total")[:10]
    )

    by_month_counts = [0] * 12
    for nc in qs.only("inspection_date"):
        by_month_counts[nc.inspection_date.month - 1] += 1

    closed = qs.filter(status=NCStatus.WDROZONE, actual_preventive_date__isnull=False)
    deltas = [
        (nc.actual_preventive_date - nc.entry_date).days for nc in closed if nc.actual_preventive_date
    ]
    deltas = [d for d in deltas if d >= 0]
    avg_days_to_close = round(sum(deltas) / len(deltas), 1) if deltas else None

    overdue_count = len([nc for nc in qs.filter(status=NCStatus.W_TOKU) if nc.is_due_for_reminder])

    inspections = list(Inspection.objects.filter(inspected_at__year=year).select_related("template"))
    score_by_month = defaultdict(list)
    for insp in inspections:
        pct = insp.result_percent
        if pct is None:
            continue
        score_by_month[insp.inspected_at.month].append(pct)
    score_trend_values = [
        round(sum(score_by_month[m]) / len(score_by_month[m]), 1) if score_by_month.get(m) else None
        for m in range(1, 13)
    ]

    chart_data = {
        "by_status": {
            "labels": [dict(NCStatus.choices).get(r["status"], r["status"]) for r in by_status],
            "values": [r["total"] for r in by_status],
        },
        "by_department": {
            "labels": [_dept_label(r["department"]) for r in by_department],
            "values": [r["total"] for r in by_department],
        },
        "by_category": {
            "labels": [r["gmp_category"] for r in by_category],
            "values": [r["total"] for r in by_category],
        },
        "by_month": {"labels": MONTH_LABELS, "values": by_month_counts},
        "score_trend": {"labels": MONTH_LABELS, "values": score_trend_values},
    }

    return {
        "total_ncs": total_ncs,
        "by_status": by_status,
        "top_locations": top_locations,
        "avg_days_to_close": avg_days_to_close,
        "overdue_count": overdue_count,
        "chart_data": chart_data,
    }


# ---------------------------------------------------------------------------
# Tab: Wyniki inspekcji (wynik % wg działu/zmiany/miesiąca + liczba NC wg kwartału/roku)
# ---------------------------------------------------------------------------

def _build_results_tab(base_nc_qs, scope, department, year):
    departments = _in_scope_departments(scope, department)
    inspections = list(
        Inspection.objects.filter(inspected_at__year=year).select_related("template")
    )
    by_dept_shift_month = defaultdict(lambda: defaultdict(list))
    for insp in inspections:
        dept = derive_department(insp.template.area_code, insp.area_detail)
        pct = insp.result_percent
        if pct is None:
            continue
        by_dept_shift_month[dept][(insp.shift, insp.inspected_at.month)].append(pct)

    results_by_department = []
    for dept in departments:
        shift_rows = []
        dept_values = []
        shifts_present = sorted({s for (s, _m) in by_dept_shift_month.get(dept, {}).keys()})
        ordered_shifts = [s for s in SHIFT_ORDER if s in shifts_present] + \
            [s for s in shifts_present if s not in SHIFT_ORDER]
        for shift in ordered_shifts:
            months = []
            row_values = []
            for m in range(1, 13):
                vals = by_dept_shift_month.get(dept, {}).get((shift, m), [])
                if vals:
                    avg = round(sum(vals) / len(vals), 1)
                    months.append(_score_cell(avg))
                    row_values.append(avg)
                    dept_values.append(avg)
                else:
                    months.append(_score_cell(None))
            year_avg = round(sum(row_values) / len(row_values), 1) if row_values else None
            shift_rows.append({"shift": shift, "months": months, "year_avg": _score_cell(year_avg)})

        department_avg = round(sum(dept_values) / len(dept_values), 1) if dept_values else None
        department_avg = _score_cell(department_avg)

        # Liczba niezgodności wg kwartału, porównanie lat
        nc_years = sorted(set(
            base_nc_qs.filter(department=dept).values_list("inspection_date__year", flat=True)
        ))
        quarter_rows = []
        for y in nc_years:
            q_counts = [0, 0, 0, 0]
            for d in base_nc_qs.filter(department=dept, inspection_date__year=y).only("inspection_date"):
                q_counts[_quarter_of(d.inspection_date.month) - 1] += 1
            quarter_rows.append({"year": y, "q": q_counts, "total": sum(q_counts)})

        results_by_department.append({
            "department": dept,
            "department_label": _dept_label(dept),
            "shift_rows": shift_rows,
            "department_avg": department_avg,
            "quarter_rows": quarter_rows,
            "has_score_data": bool(shift_rows),
            "has_quarter_data": bool(quarter_rows),
        })

    return {"results_by_department": results_by_department, "month_labels": MONTH_LABELS}


# ---------------------------------------------------------------------------
# Tab: Niezgodności wg grup (kategorii GMP/GHP) - kwartały + udział %
# ---------------------------------------------------------------------------

def _build_groups_tab(qs, scope, department, year):
    departments = _in_scope_departments(scope, department)
    groups_by_department = []

    for dept in departments:
        dept_qs = qs.filter(department=dept)
        rows_map = defaultdict(lambda: [0, 0, 0, 0])
        for nc in dept_qs.exclude(gmp_category="").only("gmp_category", "inspection_date"):
            rows_map[nc.gmp_category][_quarter_of(nc.inspection_date.month) - 1] += 1

        total_all = sum(sum(v) for v in rows_map.values())
        rows = []
        for category, q_counts in sorted(rows_map.items(), key=lambda kv: -sum(kv[1])):
            total = sum(q_counts)
            pct = round(100 * total / total_all, 1) if total_all else 0
            rows.append({"category": category, "q": q_counts, "total": total, "pct": pct})

        totals_row = {
            "q": [sum(r["q"][i] for r in rows) for i in range(4)],
            "total": total_all,
        }
        groups_by_department.append({
            "department": dept, "department_label": _dept_label(dept),
            "rows": rows, "totals_row": totals_row,
        })

    return {"groups_by_department": groups_by_department}


# ---------------------------------------------------------------------------
# Tab: Niezgodności wg punktów checklisty (ranking w ramach kategorii)
# ---------------------------------------------------------------------------

def _build_points_tab(qs, scope, department, year):
    departments = _in_scope_departments(scope, department)
    points_by_department = []

    for dept in departments:
        dept_qs = qs.filter(department=dept)
        cat_map = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
        point_desc = {}
        for nc in dept_qs.exclude(gmp_category="").only(
            "gmp_category", "checklist_point_label", "point_description", "inspection_date"
        ):
            key = nc.checklist_point_label or "brak punktu"
            cat_map[nc.gmp_category][key][_quarter_of(nc.inspection_date.month) - 1] += 1
            if key not in point_desc and nc.point_description:
                point_desc[key] = nc.point_description

        categories = []
        for category, points in sorted(
            cat_map.items(), key=lambda kv: -sum(sum(p) for p in kv[1].values())
        ):
            point_rows = []
            for label, q_counts in sorted(points.items(), key=lambda kv: -sum(kv[1])):
                point_rows.append({
                    "label": label,
                    "description": point_desc.get(label, ""),
                    "q": q_counts,
                    "total": sum(q_counts),
                })
            categories.append({
                "category": category,
                "points": point_rows,
                "category_total": sum(p["total"] for p in point_rows),
            })

        points_by_department.append({
            "department": dept, "department_label": _dept_label(dept), "categories": categories,
        })

    return {"points_by_department": points_by_department}
