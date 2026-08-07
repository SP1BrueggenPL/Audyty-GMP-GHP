from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import UserForm
from .models import Role, User


def chip_login(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        chip_code = request.POST.get("chip_code", "").strip()
        user = authenticate(request, chip_code=chip_code)
        if user is not None:
            login(request, user)
            return redirect(request.POST.get("next") or "dashboard")
        messages.error(request, "Nierozpoznany chip. Zeskanuj ponownie lub zgłoś się do administratora.")

    return render(request, "registration/chip_login.html", {"next": request.GET.get("next", "")})


def _require_admin(request):
    if request.user.is_admin_role:
        return True
    messages.error(request, "Tylko administrator może zarządzać użytkownikami.")
    return False


def _manageable_users():
    """Konta pracownicze zarządzane z tego ekranu - z wyłączeniem administratorów/
    superużytkowników, których hasła są zarządzane w panelu /admin/."""
    return User.objects.exclude(is_superuser=True).exclude(role=Role.ADMIN)


@login_required
def user_list(request):
    if not _require_admin(request):
        return redirect("dashboard")

    users = _manageable_users().order_by("role", "last_name", "first_name")
    role_filter = request.GET.get("role", "")
    if role_filter:
        users = users.filter(role=role_filter)

    return render(request, "accounts/user_list.html", {
        "users": users,
        "role_choices": Role.choices,
        "current_role": role_filter,
    })


@login_required
def user_new(request):
    if not _require_admin(request):
        return redirect("dashboard")

    if request.method == "POST":
        form = UserForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            messages.success(request, f"Użytkownik {new_user} został utworzony.")
            return redirect("user_list")
    else:
        form = UserForm()

    return render(request, "accounts/user_form.html", {"form": form, "is_new": True})


@login_required
def user_edit(request, pk):
    if not _require_admin(request):
        return redirect("dashboard")

    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.is_superuser or user_obj.role == Role.ADMIN:
        messages.error(request, "Konta administratorów zarządzane są w panelu /admin/.")
        return redirect("user_list")

    if request.method == "POST":
        form = UserForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Zapisano zmiany dla {user_obj}.")
            return redirect("user_list")
    else:
        form = UserForm(instance=user_obj)

    return render(request, "accounts/user_form.html", {"form": form, "is_new": False, "user_obj": user_obj})


@require_POST
@login_required
def user_delete(request, pk):
    if not _require_admin(request):
        return redirect("dashboard")

    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.is_superuser or user_obj.role == Role.ADMIN:
        messages.error(request, "Konta administratorów zarządzane są w panelu /admin/.")
        return redirect("user_list")

    label = str(user_obj)
    try:
        user_obj.delete()
        messages.success(request, f"Użytkownik {label} został usunięty.")
    except ProtectedError:
        messages.error(
            request,
            f"Nie można usunąć {label} - ma powiązane inspekcje lub niezgodności w systemie. "
            "Odznacz „Konto aktywne”, jeśli chcesz je dezaktywować bez usuwania historii.",
        )
        return redirect("user_edit", pk=pk)

    return redirect("user_list")
