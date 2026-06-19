from django.conf import settings
from django.db import models


class Profile(models.Model):
    """auth.User 확장 프로필.

    USERS ERD의 nickname/oauth_provider/provider_user_id/withdrawn_at를 담는다.
    크레딧 잔액은 credits 앱의 CreditTransaction 합계로 파생하므로 여기에 두지 않는다.
    """

    PROVIDER_GOOGLE = 'GOOGLE'
    PROVIDER_KAKAO = 'KAKAO'
    PROVIDER_NAVER = 'NAVER'
    PROVIDER_CHOICES = [
        (PROVIDER_GOOGLE, 'GOOGLE'),
        (PROVIDER_KAKAO, 'KAKAO'),
        (PROVIDER_NAVER, 'NAVER'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    nickname = models.CharField(max_length=10)
    oauth_provider = models.CharField(max_length=10, blank=True, choices=PROVIDER_CHOICES)
    provider_user_id = models.CharField(max_length=255, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_withdrawn(self):
        return self.withdrawn_at is not None

    def __str__(self):
        return self.nickname or f'profile:{self.user_id}'
