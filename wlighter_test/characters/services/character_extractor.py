import re

from django.core.exceptions import ValidationError
from django.db import transaction

from ..constants import (
    AGE_MAX_LENGTH,
    APPEARANCE_MAX_LENGTH,
    CHARACTER_LIMIT_PER_WORK,
    DETAIL_MAX_LENGTH,
    GENDER_MAX_LENGTH,
    NAME_MAX_LENGTH,
    RELATION_MAX_LENGTH,
    ROLE_MAX_LENGTH,
)
from ..models import CharacterProfile
from .openai_client import request_json


SYSTEM_PROMPT = """
너는 한국어 웹소설의 시놉시스를 읽고 작품 관리용 캐릭터 설정집을 만드는 분석가다.
반드시 JSON만 반환한다. 원문 근거가 부족한 값은 빈 문자열로 둔다.
"""


def compact(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def cut(value: str | None, limit: int) -> str:
    return compact(value)[:limit]


def first_attr(obj, names, default="") -> str:
    for name in names:
        value = getattr(obj, name, None)
        if value:
            return str(value)
    return default


def build_prompt(work, synopsis: str) -> str:
    return f"""
[작품 정보]
제목: {first_attr(work, ["title", "name"], "작품")}
장르: {first_attr(work, ["genre"], "")}

[시놉시스]
{synopsis}

[반환 JSON 형식]
{{
  "characters": [
    {{
      "name": "필수, 30자 이내",
      "age": "선택, 10자 이내",
      "role": "주인공/주요인물/조연/단역 중 하나 권장, 5자 이내",
      "gender": "선택, 5자 이내",
      "relation": "다른 인물과의 관계 요약, 500자 이내",
      "appearance": "외형 정보, 300자 이내",
      "detail": "성격/직업/소속/서사 역할 등 세부 설정, 1000자 이내"
    }}
  ]
}}

[규칙]
- 최대 {CHARACTER_LIMIT_PER_WORK}명까지만 추출한다.
- 이름이 없는 항목은 만들지 않는다.
- 내용은 모두 한국어로 작성한다.
"""


def normalize_item(item: dict) -> dict:
    return {
        "name": cut(item.get("name"), NAME_MAX_LENGTH),
        "age": cut(item.get("age"), AGE_MAX_LENGTH),
        "role": cut(item.get("role"), ROLE_MAX_LENGTH),
        "gender": cut(item.get("gender"), GENDER_MAX_LENGTH),
        "relation": cut(item.get("relation"), RELATION_MAX_LENGTH),
        "appearance": cut(item.get("appearance"), APPEARANCE_MAX_LENGTH),
        "detail": cut(item.get("detail"), DETAIL_MAX_LENGTH),
    }


def extract_character_settings(work, synopsis: str | None = None, save: bool = True):
    source = synopsis or first_attr(work, ["synopsis", "description", "desc"], "")
    if not source.strip():
        raise ValidationError("캐릭터 설정을 생성하려면 작품 시놉시스가 필요합니다.")

    payload = request_json(SYSTEM_PROMPT, build_prompt(work, source))
    normalized = []
    seen_names = set()

    for item in (payload.get("characters") or [])[:CHARACTER_LIMIT_PER_WORK]:
        row = normalize_item(item)
        if not row["name"] or row["name"] in seen_names:
            continue
        seen_names.add(row["name"])
        normalized.append(row)

    if not save:
        return normalized

    with transaction.atomic():
        saved = []
        for row in normalized:
            character, _ = CharacterProfile.objects.update_or_create(
                work=work,
                name=row["name"],
                defaults={**row, "source": CharacterProfile.SOURCE_AI},
            )
            character.full_clean()
            character.save()
            saved.append(character)
        return saved

