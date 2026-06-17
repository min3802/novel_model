from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('signup/', views.signup, name='signup'),
    path('profile/', views.profile_detail, name='profile_detail'),
    path('profile/edit/', views.profile_update, name='profile_update'),
    path('withdraw/', views.withdraw, name='withdraw'),
]
