from django.urls import path

from . import views

app_name = 'characters'

urlpatterns = [
    path('', views.character_work_list, name='character_work_list'),
    path('works/<int:work_id>/', views.character_list, name='character_list'),
    path('works/<int:work_id>/extract/', views.character_extract, name='character_extract'),
    path('works/<int:work_id>/new/', views.character_create, name='character_create'),
    path('works/<int:work_id>/<int:character_id>/', views.character_detail, name='character_detail'),
    path('works/<int:work_id>/<int:character_id>/edit/', views.character_update, name='character_update'),
    path('works/<int:work_id>/<int:character_id>/delete/', views.character_delete, name='character_delete'),
]
