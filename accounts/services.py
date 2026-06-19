"""accounts 도메인 로직 (뷰/어댑터에서 호출하는 순수 함수 모음).

OAuth 머신러리 없이도 단위 테스트가 가능하도록 핵심 규칙을 여기에 모은다.
"""

import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

# 회원탈퇴 후 동일 이메일 재가입 차단 기간(REQ-USER-004).
REJOIN_BLOCK_DAYS = 7

_NICKNAME_ALLOWED = re.compile(r'[^가-힣A-Za-z0-9]')


def sanitize_nickname_base(base):
    """임의 문자열을 닉네임 규칙(한/영/숫자, 2~10자)에 맞게 정리."""
    cleaned = _NICKNAME_ALLOWED.sub('', base or '')
    cleaned = cleaned[:10]
    if len(cleaned) < 2:
        cleaned = (cleaned + 'user')[:10]
    return cleaned


def default_nickname(base):
    return sanitize_nickname_base(base) or 'user'


def is_rejoin_blocked(email, now=None):
    """탈퇴 후 7일 이내 동일 이메일이면 재가입 차단 대상."""
    if not email:
        return False
    from .models import Profile

    now = now or timezone.now()
    cutoff = now - timedelta(days=REJOIN_BLOCK_DAYS)
    return Profile.objects.filter(
        user__email__iexact=email,
        withdrawn_at__isnull=False,
        withdrawn_at__gt=cutoff,
    ).exists()


def current_credit_balance(user):
    from credits.models import CreditTransaction

    return CreditTransaction.objects.filter(user=user).aggregate(
        total=Sum('credit_delta')
    )['total'] or 0


def forfeit_credits(user):
    """잔여 크레딧을 0으로 소멸시키는 거래 기록(REQ-USER-004: 환불 없이 소멸)."""
    from credits.models import CreditTransaction

    balance = current_credit_balance(user)
    if balance > 0:
        CreditTransaction.objects.create(
            user=user,
            transaction_type=CreditTransaction.TYPE_USE,
            credit_delta=-balance,
            balance_after=0,
            feature_name='withdrawal',
            memo='회원탈퇴로 잔여 크레딧 소멸',
        )
    return balance


def withdraw_user(user, now=None):
    """회원탈퇴 처리.

    - 잔여 크레딧 소멸
    - withdrawn_at 기록(식별자/이메일은 7일 재가입 차단을 위해 보관)
    - 계정 비활성화

    NOTE: 작품/회차/대화 등 사용자 데이터의 완전 삭제 및 7일 후 식별정보
    영구 삭제(스케줄러)는 별도 배치 작업이 필요하다. 미완_작업.md 참고.
    """
    from .models import Profile

    now = now or timezone.now()
    with transaction.atomic():
        forfeit_credits(user)
        profile, _ = Profile.objects.get_or_create(
            user=user,
            defaults={'nickname': default_nickname(user.get_username())},
        )
        profile.withdrawn_at = now
        profile.save(update_fields=['withdrawn_at', 'updated_at'])
        user.is_active = False
        user.save(update_fields=['is_active'])
    return profile
