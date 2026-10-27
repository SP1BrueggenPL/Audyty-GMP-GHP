from django.db import migrations

# Formularz "Inspekcja GMP/GHP - MIXOWANIE" (CD-00007385-1): 7 zakresów, 34 punkty, 25 pkt.
FORM = {
    "name": "Inspekcja GMP/GHP - MIXOWANIE",
    "document_code": "CD-00007385-1",
    "sections": [
        {
            "label": "I",
            "name": "Higiena - porządek",
            "max_points": 7,
            "subsections": [
                {
                    "number": "1",
                    "name": "Poprawność składowania (sprzęt do sprzątania, taśma, materiały/narzędzia w szafie, stretch, itp.)",
                    "items": [
                        {
                            "number": "1.1",
                            "description": "Ocena stanu szafy z materiałami/narzędziami"
                        },
                        {
                            "number": "1.2",
                            "description": "Stanowiska pracy i ich otoczenie (włączając stanowiska nieużywane podczas inspekcji); włączając zastawianie sprzętu ppoż."
                        }
                    ]
                },
                {
                    "number": "2",
                    "name": "FERT i materiały pakowaniowe",
                    "items": [
                        {
                            "number": "2.1",
                            "description": "Dostępny tylko FERT i materiały opakowanie w bieżącym miksowaniu"
                        },
                        {
                            "number": "2.2",
                            "description": "FERT i materiały opakowaniowe są umieszczone oznaczonych miejscach"
                        }
                    ]
                },
                {
                    "number": "3",
                    "name": "Magazynowanie pustych palet",
                    "items": [
                        {
                            "number": "3.1",
                            "description": "Palety przechowywane w miejscu do tego przeznaczonym"
                        },
                        {
                            "number": "3.2",
                            "description": "Palety zgodne odseparowane od palet uszkodzonych"
                        }
                    ]
                },
                {
                    "number": "4",
                    "name": "Drobne elementy infrastruktury i naprawy tymczasowe\n(ze szczegółnym uwzględnieniem rolek, po których jeżdża palety i inne elementy)",
                    "items": [
                        {
                            "number": "4.1",
                            "description": "Nie uszkodzone (dotyczy zwłaszcza rolek)"
                        },
                        {
                            "number": "4.2",
                            "description": "Kompletne (dotyczy zwłaszcza rolek)"
                        },
                        {
                            "number": "4.3",
                            "description": "Naprawy tynczasowe zgodne z zasadami i/lub zgłoszone w coswin"
                        }
                    ]
                }
            ]
        },
        {
            "label": "II",
            "name": "Higiena - czystość",
            "max_points": 7,
            "subsections": [
                {
                    "number": "1",
                    "name": "Pozostałości  FERT i opakowań",
                    "items": [
                        {
                            "number": "1.1",
                            "description": "Brak resztek surowców/półproduktów na podłodze"
                        },
                        {
                            "number": "1.2",
                            "description": "Brak resztek materiałów opakowaniowych na podłodze"
                        }
                    ]
                },
                {
                    "number": "2",
                    "name": "Czystość stanowisk pracy, drobnego sprzętu i otoczenia",
                    "items": [
                        {
                            "number": "2.1",
                            "description": "Szafa z materiałami/narzędziami - czysta, bez zabrudzeń"
                        },
                        {
                            "number": "2.2",
                            "description": "Stanowiska pracy i ich otoczenie (włączając stanowiska nieużywane podczas inspekcji i paleciaki)"
                        },
                        {
                            "number": "2.3",
                            "description": "Rolki - czyste"
                        },
                        {
                            "number": "2.4",
                            "description": "Panel sterowniczy/stanowisko komputerowe czyste"
                        }
                    ]
                },
                {
                    "number": "3",
                    "name": "Wycieki i zastoiny wody",
                    "items": [
                        {
                            "number": "3.1",
                            "description": "Brak stwierdzonych przecieków/wycieków i zastoin wody"
                        }
                    ]
                }
            ]
        },
        {
            "label": "III",
            "name": "Gospodarka odpadami i DDD",
            "max_points": 3,
            "subsections": [
                {
                    "number": "1",
                    "name": "Gospodarka odpadami  - składowanie",
                    "items": [
                        {
                            "number": "1.1",
                            "description": "Odpady prawidłowo oznakowane i przechowywane w odpowiednich, nieuszkodzonych pojemnikach, odpady przechowywane w wyznaczonych miejscach"
                        }
                    ]
                },
                {
                    "number": "2",
                    "name": "DDD",
                    "items": [
                        {
                            "number": "2.1",
                            "description": "Pułapki/ lampy owadobójcze  zainstalowane w odpowiednich miejscach, kompletne, nieuszkodzone"
                        },
                        {
                            "number": "2.2",
                            "description": "Brak potwierdzonej obecności owadów latających oraz szkodników biegających (odchody, pajęczyny, widoczne trasy przemieszczania się szkodników)"
                        },
                        {
                            "number": "2.3",
                            "description": "Brak stwierdzonych uszkodzeń elementów infrastruktury, mogących stanowić potencjalne miejsce bytowania szkodników (pęknięcia, ubytki w ścianach, posadzkach, sufitach)"
                        }
                    ]
                }
            ]
        },
        {
            "label": "IV",
            "name": "Znakowanie i składowanie",
            "max_points": 3,
            "subsections": [
                {
                    "number": "1",
                    "name": "Znakowanie",
                    "items": [
                        {
                            "number": "1.1",
                            "description": "FERT, etykieta, materiały opakowaniowe oznaczone w sposób prawidłowy, umożliwiający identyfikację"
                        }
                    ]
                },
                {
                    "number": "2",
                    "name": "Składowanie",
                    "items": [
                        {
                            "number": "2.1",
                            "description": "Wszystkie materiały (FERT, materiały opakowaniowe i pomocnicze) zamknięte/zabezpieczone i przechowywane na paletach (nie na podłodze) z czystą przekładką"
                        }
                    ]
                },
                {
                    "number": "3",
                    "name": "Przestrzeganie zasady FEFO",
                    "items": [
                        {
                            "number": "3.1",
                            "description": "Surowce wydawane/zużywane do produkcji zgodnie z FEFO (\"first expired, first out\")  - sprawdzić 1-2 FERT"
                        }
                    ]
                }
            ]
        },
        {
            "label": "V",
            "name": "Poprawność prowadzenia dokumentacji",
            "max_points": 2,
            "subsections": [
                {
                    "number": "1",
                    "name": "Zlecenie produkcyjne",
                    "items": [
                        {
                            "number": "1.1",
                            "description": "Czy mixowanie jest realizowane zgodnie z danymi na zleceniu? (ilość określonego FERT w mixie; opakowania i inne; poprawność uzupełnienia cheklisty miksowania);"
                        },
                        {
                            "number": "1.2",
                            "description": "INNE - np. niepoprawny formularz, niewłaściwa wersja dokumentu dostępna na linii"
                        }
                    ]
                },
                {
                    "number": "2",
                    "name": "Inna dokumentacja",
                    "items": [
                        {
                            "number": "2.1",
                            "description": "CZYSZCZENIE/SPRZĄTANIE - potwierdzenie codziennego sprzątania, czyszczenia rolek itp.\nchecklista czyszczenia codzienna  i/lub czy checklista sprzątania okresowego jest dostępna"
                        }
                    ]
                }
            ]
        },
        {
            "label": "VI",
            "name": "Higiena pracowników",
            "max_points": 2,
            "subsections": [
                {
                    "number": "1",
                    "name": "Przestrzeganie przez pracowników  oraz osoby wizytujące i firmy zewnętrzne obowiązujących zasad higieny",
                    "items": [
                        {
                            "number": "1.1",
                            "description": "Mycie i dezynfekcja rąk zgodnie z zasadami, czepek,  odzież ochronna, obuwie robocze noszone zgodnie z zasadami, brak noszonej biżuterii, zegarków, stosowanie perfum i kosmetyków zgodne z zasadami"
                        },
                        {
                            "number": "1.2",
                            "description": "Jedzenie i picie tylko w wyznaczonych pomieszczeniach socjalnych, brak używania naczyń ze szkła lub ceramiki, utrzymanie czystości w strefie socjalnej, przestrzeganie zakazu żucia gumy"
                        },
                        {
                            "number": "1.3",
                            "description": "Skaleczenia zabezpieczone zgodnie z zasadami (niebieskie plastry - jak pracownik ma plaster, sprawdź zapisy w karcie \"rozchody plastrów\" u KZZ)"
                        }
                    ]
                }
            ]
        },
        {
            "label": "VII",
            "name": "Ocena wiedzy pracowników",
            "max_points": 1,
            "subsections": [
                {
                    "number": "1",
                    "name": "Ocena wiedzy na podstawie rozmowy \n(rozmawiamy z 2-3 osobami; wpisujemy stanowisko osób, z którymi prowadzono rozmowę)",
                    "items": [
                        {
                            "number": "1.1",
                            "description": "Alergeny - wiedza dotycząca rodzaju alergenów występujących w zakładzie (w tym postępowanie w przypadku zabrudzenia rąk lub odzieży alergenem innym niż występujący w zakładzie produkcyjnym)"
                        },
                        {
                            "number": "1.2",
                            "description": "Postępowanie z wyrobem niezgodnym - sposób postępowania w przypadku zidentyfikowania niezgodności (np. niewłaściwa data czy użycie niewłaściwego materiału)"
                        },
                        {
                            "number": "1.3",
                            "description": "Food defence - co to jest \"ochrona żywności\"; w jaki sposób zapewniamy bezpieczeństwo produktu"
                        },
                        {
                            "number": "1.4",
                            "description": "Kultura Bezpieczeństwa Żywności (FSC) - pojęcie bardzo szerokie, pytania o działania mające na celu budowanie FSC"
                        }
                    ]
                },
                {
                    "number": "2",
                    "name": "Ocena wiedzy na podstawie obserwacji podczas inspekcji",
                    "items": [
                        {
                            "number": "2.1",
                            "description": "Higiena pracowników"
                        }
                    ]
                }
            ]
        }
    ]
}


def create_mix_form(apps, schema_editor):
    """Tworzy formularz MIX (jeśli jeszcze go nie ma), żeby był dostępny od razu po wdrożeniu."""
    Template = apps.get_model("audits", "ChecklistTemplate")
    Section = apps.get_model("audits", "ChecklistSection")
    Subsection = apps.get_model("audits", "ChecklistSubsection")
    Item = apps.get_model("audits", "ChecklistItem")

    if Template.objects.filter(area_code="MIX", document_code=FORM["document_code"]).exists():
        return
    Template.objects.filter(area_code="MIX").update(is_active=False)
    template = Template.objects.create(
        area_code="MIX", name=FORM["name"], document_code=FORM["document_code"],
        version_note="GMP_GHP_MIX_12.01.2026", is_active=True,
    )
    for s_order, sec in enumerate(FORM["sections"], start=1):
        section = Section.objects.create(
            template=template, order=s_order, label=sec["label"], name=sec["name"], max_points=sec["max_points"],
        )
        for sub_order, sub in enumerate(sec["subsections"], start=1):
            subsection = Subsection.objects.create(
                section=section, order=sub_order, number=sub["number"], name=sub["name"],
            )
            for item_order, item in enumerate(sub["items"], start=1):
                Item.objects.create(
                    subsection=subsection, order=item_order, number=item["number"], description=item["description"],
                )


class Migration(migrations.Migration):

    dependencies = [
        ('audits', '0012_inspection_extra_penalty'),
    ]

    operations = [
        migrations.RunPython(create_mix_form, migrations.RunPython.noop),
    ]
