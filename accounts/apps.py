from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        # 회원가입 시 Profile 생성 시그널 등록
        from . import signals  # noqa: F401
