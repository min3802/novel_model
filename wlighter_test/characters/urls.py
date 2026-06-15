from django.urls import path

from . import views

app_name = "characters"

urlpatterns = [
    path("works/<int:work_id>/", views.character_collection, name="character_collection"),
    path("works/<int:work_id>/extract/", views.character_extract, name="character_extract"),
    path("<int:character_id>/", views.character_detail, name="character_detail"),
]

