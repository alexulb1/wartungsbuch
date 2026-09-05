"""Formulare der Oberflaeche."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Benutzer, Ereignis


class DatumsFeld(forms.DateInput):
    """HTML5-Datumsfeld. Das value-Attribut muss ISO tragen, sonst zeigt der
    Browser ein leeres Feld -- unabhaengig von der Anzeigesprache."""

    input_type = "date"

    def __init__(self, attrs=None):
        # Das Format gehoert in den Konstruktor -- ein Klassenattribut wird
        # von DateInput.__init__ ueberschrieben, und das Feld bliebe im
        # Browser leer.
        super().__init__(attrs=attrs, format="%Y-%m-%d")


class ErledigenForm(forms.ModelForm):
    """Abhaken einer faelligen Aufgabe.

    Das Datum ist frei waehlbar und mit dem Stichtag vorbelegt -- Dokumentation
    hinkt der Arbeit nach (SPEC 4).
    """

    class Meta:
        model = Ereignis
        fields = ["datum", "kosten", "ausgefuehrt_von", "notiz"]
        widgets = {"datum": DatumsFeld(), "notiz": forms.Textarea(attrs={"rows": 3})}


class EreignisForm(forms.ModelForm):
    """Ein Vorgang ohne wiederkehrende Aufgabe -- etwa eine Renovierung."""

    class Meta:
        model = Ereignis
        fields = ["datum", "taetigkeit", "beschreibung", "kosten", "ausgefuehrt_von", "notiz"]
        widgets = {"datum": DatumsFeld(), "notiz": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, bereich=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.bereich = bereich
        if bereich is not None:
            self.fields["taetigkeit"].queryset = bereich.typ.taetigkeiten.all()
        self.fields["taetigkeit"].required = False
        self.fields["taetigkeit"].empty_label = _("— keine, freie Beschreibung —")

    def clean(self):
        daten = super().clean()
        if not daten.get("taetigkeit") and not (daten.get("beschreibung") or "").strip():
            raise forms.ValidationError(
                _("Bitte eine Tätigkeit wählen oder beschreiben, was gemacht wurde.")
            )
        return daten


class ProfilForm(forms.ModelForm):
    class Meta:
        model = Benutzer
        fields = ["name", "sprache"]


class AnmeldeForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail-Adresse"))
