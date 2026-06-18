from django.contrib import admin

from .models import CreditPayment
from .models import CreditTransaction


@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'plan_code',
        'amount',
        'credit_amount',
        'status',
        'order_id',
        'payment_key',
        'approved_at',
        'canceled_at',
    )
    list_filter = ('status', 'plan_code', 'method')
    search_fields = ('order_id', 'payment_key', 'user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'transaction_type',
        'credit_delta',
        'balance_after',
        'feature_name',
        'payment',
        'created_at',
    )
    list_filter = ('transaction_type',)
    search_fields = ('user__username', 'user__email', 'feature_name', 'memo')
