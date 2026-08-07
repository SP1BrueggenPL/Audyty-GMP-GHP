"""
Automatyczne przypomnienia i eskalacje dla niezgodności GMP/GHP.

Zastępuje ręczne "przypominanie i przypominanie" mailowe opisane w procesie:
- po NC_REMINDER_AFTER_DAYS dniach bez uzupełnienia przyczyny/działań ->
  przypomnienie do osoby odpowiedzialnej za obszar (powtarzane co
  NC_REMINDER_REPEAT_DAYS dni, żeby nie zalewać skrzynki codziennie),
- po NC_ESCALATION_AFTER_DAYS dniach -> jednorazowa eskalacja do osób
  z flagą receives_escalations=True (dyrekcja) oraz do audytora.

Do uruchamiania codziennie z harmonogramu (Harmonogram zadań Windows / cron):
    python manage.py send_nc_reminders
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from audits.models import NCStatus, NonConformity

User = get_user_model()

REPEAT_DAYS = getattr(settings, "NC_REMINDER_REPEAT_DAYS", 3)


class Command(BaseCommand):
    help = "Wysyła przypomnienia do osób odpowiedzialnych i eskalacje do dyrekcji dla przeterminowanych niezgodności."

    def handle(self, *args, **options):
        now = timezone.now()
        open_ncs = NonConformity.objects.filter(status=NCStatus.W_TOKU).exclude(responsible_person__isnull=True)

        reminded, escalated = 0, 0

        for nc in open_ncs:
            if nc.is_responsible_part_filled:
                continue

            if nc.is_due_for_escalation:
                self.send_escalation(nc, now)
                escalated += 1
                continue

            if nc.is_due_for_reminder:
                if nc.last_reminder_sent_at and (now - nc.last_reminder_sent_at).days < REPEAT_DAYS:
                    continue
                self.send_reminder(nc, now)
                reminded += 1

        self.stdout.write(self.style.SUCCESS(f"Przypomnienia: {reminded}, eskalacje: {escalated}"))

    def send_reminder(self, nc, now):
        if not nc.responsible_person or not nc.responsible_person.email:
            return
        body = render_to_string("audits/email_nc_reminder.txt", {"nc": nc})
        send_mail(
            subject=f"[Przypomnienie] Niezgodność {nc.number} czeka na Twoje działania",
            message=body,
            from_email=None,
            recipient_list=[nc.responsible_person.email],
            fail_silently=True,
        )
        nc.reminder_count += 1
        nc.last_reminder_sent_at = now
        nc.save(update_fields=["reminder_count", "last_reminder_sent_at"])

    def send_escalation(self, nc, now):
        recipients = list(
            User.objects.filter(receives_escalations=True).exclude(email="").values_list("email", flat=True)
        )
        if nc.inspector and nc.inspector.email:
            recipients.append(nc.inspector.email)
        if not recipients:
            return
        body = render_to_string("audits/email_nc_escalation.txt", {"nc": nc})
        send_mail(
            subject=f"[Eskalacja] Niezgodność {nc.number} przeterminowana o ponad {settings.NC_ESCALATION_AFTER_DAYS} dni",
            message=body,
            from_email=None,
            recipient_list=list(set(recipients)),
            fail_silently=True,
        )
        nc.escalated_at = now
        nc.save(update_fields=["escalated_at"])
