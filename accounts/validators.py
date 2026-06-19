import re

from django.core.exceptions import ValidationError

# 닉네임 규칙(REQ-USER-001): 한글/영문/숫자만, 공백 불가, 2~10자.
NICKNAME_RE = re.compile(r'^[가-힣A-Za-z0-9]{2,10}$')


def validate_nickname(value):
    text = value or ''
    if any(ch.isspace() for ch in text):
        raise ValidationError('닉네임에는 공백을 사용할 수 없습니다.')
    if not NICKNAME_RE.fullmatch(text):
        raise ValidationError('닉네임은 한글·영문·숫자만 사용하여 2~10자로 입력해야 합니다.')
    return text
