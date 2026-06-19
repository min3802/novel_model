from allauth.account.signals import user_signed_up
from django.dispatch import receiver

from .models import Profile
from .services import default_nickname


@receiver(user_signed_up)
def create_profile_on_signup(sender, request, user, **kwargs):
    """소셜 회원가입 완료 시 Profile 생성 + 연동 제공자 정보 기록."""
    sociallogin = kwargs.get('sociallogin')
    provider = ''
    provider_uid = ''
    base = user.email or user.get_username() or 'user'
    if sociallogin is not None and sociallogin.account is not None:
        provider = (sociallogin.account.provider or '').upper()
        provider_uid = str(sociallogin.account.uid or '')
        extra = sociallogin.account.extra_data or {}
        base = extra.get('nickname') or extra.get('name') or base
    Profile.objects.get_or_create(
        user=user,
        defaults={
            'nickname': default_nickname(base),
            'oauth_provider': provider,
            'provider_user_id': provider_uid,
        },
    )
