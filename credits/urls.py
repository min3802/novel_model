from django.urls import path
from . import views

app_name = 'credits'

urlpatterns = [
    path('', views.credit_balance, name='credit_balance'),
    path('charge/', views.credit_charge, name='credit_charge'),
    path('balance/', views.credit_balance, name='credit_balance'),
    path('use/', views.credit_use, name='credit_use'),
    path('cancel/', views.payment_cancel, name='payment_cancel'),
    path('cancel/<int:payment_id>/', views.payment_cancel, name='payment_cancel_detail'),
    path('success/', views.payment_success, name='payment_success'),
    path('fail/', views.payment_fail, name='payment_fail'),
]
