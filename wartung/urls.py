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
]
