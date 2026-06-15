import json
import os

from django.conf import settings
from django.core.exceptions import ValidationError

from characters.models import CharacterProfile

from ..constants import RELATION_CHARACTER_LIMIT


SYSTEM_PROMPT = """
너는 캐릭터 설정집을 읽고 HTML 인물 관계도에 들어갈 요약 데이터를 만드는 분석가다.
관계도는 사용자가 직접 수정하지 않는 결과물이므로, 캐릭터 설정집에 적힌 정보만 근거로 삼는다.
반드시 JSON만 반환한다. 제공된 캐릭터 외 새 인물을 만들지 않는다.
동일 인물의 별칭/호칭으로 보이는 항목은 중복 노드로 만들지 않는다.
"""


def request_json(system_prompt: str, user_prompt: str) -> dict:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되어 있지 않습니다.")
    client = OpenAI(api_key=api_key)
    model = getattr(settings, "WLIGHTER_TEXT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


def get_selected_characters(work, character_ids: list[int] | None = None) -> list[CharacterProfile]:
    query = CharacterProfile.objects.filter(work=work).order_by("id")
    if character_ids:
        if len(character_ids) > RELATION_CHARACTER_LIMIT:
            raise ValidationError(f"관계도에 포함 가능한 캐릭터는 최대 {RELATION_CHARACTER_LIMIT}명입니다.")
        unique_ids = list(dict.fromkeys(int(item) for item in character_ids))
        query = query.filter(id__in=unique_ids)
        characters = list(query)
        if len(characters) != len(unique_ids):
            raise ValidationError("선택한 캐릭터 중 해당 작품에 속하지 않는 캐릭터가 있습니다.")
        return sorted(characters, key=lambda character: unique_ids.index(character.id))
    return list(query[:RELATION_CHARACTER_LIMIT])


def build_prompt(work, characters: list[CharacterProfile]) -> str:
    character_lines = []
    for index, character in enumerate(characters, start=1):
        character_lines.append(
            "\n".join(
                [
                    f"[{index}] id=char_{character.id}",
                    f"이름: {character.name}",
                    f"나이: {character.age or '-'}",
                    f"성별: {character.gender or '-'}",
                    f"역할: {character.role or '-'}",
                    f"관계 원문: {character.relation or '-'}",
                    f"외형: {character.appearance or '-'}",
                    f"세부 설정: {character.detail or '-'}",
                ]
            )
        )

    return f"""
[작품명]
{getattr(work, "title", "작품")}

[캐릭터 설정집]
{chr(10).join(character_lines)}

[반환 JSON 형식]
{{
  "work_title": "작품명",
  "main_character": "중심 인물 이름",
  "summary": "관계도 상단에 들어갈 2~3문장 요약",
  "characters": [
    {{
      "id": "char_캐릭터DBID",
      "name": "캐릭터명",
      "role": "관계도 카드에 표시할 역할",
      "description": "관계도 카드용 한 줄 설명",
      "is_main": true,
      "importance": 1,
      "image_path": ""
    }}
  ],
  "groups": [
    {{
      "id": "group_001",
      "name": "소속/조직/팀명",
      "group_type": "team",
      "members": ["char_캐릭터DBID"],
      "description": "그룹 설명",
      "importance": 1
    }}
  ],
  "relations": [
    {{
      "source": "char_출발캐릭터DBID",
      "target": "char_도착캐릭터DBID",
      "relation": "관계 라벨",
      "description": "관계도 하단 목록에 들어갈 관계 설명",
      "direction": "both",
      "style": "partnership",
      "importance": 1
    }}
  ],
  "warnings": ["추정 또는 제외 사유가 있을 때만 작성"]
}}

[규칙]
- characters는 제공된 캐릭터만 사용하고 최대 {RELATION_CHARACTER_LIMIT}명이다.
- 캐릭터 id는 반드시 입력에 제공된 char_DBID 형식을 유지한다.
- relations의 source/target은 characters의 id와 정확히 일치해야 한다.
- direction은 both 또는 one_way 중 하나만 사용한다.
- style은 romance, partnership, hierarchy, rivalry, mentorship, family, organization, neutral 중 하나를 권장한다.
- 관계 라벨은 짧게, 관계 설명은 1~2문장으로 요약한다.
- 관계도 내용은 캐릭터 설정집 기반 자동 요약 결과다. 사용자가 직접 관계도를 수정한다고 가정하지 않는다.
"""


def normalize_relation_data(work, payload: dict, characters: list[CharacterProfile]) -> dict:
    valid_by_id = {f"char_{character.id}": character for character in characters}
    valid_names = {character.name for character in characters}

    normalized_characters = []
    seen_ids = set()
    for item in payload.get("characters") or []:
        raw_id = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if raw_id not in valid_by_id and name in valid_names:
            source = next(character for character in characters if character.name == name)
            raw_id = f"char_{source.id}"
        source = valid_by_id.get(raw_id)
        if not source or raw_id in seen_ids:
            continue
        seen_ids.add(raw_id)
        normalized_characters.append(
            {
                "id": raw_id,
                "name": source.name,
                "role": str(item.get("role") or source.role or "인물").strip()[:40],
                "description": str(item.get("description") or source.detail or source.relation or source.appearance).strip()[:180],
                "is_main": bool(item.get("is_main", False)),
                "importance": int(item.get("importance") or 3),
                "image_path": str(item.get("image_path") or "").strip(),
            }
        )

    if not normalized_characters:
        for index, character in enumerate(characters, start=1):
            normalized_characters.append(
                {
                    "id": f"char_{character.id}",
                    "name": character.name,
                    "role": character.role or ("주인공" if index == 1 else "인물"),
                    "description": (character.detail or character.relation or character.appearance)[:180],
                    "is_main": index == 1,
                    "importance": index,
                    "image_path": "",
                }
            )

    valid_node_ids = {item["id"] for item in normalized_characters}
    if not any(item["is_main"] for item in normalized_characters):
        normalized_characters[0]["is_main"] = True

    groups = []
    seen_groups = set()
    for index, group in enumerate(payload.get("groups") or [], start=1):
        members = [member for member in (group.get("members") or []) if member in valid_node_ids]
        name = str(group.get("name", "")).strip()
        if not name or not members or name in seen_groups:
            continue
        seen_groups.add(name)
        groups.append(
            {
                "id": str(group.get("id") or f"group_{index:03d}").strip(),
                "name": name[:60],
                "group_type": str(group.get("group_type") or "group").strip()[:30],
                "members": members,
                "description": str(group.get("description") or "").strip()[:180],
                "importance": int(group.get("importance") or 3),
            }
        )

    relations = []
    seen_relations = set()
    for relation in payload.get("relations") or []:
        source = str(relation.get("source", "")).strip()
        target = str(relation.get("target", "")).strip()
        label = str(relation.get("relation") or "관계").strip()[:30]
        key = (source, target, label)
        if source not in valid_node_ids or target not in valid_node_ids or source == target or key in seen_relations:
            continue
        seen_relations.add(key)
        direction = str(relation.get("direction") or "both").strip()
        relations.append(
            {
                "source": source,
                "target": target,
                "relation": label,
                "description": str(relation.get("description") or "").strip()[:220],
                "direction": "one_way" if direction == "one_way" else "both",
                "style": str(relation.get("style") or "neutral").strip()[:30],
                "importance": int(relation.get("importance") or 3),
            }
        )

    title = getattr(work, "title", "작품")
    main_character = next((item["name"] for item in normalized_characters if item["is_main"]), normalized_characters[0]["name"])
    summary = str(payload.get("summary") or "").strip()
    if not summary:
        summary = f"{main_character}을 중심으로 캐릭터 설정집의 관계 정보를 요약한 인물 관계도입니다."

    return {
        "work_title": str(payload.get("work_title") or title).strip(),
        "main_character": main_character,
        "summary": summary[:350],
        "characters": normalized_characters[:RELATION_CHARACTER_LIMIT],
        "groups": groups,
        "relations": relations,
        "warnings": [str(item).strip()[:180] for item in (payload.get("warnings") or []) if str(item).strip()],
    }


def extract_relation_data(work, character_ids: list[int] | None = None) -> dict:
    characters = get_selected_characters(work, character_ids)
    if not characters:
        raise ValidationError("관계도를 생성하려면 등록된 캐릭터 설정이 필요합니다.")

    payload = request_json(SYSTEM_PROMPT, build_prompt(work, characters))
    return normalize_relation_data(work, payload, characters)
