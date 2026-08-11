from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import UserForm
from .models import Role, User

CODE_LENGTH = 6
SESSION_KEY = "pending_chip_user"


def chip_login(request):
    """Logowanie dwuetapowe: numer chipa, a potem 6-znakowy kod autoryzujący.

    Pierwsze logowanie na danym chipie (albo po resecie kodu przez admina) -
    konto nie ma jeszcze ustawionego hasła (`has_usable_password() == False`),
    więc zamiast prosić o kod, pozwalamy go ustawić. Od tego momentu logowanie
    to zwykłe username+password (numer chipa + kod) przez ModelBackend.
    """
    if request.user.is_authenticated:
        return redirect("dashboard")

    next_url = request.POST.get("next") or request.GET.get("next", "")
    target_user = None
    pending_username = request.session.get(SESSION_KEY)
    if pending_username:
        target_user = User.objects.filter(username=pending_username, is_active=True).first()
        if not target_user:
            request.session.pop(SESSION_KEY, None)

    if request.method == "POST":
        if request.POST.get("cancel"):
            request.session.pop(SESSION_KEY, None)
            target_user = None

        elif "chip_code" in request.POST:
            chip_code = request.POST.get("chip_code", "").strip()
            user = User.objects.filter(username=chip_code, is_active=True).first()
            if user is None:
                messages.error(request, "Nierozpoznany chip. Zeskanuj ponownie lub zgłoś się do administratora.")
            else:
                request.session[SESSION_KEY] = user.username
                target_user = user

        elif "new_code" in request.POST and target_user:
            if target_user.has_usable_password():
                messages.error(request, "Ten chip ma już ustawiony kod. Wpisz go, aby się zalogować.")
            else:
                code = request.POST.get("new_code", "")
                confirm = request.POST.get("new_code_confirm", "")
                if len(code) != CODE_LENGTH:
                    messages.error(request, f"Kod musi mieć dokładnie {CODE_LENGTH} znaków.")
                elif code != confirm:
                    messages.error(request, "Podane kody nie są identyczne.")
                else:
                    target_user.set_password(code)
                    target_user.save()
                    authed = authenticate(request, username=target_user.username, password=code)
                    if authed is not None:
                        request.session.pop(SESSION_KEY, None)
                        login(request, authed)
                        messages.success(request, "Kod ustawiony. Od teraz loguj się chipem i tym kodem.")
                        return redirect(next_url or "dashboard")
                    messages.error(request, "Coś poszło nie tak przy zapisie kodu. Spróbuj ponownie.")

        elif "auth_code" in request.POST and target_user:
            code = request.POST.get("auth_code", "")
            authed = authenticate(request, username=target_user.username, password=code)
            if authed is not None:
                request.session.pop(SESSION_KEY, None)
                login(request, authed)
                return redirect(next_url or "dashboard")
            messages.error(request, "Niepoprawny kod. Spróbuj ponownie lub poproś administratora o reset kodu.")

    if target_user is None:
        step = "chip"
    elif target_user.has_usable_password():
        step = "enter_code"
    else:
        step = "set_code"

    return render(request, "registration/chip_login.html", {
        "step": step,
        "next": next_url,
        "chip_display": target_user.username if target_user else "",
        "code_length": CODE_LENGTH,
    })


def _require_admin(request):
    if request.user.is_admin_role:
        return True
    messages.error(request, "Tylko administrator może zarządzać użytkownikami.")
    return False


def _manageable_users():
    """Konta zarządzane z tego ekranu - z wyłączeniem superużytkowników
    (tych zarządza się w panelu Django /admin/). QualityAdmin i Helpdesk
    są tu widoczne i edytowalne jak każda inna rola."""
    return User.objects.exclude(is_superuser=True)


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
    if user_obj.is_superuser:
        messages.error(request, "Konta superużytkowników zarządzane są w panelu /admin/.")
        return redirect("user_list")

    if request.method == "POST":
        form = UserForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Zapisano zmiany dla {user_obj}.")
            return redirect("user_list")
    else:
        form = UserForm(instance=user_obj)

    return render(request, "accounts/user_form.html", {
        "form": form, "is_new": False, "user_obj": user_obj,
        "code_is_set": user_obj.has_usable_password(),
    })


@require_POST
@login_required
def user_delete(request, pk):
    if not _require_admin(request):
        return redirect("dashboard")

    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.is_superuser:
        messages.error(request, "Konta superużytkowników zarządzane są w panelu /admin/.")
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


@require_POST
@login_required
def user_reset_code(request, pk):
    if not _require_admin(request):
        return redirect("dashboard")

    user_obj = get_object_or_404(User, pk=pk)
    if user_obj.is_superuser:
        messages.error(request, "Konta superużytkowników zarządzane są w panelu /admin/.")
        return redirect("user_list")

    user_obj.set_unusable_password()
    user_obj.save()
    messages.success(
        request,
        f"Kod dla {user_obj} został zresetowany. Przy następnym logowaniu ta osoba ustawi nowy kod.",
    )
    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("user_edit", pk=pk)
