from django.urls import path

from . import views

urlpatterns = [
    path("uzytkownicy/", views.user_list, name="user_list"),
    path("uzytkownicy/nowy/", views.user_new, name="user_new"),
    path("uzytkownicy/<int:pk>/edytuj/", views.user_edit, name="user_edit"),
    path("uzytkownicy/<int:pk>/usun/", views.user_delete, name="user_delete"),
]
