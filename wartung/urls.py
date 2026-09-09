from django.urls import path

from . import views

app_name = "wartung"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("bereich/<int:pk>/", views.bereich, name="bereich"),
    path("bereich/<int:pk>/aufgaben/", views.aufgaben_ergaenzen, name="aufgaben_ergaenzen"),
    path("bereich/<int:pk>/ereignis/", views.ereignis_neu, name="ereignis_neu"),
    path("aufgabe/<int:pk>/erledigen/", views.erledigen, name="erledigen"),
    path("profil/", views.profil, name="profil"),
    path("anmelden/", views.anmelden, name="anmelden"),
    path("anmelden/<str:marke>/", views.anmelden_mit_marke, name="anmelden_mit_marke"),
    path("abmelden/", views.abmelden, name="abmelden"),
    path("erledigt/<str:marke>/", views.erledigt_mit_marke, name="erledigt_mit_marke"),
    path("kalender/<str:schluessel>.ics", views.kalender, name="kalender"),
    path("export.csv", views.export_csv, name="export_csv"),
    path("anhang/<uuid:kennung>/", views.anhang, name="anhang"),
    path("anhang/<uuid:kennung>/vorschau/", views.anhang_vorschau, name="anhang_vorschau"),
    path("gesund", views.lebenszeichen, name="lebenszeichen"),
]
