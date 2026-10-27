"""
Jednorazowy import realnej treści checklist GMP/GHP z plików Excel
obowiązujących w zakładzie (folder Wytyczne/Templatki) do bazy danych.

Użycie:
    python manage.py import_checklists_from_xlsx

Czyta "czyste" (niewypełnione) wzory formularzy i tworzy z nich strukturę
ChecklistTemplate -> ChecklistSection -> ChecklistSubsection -> ChecklistItem.
Jeśli szablon dla danego area_code już istnieje, jest usuwany i tworzony od nowa
(nie powiedzie się, gdy ma zapisane inspekcje - wtedy użyj importu w aplikacji,
który zostawia stary szablon jako nieaktywny).
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from audits.checklist_import import ChecklistImportError, import_template
from audits.models import AreaCode

SOURCE_DIR = settings.BASE_DIR.parent / "Wytyczne" / "Templatki"

TEMPLATES = [
    {
        "area_code": AreaCode.WCE_WPP,
        "file": "GMP_GHP_WPP_WCE_FORM_12.01.2026.xlsx",
        "sheet": "GMP GHP_WCE_WPP",
    },
    {
        "area_code": AreaCode.MIX,
        "file": "GMP_GHP_MIX_12.01.2026.xlsx",
        "sheet": "MIX",
    },
    {
        "area_code": AreaCode.WLS,
        "file": "GMP_GHP_WLS_12.01.2026.xlsx",
        "sheet": "GMP GHP_WLS",
    },
    {
        "area_code": AreaCode.WED,
        "file": "GMP_WED_16.07.2026.xlsx",
        "sheet": "WED",
    },
]


class Command(BaseCommand):
    help = "Importuje strukturę checklist GMP/GHP z oryginalnych plików Excel do bazy danych."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-dir", default=None,
            help="Ścieżka do folderu z plikami xlsx (domyślnie ../Wytyczne/Templatki względem projektu).",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"]) if options["source_dir"] else SOURCE_DIR
        if not source_dir.exists():
            raise CommandError(f"Nie znaleziono folderu ze wzorami: {source_dir}")

        for cfg in TEMPLATES:
            path = source_dir / cfg["file"]
            if not path.exists():
                self.stderr.write(self.style.WARNING(f"Pominięto {cfg['area_code']}: brak pliku {path}"))
                continue
            try:
                template, items = import_template(
                    path, cfg["area_code"], sheet_name=cfg["sheet"], version_note=path.stem, existing="delete",
                )
            except ChecklistImportError as exc:
                raise CommandError(f"{path.name}: {exc}") from exc
            self.stdout.write(self.style.SUCCESS(
                f"Zaimportowano {cfg['area_code']}: {template.sections.count()} sekcji, {items} punktów z {path.name}"
            ))
