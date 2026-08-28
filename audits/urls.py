from django.urls import path

from . import checklist_admin, reports_export, reports_views, views

urlpatterns = [
    path("panel/", views.dashboard, name="dashboard"),
    path("inspekcje/", views.inspection_list, name="inspection_list"),
    path("inspekcje/nowa/", views.inspection_type_select, name="inspection_type_select"),
    path("inspekcje/nowa/<int:template_id>/", views.inspection_new, name="inspection_new"),
    path("inspekcje/<int:pk>/", views.inspection_detail, name="inspection_detail"),
    path("inspekcje/<int:pk>/edytuj/", views.inspection_edit, name="inspection_edit"),
    path("inspekcje/<int:pk>/usun/", views.inspection_delete, name="inspection_delete"),
    path("inspekcje/<int:pk>/raport/", views.inspection_report, name="inspection_report"),
    path("inspekcje/<int:pk>/raport/pdf/", views.inspection_report_pdf, name="inspection_report_pdf"),
    path("niezgodnosci/", views.nonconformity_list, name="nonconformity_list"),
    path("niezgodnosci/nowa/", views.nonconformity_new, name="nonconformity_new"),
    path("niezgodnosci/<int:pk>/", views.nonconformity_detail, name="nonconformity_detail"),
    path("niezgodnosci/<int:pk>/usun/", views.nonconformity_delete, name="nonconformity_delete"),
    path("raporty/", reports_views.reports_dashboard, name="reports_dashboard"),
    path("raporty/eksport/", reports_export.reports_export, name="reports_export"),
    path("api/osoby-ze-zmiany/", views.users_by_shift, name="users_by_shift"),
    path("api/podpowiedz-niezgodnosc/", views.suggest_nonconformity, name="suggest_nonconformity"),
    path("api/podpowiedz-podsumowanie/", views.suggest_inspection_summary_view, name="suggest_inspection_summary"),
    path("checklisty/<int:pk>/", checklist_admin.checklist_template_edit, name="checklist_template_edit"),
    path("checklisty/sekcja/<int:pk>/", checklist_admin.checklist_section_edit, name="checklist_section_edit"),
    path("checklisty/podsekcja/<int:pk>/", checklist_admin.checklist_subsection_edit, name="checklist_subsection_edit"),
]
