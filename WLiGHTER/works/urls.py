from django.urls import path

from . import views

app_name = 'works'

urlpatterns = [
    path('', views.work_list, name='work_list'),
    path('new/', views.work_create, name='work_create'),
    path('<int:work_id>/', views.work_detail, name='work_detail'),
    path('<int:work_id>/edit/', views.work_update, name='work_update'),
    path('<int:work_id>/delete/', views.work_delete, name='work_delete'),

    path('<int:work_id>/episodes/', views.episode_list, name='episode_list'),
    path('<int:work_id>/episodes/new/', views.episode_create, name='episode_create'),
    path('<int:work_id>/episodes/<int:episode_id>/', views.episode_detail, name='episode_detail'),
    path('<int:work_id>/episodes/<int:episode_id>/edit/', views.episode_update, name='episode_update'),
    path('<int:work_id>/episodes/<int:episode_id>/delete/', views.episode_delete, name='episode_delete'),
]
