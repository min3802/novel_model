from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plan_code', models.CharField(max_length=20)),
                ('plan_name', models.CharField(max_length=50)),
                ('credit_amount', models.IntegerField()),
                ('amount', models.IntegerField()),
                ('order_id', models.CharField(max_length=100, unique=True)),
                ('payment_key', models.CharField(blank=True, max_length=200, null=True, unique=True)),
                ('order_name', models.CharField(blank=True, max_length=100)),
                ('method', models.CharField(blank=True, max_length=30)),
                ('status', models.CharField(choices=[('READY', '요청'), ('DONE', '완료'), ('CANCELED', '취소'), ('FAIL', '실패'), ('CONFIRM_FAIL', '승인실패')], default='READY', max_length=20)),
                ('receipt_url', models.URLField(blank=True, max_length=500)),
                ('requested_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('canceled_at', models.DateTimeField(blank=True, null=True)),
                ('cancel_reason', models.CharField(blank=True, max_length=255)),
                ('cancel_transaction_key', models.CharField(blank=True, max_length=100)),
                ('fail_code', models.CharField(blank=True, max_length=100)),
                ('fail_message', models.TextField(blank=True)),
                ('raw_response', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CreditTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_type', models.CharField(choices=[('CHARGE', '충전'), ('USE', '사용'), ('CANCEL', '환불')], max_length=20)),
                ('credit_delta', models.IntegerField()),
                ('balance_after', models.IntegerField()),
                ('feature_name', models.CharField(blank=True, max_length=100)),
                ('memo', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='transactions', to='credits.creditpayment')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
