import base64
import uuid
import requests

from django.conf import settings
from django.shortcuts import render


def credit_balance(request):
    return render(request, 'credits/credit_balance.html')


def credit_charge(request):
    context = {
        'client_key': settings.TOSS_CLIENT_KEY,
        'order_id': f'order-{uuid.uuid4().hex[:20]}',
        'amount': 5000,
        'order_name': 'w.LiGHTER 크레딧 5000원 충전',
        'success_url': settings.TOSS_SUCCESS_URL,
        'fail_url': settings.TOSS_FAIL_URL,
    }
    return render(request, 'credits/credit_charge.html', context)


def payment_success(request):
    payment_key = request.GET.get('paymentKey')
    order_id = request.GET.get('orderId')
    amount = request.GET.get('amount')

    secret_key = settings.TOSS_SECRET_KEY
    encoded_secret = base64.b64encode(f'{secret_key}:'.encode()).decode()

    response = requests.post(
        'https://api.tosspayments.com/v1/payments/confirm',
        headers={
            'Authorization': f'Basic {encoded_secret}',
            'Content-Type': 'application/json',
        },
        json={
            'paymentKey': payment_key,
            'orderId': order_id,
            'amount': int(amount),
        },
        timeout=10,
    )

    result = response.json()

    return render(request, 'credits/payment_success.html', {
        'status_code': response.status_code,
        'result': result,
    })


def payment_fail(request):
    return render(request, 'credits/payment_fail.html', {
        'code': request.GET.get('code'),
        'message': request.GET.get('message'),
        'order_id': request.GET.get('orderId'),
    })