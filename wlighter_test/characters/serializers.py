from .models import CharacterProfile


def character_to_dict(character: CharacterProfile) -> dict:
    return {
        "id": character.id,
        "work_id": character.work_id,
        "name": character.name,
        "age": character.age,
        "role": character.role,
        "gender": character.gender,
        "relation": character.relation,
        "appearance": character.appearance,
        "detail": character.detail,
        "source": character.source,
        "created_at": character.created_at.isoformat() if character.created_at else None,
        "updated_at": character.updated_at.isoformat() if character.updated_at else None,
    }

