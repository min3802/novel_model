from django.urls import path

from . import views

app_name = "visuals"

urlpatterns = [
    path("works/<int:work_id>/covers/", views.cover_collection, name="cover_collection"),
    path("covers/<int:image_id>/", views.cover_delete, name="cover_delete"),
    path("works/<int:work_id>/relations/extract/", views.relation_extract, name="relation_extract"),
    path("works/<int:work_id>/relations/", views.relation_map_collection, name="relation_map_collection"),
    path("relations/<int:relation_map_id>/", views.relation_map_detail, name="relation_map_detail"),
    path("relations/<int:relation_map_id>/html/", views.relation_map_html, name="relation_map_html"),
    path("relations/<int:relation_map_id>/pdf/", views.relation_map_pdf, name="relation_map_pdf"),
]

