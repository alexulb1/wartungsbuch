"""Formulare der Oberflaeche."""

import uuid

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


class MehrfachDateiEingabe(forms.ClearableFileInput):
    allow_multiple_selected = True


class MehrfachDateiFeld(forms.FileField):
    """Django nimmt je Feld nur eine Datei entgegen; das hier ist das in der
    Django-Dokumentation beschriebene Muster für Mehrfachauswahl."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MehrfachDateiEingabe(attrs={"multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        einzeln = super().clean
        if isinstance(data, (list, tuple)):
            return [einzeln(d, initial) for d in data if d]
        return [einzeln(data, initial)] if data else []


def _anhangfeld():
    return MehrfachDateiFeld(
        label=_("Fotos oder Belege"),
        required=False,
        help_text=_("Bilder und PDF, höchstens 25 MB je Datei."),
    )


def _absendekennung():
    """Einmal-Kennung je angezeigtem Formular, gegen doppeltes Absenden
    (einmalig.py). Das initial ist aufrufbar, also bei jeder Anzeige neu."""
    return forms.UUIDField(required=False, widget=forms.HiddenInput, initial=uuid.uuid4)


def _geprueft(dateien):
    from .dateipruefung import pruefe_datei

    for datei in dateien or []:
        pruefe_datei(datei)
    return dateien or []


class ErledigenForm(forms.ModelForm):
    """Abhaken einer faelligen Aufgabe.

    Das Datum ist frei waehlbar und mit dem Stichtag vorbelegt -- Dokumentation
    hinkt der Arbeit nach (SPEC 4).
    """

    anhaenge = _anhangfeld()
    absendekennung = _absendekennung()

    def __init__(self, *args, mit_anhaengen=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not mit_anhaengen:
            # Die Abhak-Seite aus der Wochenmail benutzt dasselbe Formular,
            # dort ist niemand angemeldet. Ein Datei-Upload wäre unangemeldeter
            # Schreibzugriff auf den Speicher -- das Feld muss weg, nicht nur
            # unbeachtet bleiben.
            self.fields.pop("anhaenge")

    def clean_anhaenge(self):
        return _geprueft(self.cleaned_data.get("anhaenge"))

    class Meta:
        model = Ereignis
        fields = ["datum", "kosten", "ausgefuehrt_von", "notiz"]
        widgets = {"datum": DatumsFeld(), "notiz": forms.Textarea(attrs={"rows": 3})}


class EreignisForm(forms.ModelForm):
    """Ein Vorgang ohne wiederkehrende Aufgabe -- etwa eine Renovierung."""

    anhaenge = _anhangfeld()
    absendekennung = _absendekennung()

    def clean_anhaenge(self):
        return _geprueft(self.cleaned_data.get("anhaenge"))

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


class UnterlageForm(forms.Form):
    """Anhänge nachtragen -- als Unterlage zum Bauteil."""

    beschriftung = forms.CharField(
        label=_("Beschriftung"),
        max_length=200,
        required=False,
        help_text=_('Etwa "Typenschild" oder "Bedienungsanleitung".'),
    )
    anhaenge = _anhangfeld()

    def clean_anhaenge(self):
        dateien = _geprueft(self.cleaned_data.get("anhaenge"))
        if not dateien:
            raise forms.ValidationError(_("Bitte mindestens eine Datei auswählen."))
        return dateien
