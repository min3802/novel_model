from django.core.exceptions import ValidationError

from characters.models import Character
from common.openai_client import request_json

from ..prompts.relation_prompts import SYSTEM_PROMPT, build_relation_extract_prompt


RELATION_CHARACTER_LIMIT = 20


def get_selected_characters(work, character_ids=None):
    query = Character.objects.filter(work=work).order_by('id')
    if not character_ids:
        return list(query[:RELATION_CHARACTER_LIMIT])

    unique_ids = list(dict.fromkeys(int(item) for item in character_ids))
    if len(unique_ids) > RELATION_CHARACTER_LIMIT:
        raise ValidationError(f'관계도에 포함 가능한 캐릭터는 최대 {RELATION_CHARACTER_LIMIT}명입니다.')

    characters = list(query.filter(id__in=unique_ids))
    if len(characters) != len(unique_ids):
        raise ValidationError('선택한 캐릭터 중 해당 작품에 속하지 않는 캐릭터가 있습니다.')

    return sorted(characters, key=lambda character: unique_ids.index(character.id))


def normalize_relation_data(work, payload, characters):
    valid_by_id = {f'char_{character.id}': character for character in characters}
    valid_names = {character.name for character in characters}

    normalized_characters = []
    seen_ids = set()
    for item in payload.get('characters') or []:
        raw_id = str(item.get('id', '')).strip()
        name = str(item.get('name', '')).strip()
        if raw_id not in valid_by_id and name in valid_names:
            source = next(character for character in characters if character.name == name)
            raw_id = f'char_{source.id}'

        source = valid_by_id.get(raw_id)
        if not source or raw_id in seen_ids:
            continue

        seen_ids.add(raw_id)
        normalized_characters.append(
            {
                'id': raw_id,
                'name': source.name,
                'role': str(item.get('role') or source.role or '인물').strip()[:40],
                'description': str(
                    item.get('description') or source.description or source.relation or source.personality or source.appearance
                ).strip()[:180],
                'is_main': bool(item.get('is_main', False)),
                'importance': int(item.get('importance') or 3),
            }
        )

    if not normalized_characters:
        for index, character in enumerate(characters, start=1):
            normalized_characters.append(
                {
                    'id': f'char_{character.id}',
                    'name': character.name,
                    'role': character.role or ('주인공' if index == 1 else '인물'),
                    'description': (character.description or character.relation or character.personality or character.appearance)[:180],
                    'is_main': index == 1,
                    'importance': index,
                }
            )

    if not normalized_characters:
        raise ValidationError('관계도를 생성하려면 등록된 캐릭터 설정이 필요합니다.')

    valid_node_ids = {item['id'] for item in normalized_characters}
    if not any(item['is_main'] for item in normalized_characters):
        normalized_characters[0]['is_main'] = True

    groups = []
    seen_groups = set()
    for index, group in enumerate(payload.get('groups') or [], start=1):
        members = [member for member in (group.get('members') or []) if member in valid_node_ids]
        name = str(group.get('name', '')).strip()
        if not name or not members or name in seen_groups:
            continue
        seen_groups.add(name)
        groups.append(
            {
                'id': str(group.get('id') or f'group_{index:03d}').strip(),
                'name': name[:60],
                'group_type': str(group.get('group_type') or 'group').strip()[:30],
                'members': members,
                'description': str(group.get('description') or '').strip()[:180],
                'importance': int(group.get('importance') or 3),
            }
        )

    relations = []
    seen_relations = set()
    for relation in payload.get('relations') or []:
        source = str(relation.get('source', '')).strip()
        target = str(relation.get('target', '')).strip()
        label = str(relation.get('relation') or '관계').strip()[:30]
        key = (source, target, label)
        if source not in valid_node_ids or target not in valid_node_ids or source == target or key in seen_relations:
            continue
        seen_relations.add(key)
        direction = str(relation.get('direction') or 'both').strip()
        relations.append(
            {
                'source': source,
                'target': target,
                'relation': label,
                'description': str(relation.get('description') or '').strip()[:220],
                'direction': 'one_way' if direction == 'one_way' else 'both',
                'style': str(relation.get('style') or 'neutral').strip()[:30],
                'importance': int(relation.get('importance') or 3),
            }
        )

    main_character = next((item['name'] for item in normalized_characters if item['is_main']), normalized_characters[0]['name'])
    summary = str(payload.get('summary') or '').strip()
    if not summary:
        summary = f'{main_character}을 중심으로 캐릭터 설정집의 관계 정보를 요약한 인물 관계도입니다.'

    return {
        'work_title': str(payload.get('work_title') or work.title).strip(),
        'main_character': main_character,
        'summary': summary[:350],
        'characters': normalized_characters[:RELATION_CHARACTER_LIMIT],
        'groups': groups,
        'relations': relations,
        'warnings': [str(item).strip()[:180] for item in (payload.get('warnings') or []) if str(item).strip()],
    }


def extract_relation_data(work, character_ids=None):
    characters = get_selected_characters(work, character_ids)
    if not characters:
        raise ValidationError('관계도를 생성하려면 등록된 캐릭터 설정이 필요합니다.')

    payload = request_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_relation_extract_prompt(
            work_title=work.title,
            characters=characters,
            limit=RELATION_CHARACTER_LIMIT,
        ),
    )
    return normalize_relation_data(work, payload, characters)
