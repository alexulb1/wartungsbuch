"""Django-Admin als Pflegeoberflaeche (SPEC 9)."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Aufgabe,
    Benutzer,
    Bereich,
    BereichsTyp,
    Ereignis,
    Objekt,
    ObjektTyp,
    Taetigkeit,
)

admin.site.site_header = _("Wartungsbuch")
admin.site.site_title = _("Wartungsbuch")
admin.site.index_title = _("Verwaltung")


@admin.register(Benutzer)
class BenutzerAdmin(admin.ModelAdmin):
    list_display = ["email", "name", "sprache", "is_active", "is_staff"]
    list_filter = ["sprache", "is_active", "is_staff"]
    search_fields = ["email", "name"]
    ordering = ["email"]
    # Kein Passwortfeld: Die Anmeldung laeuft ueber Magic Link (SPEC 2).
    fields = ["email", "name", "sprache", "is_active", "is_staff", "is_superuser", "groups"]
    filter_horizontal = ["groups"]


class KatalogAdmin(admin.ModelAdmin):
    list_display = ["name_de", "name_en", "name_sv", "schluessel", "sortierung"]
    search_fields = ["name_de", "name_en", "name_sv", "schluessel"]
    prepopulated_fields = {"schluessel": ("name_de",)}
    ordering = ["sortierung", "name_de"]


@admin.register(ObjektTyp)
class ObjektTypAdmin(KatalogAdmin):
    pass


@admin.register(BereichsTyp)
class BereichsTypAdmin(KatalogAdmin):
    pass


@admin.register(Taetigkeit)
class TaetigkeitAdmin(KatalogAdmin):
    list_display = [
        "name_de",
        "name_en",
        "name_sv",
        "standard_intervall_wert",
        "standard_intervall_einheit",
        "standard_modus",
    ]
    filter_horizontal = ["bereichs_typen"]
    fieldsets = [
        (None, {"fields": ["schluessel", "sortierung", "bereichs_typen"]}),
        (_("Bezeichnung"), {"fields": ["name_de", "name_en", "name_sv"]}),
        (_("Hinweis"), {"fields": ["hinweis_de", "hinweis_en", "hinweis_sv"]}),
        (
            _("Übliches Intervall"),
            {
                "fields": [
                    "standard_intervall_wert",
                    "standard_intervall_einheit",
                    "standard_modus",
                    "standard_kalender_monat",
                ]
            },
        ),
    ]


class BereichInline(admin.TabularInline):
    model = Bereich
    extra = 0
    fields = ["typ", "bezeichnung", "notiz"]


@admin.register(Objekt)
class ObjektAdmin(admin.ModelAdmin):
    list_display = ["name", "typ", "ruhezeit"]
    list_filter = ["typ"]
    search_fields = ["name"]
    inlines = [BereichInline]

    @admin.display(description=_("Ruhezeit"))
    def ruhezeit(self, objekt):
        if not objekt.hat_ruhezeit:
            return _("ganzjährig")
        return f"{objekt.aktiv_ab_monat}–{objekt.aktiv_bis_monat}"


class AufgabeInline(admin.TabularInline):
    model = Aufgabe
    extra = 0
    autocomplete_fields = ["taetigkeit"]
    fields = [
        "taetigkeit",
        "intervall_wert",
        "intervall_einheit",
        "modus",
        "kalender_monat",
        "kalender_tag",
        "aktiv",
    ]


@admin.register(Bereich)
class BereichAdmin(admin.ModelAdmin):
    list_display = ["__str__", "objekt", "typ"]
    list_filter = ["objekt", "typ"]
    search_fields = ["bezeichnung", "objekt__name", "typ__name_de"]
    autocomplete_fields = ["objekt", "typ"]
    inlines = [AufgabeInline]


@admin.register(Aufgabe)
class AufgabeAdmin(admin.ModelAdmin):
    list_display = ["taetigkeit", "bereich", "intervall_wert", "intervall_einheit", "modus", "aktiv"]
    list_filter = ["aktiv", "modus", "bereich__objekt", "intervall_einheit"]
    search_fields = ["taetigkeit__name_de", "bereich__bezeichnung", "bereich__objekt__name"]
    autocomplete_fields = ["bereich", "taetigkeit"]


@admin.register(Ereignis)
class EreignisAdmin(admin.ModelAdmin):
    list_display = ["datum", "bezeichnung", "bereich", "kosten", "ausgefuehrt_von", "erfasst_von"]
    list_filter = ["bereich__objekt", "datum", "taetigkeit"]
    search_fields = ["beschreibung", "notiz", "ausgefuehrt_von", "taetigkeit__name_de"]
    date_hierarchy = "datum"
    autocomplete_fields = ["bereich", "aufgabe", "taetigkeit"]
    readonly_fields = ["erfasst_am"]
    fieldsets = [
        (None, {"fields": ["bereich", "aufgabe", "taetigkeit", "beschreibung", "datum"]}),
        (_("Details"), {"fields": ["kosten", "ausgefuehrt_von", "notiz"]}),
        (_("Erfassung"), {"fields": ["erfasst_von", "erfasst_am"]}),
    ]

    def save_model(self, request, obj, form, change):
        if not obj.erfasst_von_id:
            obj.erfasst_von = request.user
        super().save_model(request, obj, form, change)
