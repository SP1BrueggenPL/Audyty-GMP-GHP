from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class BruggenUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Audyty GMP/GHP", {"fields": ("role", "department", "shift", "phone", "receives_escalations")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Audyty GMP/GHP", {"fields": ("role", "department", "shift", "phone", "receives_escalations")}),
    )
    list_display = ("username", "first_name", "last_name", "role", "department", "shift", "is_active")
    list_filter = ("role", "department", "shift", "is_active")
    search_fields = ("username", "first_name", "last_name")
