from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError

from ..constants import CHARACTER_LIMIT_PER_WORK, ROLE_ORDER
from ..models import CharacterProfile


def get_work_model():
    model_path = getattr(settings, "WLIGHTER_WORK_MODEL", "works.Work")
    app_label, model_name = model_path.split(".", 1)
    return apps.get_model(app_label, model_name)


def list_characters(work):
    characters = list(CharacterProfile.objects.filter(work=work))
    return sorted(characters, key=lambda c: (ROLE_ORDER.get(c.role, 99), c.name))


def create_character(work, data: dict) -> CharacterProfile:
    if CharacterProfile.objects.filter(work=work).count() >= CHARACTER_LIMIT_PER_WORK:
        raise ValidationError(f"작품당 캐릭터는 최대 {CHARACTER_LIMIT_PER_WORK}명까지 등록할 수 있습니다.")

    character = CharacterProfile(
        work=work,
        name=(data.get("name") or "").strip(),
        age=(data.get("age") or "").strip(),
        role=(data.get("role") or "").strip(),
        gender=(data.get("gender") or "").strip(),
        relation=(data.get("relation") or "").strip(),
        appearance=(data.get("appearance") or "").strip(),
        detail=(data.get("detail") or "").strip(),
        source=CharacterProfile.SOURCE_MANUAL,
    )
    character.full_clean()
    character.save()
    return character


def update_character(character: CharacterProfile, data: dict) -> CharacterProfile:
    for field in ["name", "age", "role", "gender", "relation", "appearance", "detail"]:
        if field in data:
            setattr(character, field, (data.get(field) or "").strip())
    character.source = CharacterProfile.SOURCE_MANUAL
    character.full_clean()
    character.save()
    return character

