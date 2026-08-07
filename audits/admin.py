from django.contrib import admin

from .models import (
    ChecklistItem,
    ChecklistSection,
    ChecklistSubsection,
    ChecklistTemplate,
    Inspection,
    InspectionItemResult,
    InspectionSectionResult,
    NonConformity,
    NonConformityPhoto,
)


class ChecklistSectionInline(admin.TabularInline):
    model = ChecklistSection
    extra = 0
    fields = ("order", "label", "name", "max_points")


@admin.register(ChecklistTemplate)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "area_code", "document_code", "version_note", "is_active", "max_points_total")
    list_filter = ("area_code", "is_active")
    inlines = [ChecklistSectionInline]


class ChecklistSubsectionInline(admin.TabularInline):
    model = ChecklistSubsection
    extra = 0


@admin.register(ChecklistSection)
class ChecklistSectionAdmin(admin.ModelAdmin):
    list_display = ("template", "order", "label", "name", "max_points")
    list_filter = ("template",)
    inlines = [ChecklistSubsectionInline]


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0


@admin.register(ChecklistSubsection)
class ChecklistSubsectionAdmin(admin.ModelAdmin):
    list_display = ("section", "order", "number", "name")
    list_filter = ("section__template", "section")
    inlines = [ChecklistItemInline]


@admin.register(ChecklistItem)
class ChecklistItemAdmin(admin.ModelAdmin):
    list_display = ("subsection", "order", "number", "description")
    list_filter = ("subsection__section__template",)
    search_fields = ("number", "description")


class InspectionSectionResultInline(admin.TabularInline):
    model = InspectionSectionResult
    extra = 0


class InspectionItemResultInline(admin.TabularInline):
    model = InspectionItemResult
    extra = 0


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "template", "inspector", "shift", "status", "result_percent", "nonconformity_count")
    list_filter = ("template__area_code", "status", "shift")
    search_fields = ("area_detail", "area_representatives")
    inlines = [InspectionSectionResultInline]
    readonly_fields = ("created_at", "updated_at")


class NonConformityPhotoInline(admin.TabularInline):
    model = NonConformityPhoto
    extra = 0


@admin.register(NonConformity)
class NonConformityAdmin(admin.ModelAdmin):
    list_display = (
        "number", "department", "inspection_date", "inspector", "responsible_person",
        "status", "is_responsible_part_filled", "days_open",
    )
    list_filter = ("department", "status", "shift", "inspector")
    search_fields = ("number", "description", "location_detail", "area_representative")
    date_hierarchy = "inspection_date"
    inlines = [NonConformityPhotoInline]
    readonly_fields = ("number", "entry_date", "created_at", "updated_at")
