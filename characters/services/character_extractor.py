import re

from django.core.exceptions import ValidationError
from django.db import transaction

from common.openai_client import request_json

from ..models import Character
from ..prompts.character_extract_prompts import SYSTEM_PROMPT, build_character_extract_prompt


CHARACTER_LIMIT_PER_WORK = 20


FIELD_LIMITS = {
    'name': 50,
    'age': 20,
    'role': 30,
    'gender': 20,
}


def compact(value):
    return re.sub(r'\s+', ' ', (value or '').strip())


def cut(value, limit=None):
    text = compact(value)
    return text[:limit] if limit else text


def normalize_character_item(item):
    return {
        'name': cut(item.get('name'), FIELD_LIMITS['name']),
        'age': cut(item.get('age'), FIELD_LIMITS['age']),
        'role': cut(item.get('role'), FIELD_LIMITS['role']),
        'gender': cut(item.get('gender'), FIELD_LIMITS['gender']),
        'relation': cut(item.get('relation')),
        'appearance': cut(item.get('appearance')),
        'personality': cut(item.get('personality')),
        'description': cut(item.get('description') or item.get('detail')),
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
        if not row['name'] or row['name'] in seen_names:
            continue
        seen_names.add(row['name'])
        normalized.append(row)

    if not save:
        return normalized

    with transaction.atomic():
        saved = []
        for row in normalized:
            character, _ = Character.objects.update_or_create(
                work=work,
                name=row['name'],
                defaults={**row, 'source': Character.SOURCE_AI},
            )
            saved.append(character)
        return saved
