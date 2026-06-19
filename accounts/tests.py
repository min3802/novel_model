from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import Profile
from accounts.services import (
    default_nickname,
    is_rejoin_blocked,
    withdraw_user,
)
from accounts.validators import validate_nickname
from credits.models import CreditTransaction

User = get_user_model()


class NicknameValidatorTests(TestCase):
    def test_accepts_korean_eng_num_2_to_10(self):
        for value in ['가나', '홍길동', 'abc12', '닉네임1234']:
            self.assertEqual(validate_nickname(value), value)

    def test_rejects_space(self):
        with self.assertRaises(ValidationError):
            validate_nickname('홍 길동')

    def test_rejects_too_short_or_long(self):
        with self.assertRaises(ValidationError):
            validate_nickname('가')
        with self.assertRaises(ValidationError):
            validate_nickname('12345678901')

    def test_rejects_special_chars(self):
        with self.assertRaises(ValidationError):
            validate_nickname('hi!@#')

    def test_default_nickname_sanitizes(self):
        self.assertEqual(default_nickname('john.doe@example.com'), 'johndoeexa')
        self.assertTrue(2 <= len(default_nickname('a')) <= 10)


class WithdrawalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ryuser', email='ry@example.com', password='x'
        )
        Profile.objects.create(user=self.user, nickname='류저')

    def _add_credit(self, delta, balance_after):
        return CreditTransaction.objects.create(
            user=self.user,
            transaction_type=CreditTransaction.TYPE_CHARGE,
            credit_delta=delta,
            balance_after=balance_after,
            feature_name='test',
        )

    def test_withdraw_forfeits_credit_and_deactivates(self):
        self._add_credit(100, 100)
        withdraw_user(self.user)
        self.user.refresh_from_db()
        profile = self.user.profile
        self.assertFalse(self.user.is_active)
        self.assertIsNotNone(profile.withdrawn_at)
        from django.db.models import Sum
        balance = CreditTransaction.objects.filter(user=self.user).aggregate(
            t=Sum('credit_delta')
        )['t']
        self.assertEqual(balance, 0)

    def test_rejoin_blocked_within_7_days(self):
        withdraw_user(self.user)
        self.assertTrue(is_rejoin_blocked('ry@example.com'))
        self.assertTrue(is_rejoin_blocked('RY@example.com'))

    def test_rejoin_allowed_after_7_days(self):
        withdraw_user(self.user)
        profile = self.user.profile
        profile.withdrawn_at = timezone.now() - timedelta(days=8)
        profile.save(update_fields=['withdrawn_at'])
        self.assertFalse(is_rejoin_blocked('ry@example.com'))

    def test_rejoin_not_blocked_for_unknown_email(self):
        self.assertFalse(is_rejoin_blocked('nobody@example.com'))
