from django.urls import path
from . import views

app_name = 'relationships'

urlpatterns = [
    path('', views.relation_work_list, name='relation_work_list'),
    path('works/<int:work_id>/', views.relation_list, name='relation_list'),
    path('works/<int:work_id>/new/', views.relation_create, name='relation_create'),
    path('works/<int:work_id>/<int:map_id>/', views.relation_detail, name='relation_detail'),
    path('works/<int:work_id>/<int:map_id>/html/', views.relation_html, name='relation_html'),
    path('works/<int:work_id>/<int:map_id>/download/', views.relation_download, name='relation_download'),
    path('works/<int:work_id>/<int:map_id>/delete/', views.relation_delete, name='relation_delete'),
]
