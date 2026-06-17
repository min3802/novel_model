from django.urls import path

from . import views

app_name = 'covers'

urlpatterns = [
    path('', views.cover_work_list, name='cover_work_list'),
    path('works/<int:work_id>/covers/', views.cover_list, name='cover_list'),
    path('works/<int:work_id>/covers/new/', views.cover_create, name='cover_create'),
    path('works/<int:work_id>/covers/<int:image_id>/', views.cover_detail, name='cover_detail'),
    path('works/<int:work_id>/covers/<int:image_id>/delete/', views.cover_delete, name='cover_delete'),
]
