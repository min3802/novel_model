from django.urls import path
from . import views

app_name = 'guides'

urlpatterns = [
    path('', views.index, name='index'),
    path('new/', views.guide_create, name='guide_create'),
    path('<int:guide_id>/', views.guide_detail, name='guide_detail'),
    path('<int:guide_id>/download/', views.guide_download, name='guide_download'),
    path('<int:guide_id>/delete/', views.guide_delete, name='guide_delete'),
]
