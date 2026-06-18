from django.db import models
from django.conf import settings
from django.utils import timezone


class CreditPayment(models.Model):
    STATUS_READY = 'READY'
    STATUS_DONE = 'DONE'
    STATUS_CANCELED = 'CANCELED'
    STATUS_FAIL = 'FAIL'
    STATUS_CONFIRM_FAIL = 'CONFIRM_FAIL'

    STATUS_CHOICES = [
        (STATUS_READY, '요청'),
        (STATUS_DONE, '완료'),
        (STATUS_CANCELED, '취소'),
        (STATUS_FAIL, '실패'),
        (STATUS_CONFIRM_FAIL, '승인실패'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan_code = models.CharField(max_length=20)
    plan_name = models.CharField(max_length=50)
    credit_amount = models.IntegerField()
    amount = models.IntegerField()

    order_id = models.CharField(max_length=100, unique=True)
    payment_key = models.CharField(max_length=200, unique=True, null=True, blank=True)
    order_name = models.CharField(max_length=100, blank=True)
    method = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_READY)
    receipt_url = models.URLField(max_length=500, blank=True)

    requested_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    cancel_transaction_key = models.CharField(max_length=100, blank=True)

    fail_code = models.CharField(max_length=100, blank=True)
    fail_message = models.TextField(blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_cancel_period(self):
        base_time = self.approved_at or self.created_at
        return timezone.now() <= base_time + timezone.timedelta(days=7)

    @property
    def can_cancel(self):
        return (
            self.status == self.STATUS_DONE
            and bool(self.payment_key)
            and self.is_cancel_period
        )

    def __str__(self):
        return f'{self.order_id} ({self.status})'


class CreditTransaction(models.Model):
    TYPE_CHARGE = 'CHARGE'
    TYPE_USE = 'USE'
    TYPE_CANCEL = 'CANCEL'

    TYPE_CHOICES = [
        (TYPE_CHARGE, '충전'),
        (TYPE_USE, '사용'),
        (TYPE_CANCEL, '환불'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    payment = models.ForeignKey(
        CreditPayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
    )
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    credit_delta = models.IntegerField()
    balance_after = models.IntegerField()
    feature_name = models.CharField(max_length=100, blank=True)
    memo = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user_id} {self.transaction_type} {self.credit_delta}'
