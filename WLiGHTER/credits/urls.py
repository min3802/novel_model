from django.urls import path
from . import views

app_name = 'credits'

urlpatterns = [
    path('', views.credit_balance, name='credit_balance'),
    path('charge/', views.credit_charge, name='credit_charge'),
    path('success/', views.payment_success, name='payment_success'),
    path('fail/', views.payment_fail, name='payment_fail'),
]