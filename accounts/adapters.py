from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import HttpResponseForbidden

from .services import is_rejoin_blocked


class WLighterSocialAccountAdapter(DefaultSocialAccountAdapter):
    """소셜 로그인 어댑터.

    탈퇴 후 7일 이내 동일 이메일 재가입을 차단한다(REQ-USER-004).
    """

    def pre_social_login(self, request, sociallogin):
        email = ''
        if sociallogin.user and sociallogin.user.email:
            email = sociallogin.user.email
        elif sociallogin.account and sociallogin.account.extra_data:
            email = sociallogin.account.extra_data.get('email', '')
        if email and is_rejoin_blocked(email):
            raise ImmediateHttpResponse(
                HttpResponseForbidden(
                    '탈퇴 후 7일간 재가입이 제한됩니다. 잠시 후 다시 시도해 주세요.'
                )
            )
        return super().pre_social_login(request, sociallogin)
