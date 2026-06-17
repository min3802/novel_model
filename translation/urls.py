from django.urls import path
from . import views

app_name = 'translation'

urlpatterns = [
    path('', views.index, name='index'),
    path('episodes/<int:episode_id>/run/', views.translation_run, name='translation_run'),
    path('results/<int:translation_id>/chat/', views.review_chatbot, name='review_chatbot'),
    path('episodes/<int:episode_id>/results/', views.translation_version_list, name='translation_version_list'),
    path('results/<int:translation_id>/delete/', views.translation_version_delete, name='translation_version_delete'),
]
