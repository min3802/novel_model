import base64
import uuid

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import CreditPayment
from .models import CreditTransaction


CREDIT_PLANS = {
    "BASIC": {
        "name": "Basic 충전",
        "price": 9900,
        "credits": 10000,
    },
    "PLUS": {
        "name": "Plus 충전",
        "price": 29900,
        "credits": 35000,
    },
    "MAX": {
        "name": "Max 충전",
        "price": 49900,
        "credits": 75000,
    },
}


def _current_balance(user):
    result = CreditTransaction.objects.filter(user=user).aggregate(total=Sum('credit_delta'))
    return result['total'] or 0


def _parse_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _plan_code_from_order_id(order_id):
    order_id = (order_id or '').lower()
    for plan_code in CREDIT_PLANS:
        if f'-{plan_code.lower()}-' in order_id:
            return plan_code
    return ''


def _encode_toss_secret():
    return base64.b64encode(f'{settings.TOSS_SECRET_KEY}:'.encode()).decode()


def _json_or_error(response):
    try:
        return response.json()
    except ValueError:
        return {
            'code': 'INVALID_TOSS_RESPONSE',
            'message': response.text,
        }


@login_required
def credit_balance(request):
    return render(request, 'credits/credit_balance.html', {
        'balance': _current_balance(request.user),
        'payments': CreditPayment.objects.filter(user=request.user),
        'transactions': CreditTransaction.objects.filter(user=request.user),
    })


@login_required
def credit_charge(request):
    context = {
        'client_key': settings.TOSS_CLIENT_KEY,
        'plans': CREDIT_PLANS,
        'order_prefix': f'order-{uuid.uuid4().hex[:12]}',
        'success_url': settings.TOSS_SUCCESS_URL,
        'fail_url': settings.TOSS_FAIL_URL,
    }
    return render(request, 'credits/credit_charge.html', context)


@login_required
def credit_use(request):
    if request.method == 'POST':
        credit_amount = int(request.POST.get('credit_amount') or 0)
        feature_name = request.POST.get('feature_name') or '크레딧 차감 테스트'
        balance = _current_balance(request.user)

        if credit_amount <= 0:
            messages.error(request, '차감할 크레딧은 1 이상이어야 합니다.')
        elif balance < credit_amount:
            messages.error(request, '보유 크레딧이 부족합니다.')
        else:
            CreditTransaction.objects.create(
                user=request.user,
                transaction_type=CreditTransaction.TYPE_USE,
                credit_delta=-credit_amount,
                balance_after=balance - credit_amount,
                feature_name=feature_name,
                memo='테스트 차감',
            )
            messages.success(request, f'{credit_amount} CR 차감 완료')
            return redirect('credits:credit_balance')

    return render(request, 'credits/credit_use.html', {
        'balance': _current_balance(request.user),
    })


@login_required
def payment_cancel(request, payment_id=None):
    payment = None
    result = None
    status_code = None

    if payment_id is not None:
        payment = get_object_or_404(CreditPayment, id=payment_id, user=request.user)

    if request.method == 'POST':
        payment = get_object_or_404(
            CreditPayment,
            id=request.POST.get('payment_id'),
            user=request.user,
        )
        cancel_reason = request.POST.get('cancel_reason') or '사용자 요청으로 결제 취소'

        if not payment.can_cancel:
            messages.error(request, '취소 가능한 결제가 아닙니다.')
            return redirect('credits:payment_cancel_detail', payment_id=payment.id)

        balance = _current_balance(request.user)
        if balance < payment.credit_amount:
            messages.error(request, '충전된 크레딧을 일부 사용하여 결제 취소가 불가능합니다.')
            return redirect('credits:payment_cancel_detail', payment_id=payment.id)

        response = requests.post(
            f'https://api.tosspayments.com/v1/payments/{payment.payment_key}/cancel',
            headers={
                'Authorization': f'Basic {_encode_toss_secret()}',
                'Content-Type': 'application/json',
                'Idempotency-Key': f'cancel-{payment.id}-{uuid.uuid4().hex}',
            },
            json={
                'cancelReason': cancel_reason,
            },
            timeout=10,
        )
        status_code = response.status_code
        result = _json_or_error(response)

        if 200 <= response.status_code < 300:
            cancels = result.get('cancels') or []
            cancel_info = cancels[-1] if cancels else {}

            with transaction.atomic():
                payment.status = CreditPayment.STATUS_CANCELED
                payment.canceled_at = _parse_datetime(cancel_info.get('canceledAt')) or timezone.now()
                payment.cancel_reason = cancel_info.get('cancelReason') or cancel_reason
                payment.cancel_transaction_key = cancel_info.get('transactionKey') or ''
                payment.raw_response = result
                payment.save()

                if not CreditTransaction.objects.filter(
                    payment=payment,
                    transaction_type=CreditTransaction.TYPE_CANCEL,
                ).exists():
                    CreditTransaction.objects.create(
                        user=request.user,
                        payment=payment,
                        transaction_type=CreditTransaction.TYPE_CANCEL,
                        credit_delta=-payment.credit_amount,
                        balance_after=balance - payment.credit_amount,
                        feature_name='결제 취소',
                        memo=payment.cancel_reason,
                    )

            messages.success(request, '결제 취소 및 크레딧 환수가 완료되었습니다.')
        else:
            payment.fail_code = result.get('code') or ''
            payment.fail_message = result.get('message') or ''
            payment.save(update_fields=['fail_code', 'fail_message', 'updated_at'])
            messages.error(request, '결제 취소 요청이 실패했습니다.')

    return render(request, 'credits/payment_cancel.html', {
        'balance': _current_balance(request.user),
        'payment': payment,
        'payments': CreditPayment.objects.filter(user=request.user),
        'status_code': status_code,
        'result': result,
    })


@login_required
def payment_success(request):
    payment_key = request.GET.get('paymentKey')
    order_id = request.GET.get('orderId')
    amount = int(request.GET.get('amount') or 0)
    plan_code = _plan_code_from_order_id(order_id)
    plan = CREDIT_PLANS.get(plan_code)

    if not plan or amount != plan['price']:
        return render(request, 'credits/payment_success.html', {
            'status_code': 400,
            'result': {
                'code': 'INVALID_PAYMENT_PLAN',
                'message': '결제 플랜 또는 금액이 올바르지 않습니다.',
                'orderId': order_id,
                'amount': amount,
            },
        })

    response = requests.post(
        'https://api.tosspayments.com/v1/payments/confirm',
        headers={
            'Authorization': f'Basic {_encode_toss_secret()}',
            'Content-Type': 'application/json',
        },
        json={
            'paymentKey': payment_key,
            'orderId': order_id,
            'amount': amount,
        },
        timeout=10,
    )

    result = _json_or_error(response)

    with transaction.atomic():
        payment, _ = CreditPayment.objects.update_or_create(
            order_id=order_id,
            defaults={
                'user': request.user,
                'plan_code': plan_code,
                'plan_name': plan['name'],
                'credit_amount': plan['credits'],
                'amount': amount,
                'payment_key': payment_key,
                'order_name': result.get('orderName') or f"w.LiGHTER {plan['name']}",
                'method': result.get('method') or '',
                'status': (
                    CreditPayment.STATUS_DONE
                    if response.status_code == 200 and result.get('status') == 'DONE'
                    else CreditPayment.STATUS_CONFIRM_FAIL
                ),
                'receipt_url': (result.get('receipt') or {}).get('url') or '',
                'requested_at': _parse_datetime(result.get('requestedAt')),
                'approved_at': _parse_datetime(result.get('approvedAt')),
                'fail_code': result.get('code') or '',
                'fail_message': result.get('message') or '',
                'raw_response': result,
            },
        )

        if payment.status == CreditPayment.STATUS_DONE:
            if not CreditTransaction.objects.filter(
                payment=payment,
                transaction_type=CreditTransaction.TYPE_CHARGE,
            ).exists():
                balance = _current_balance(request.user)
                CreditTransaction.objects.create(
                    user=request.user,
                    payment=payment,
                    transaction_type=CreditTransaction.TYPE_CHARGE,
                    credit_delta=payment.credit_amount,
                    balance_after=balance + payment.credit_amount,
                    feature_name='크레딧 충전',
                    memo=payment.plan_name,
                )

    return render(request, 'credits/payment_success.html', {
        'status_code': response.status_code,
        'result': result,
        'payment': payment,
    })


@login_required
def payment_fail(request):
    code = request.GET.get('code') or ''
    message = request.GET.get('message') or ''
    order_id = request.GET.get('orderId') or ''
    plan_code = _plan_code_from_order_id(order_id)
    plan = CREDIT_PLANS.get(plan_code)

    if order_id and plan:
        CreditPayment.objects.update_or_create(
            order_id=order_id,
            defaults={
                'user': request.user,
                'plan_code': plan_code,
                'plan_name': plan['name'],
                'credit_amount': plan['credits'],
                'amount': plan['price'],
                'order_name': f"w.LiGHTER {plan['name']}",
                'status': CreditPayment.STATUS_FAIL,
                'fail_code': code,
                'fail_message': message,
                'raw_response': dict(request.GET),
            },
        )

    return render(request, 'credits/payment_fail.html', {
        'code': code,
        'message': message,
        'order_id': order_id,
    })
