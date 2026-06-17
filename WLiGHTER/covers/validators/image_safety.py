from dataclasses import dataclass

from covers.prompts.cover_prompts import COUNTRY_COVER_STYLE_PROMPTS


MAX_USER_PROMPT_CHARS = 500
MAX_SYNOPSIS_CHARS = 8000


class ImageInputValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    messages: list[str]


BLOCKED_KEYWORDS = [
    '미성년자 성적',
    '아동 성적',
    '나체 미성년자',
    '성행위',
    '포르노',
    '실존 인물처럼',
    '유명인 얼굴',
    '연예인 얼굴',
    '브랜드 로고',
    '실제 로고',
    '저작권 캐릭터',
]


def _char_len(text):
    return len((text or '').strip())


def validate_cover_inputs(*, synopsis, target_country, user_prompt=''):
    messages = []

    if _char_len(synopsis) == 0:
        messages.append('시놉시스가 비어 있습니다.')

    if _char_len(synopsis) > MAX_SYNOPSIS_CHARS:
        messages.append(f'시놉시스는 최대 {MAX_SYNOPSIS_CHARS}자까지 입력할 수 있습니다.')

    if target_country.strip().upper() not in COUNTRY_COVER_STYLE_PROMPTS:
        allowed = ', '.join(COUNTRY_COVER_STYLE_PROMPTS.keys())
        messages.append(f'지원하지 않는 대상 국가입니다. 선택 가능: {allowed}')

    if _char_len(user_prompt) > MAX_USER_PROMPT_CHARS:
        messages.append(f'사용자 추가 요청은 최대 {MAX_USER_PROMPT_CHARS}자까지 입력할 수 있습니다.')

    combined = f'{synopsis}\n{user_prompt}'.lower()
    for keyword in BLOCKED_KEYWORDS:
        if keyword.lower() in combined:
            messages.append(f'이미지 생성 전에 확인이 필요한 표현이 포함되어 있습니다: {keyword}')

    return ValidationResult(ok=not messages, messages=messages)


def assert_valid_cover_inputs(**kwargs):
    result = validate_cover_inputs(**kwargs)
    if not result.ok:
        raise ImageInputValidationError('\n'.join(result.messages))
