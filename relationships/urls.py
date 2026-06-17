from django.urls import path
from . import views

app_name = 'relationships'

urlpatterns = [
    path('', views.index, name='index'),
    path('new/', views.relation_create, name='relation_create'),
    path('<int:map_id>/', views.relation_detail, name='relation_detail'),
    path('<int:map_id>/download/', views.relation_download, name='relation_download'),
    path('<int:map_id>/delete/', views.relation_delete, name='relation_delete'),
]
