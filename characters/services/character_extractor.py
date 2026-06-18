import re

from django.core.exceptions import ValidationError
from django.db import transaction

from common.openai_client import request_json

from ..models import Character
from ..prompts.character_extract_prompts import SYSTEM_PROMPT, build_character_extract_prompt


CHARACTER_LIMIT_PER_WORK = 20


FIELD_LIMITS = {
    'char_name': 30,
    'age': 10,
    'role': 5,
    'gender': 5,
    'relationships': 500,
    'appearance': 300,
    'detail_setting': 1000,
}


def compact(value):
    return re.sub(r'\s+', ' ', (value or '').strip())


def cut(value, limit=None):
    text = compact(value)
    return text[:limit] if limit else text


def normalize_character_item(item):
    return {
        'char_name': cut(item.get('char_name') or item.get('name'), FIELD_LIMITS['char_name']),
        'age': cut(item.get('age'), FIELD_LIMITS['age']),
        'role': cut(item.get('role'), FIELD_LIMITS['role']),
        'gender': cut(item.get('gender'), FIELD_LIMITS['gender']),
        'relationships': cut(
            item.get('relationships') or item.get('relation'),
            FIELD_LIMITS['relationships']
        ),
        'appearance': cut(item.get('appearance'), FIELD_LIMITS['appearance']),
        'detail_setting': cut(
            item.get('detail_setting') or item.get('description') or item.get('detail'),
            FIELD_LIMITS['detail_setting']
        ),
    }


def extract_character_settings(work, *, save=True):
    synopsis = (work.synopsis or '').strip()
    if not synopsis:
        raise ValidationError('캐릭터 설정을 추출하려면 작품 시놉시스가 필요합니다.')

    payload = request_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_character_extract_prompt(
            work_title=work.title,
            genre=work.genre,
            synopsis=synopsis,
            limit=CHARACTER_LIMIT_PER_WORK,
        ),
    )

    normalized = []
    seen_names = set()

    for item in (payload.get('characters') or [])[:CHARACTER_LIMIT_PER_WORK]:
        row = normalize_character_item(item)

        if not row['char_name'] or row['char_name'] in seen_names:
            continue

        seen_names.add(row['char_name'])
        normalized.append(row)

    if not save:
        return normalized

    with transaction.atomic():
        saved = []

        for row in normalized:
            character, _ = Character.objects.update_or_create(
                work=work,
                char_name=row['char_name'],
                defaults={**row, 'source': Character.SOURCE_AI},
            )
            saved.append(character)

        return saved