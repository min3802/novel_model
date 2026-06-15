import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import CharacterProfile
from .serializers import character_to_dict
from .services.character_extractor import extract_character_settings
from .services.character_service import create_character, get_work_model, list_characters, update_character


def parse_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("요청 본문은 JSON 형식이어야 합니다.") from exc


def ok(data: dict, status: int = 200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def fail(exc: Exception, status: int = 400):
    return ok({"ok": False, "error": str(exc)}, status=status)


def get_work_or_404(work_id):
    return get_object_or_404(get_work_model(), pk=work_id)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def character_collection(request, work_id):
    work = get_work_or_404(work_id)
    try:
        if request.method == "GET":
            return ok({"ok": True, "characters": [character_to_dict(c) for c in list_characters(work)]})
        character = create_character(work, parse_body(request))
        return ok({"ok": True, "character": character_to_dict(character)}, status=201)
    except Exception as exc:
        return fail(exc)


@csrf_exempt
@require_http_methods(["POST"])
def character_extract(request, work_id):
    work = get_work_or_404(work_id)
    try:
        data = parse_body(request)
        characters = extract_character_settings(work, synopsis=data.get("synopsis"), save=data.get("save", True))
        if characters and isinstance(characters[0], CharacterProfile):
            characters = [character_to_dict(c) for c in characters]
        return ok({"ok": True, "characters": characters})
    except Exception as exc:
        return fail(exc)


@csrf_exempt
@require_http_methods(["GET", "PATCH", "DELETE"])
def character_detail(request, character_id):
    character = get_object_or_404(CharacterProfile, pk=character_id)
    try:
        if request.method == "GET":
            return ok({"ok": True, "character": character_to_dict(character)})
        if request.method == "DELETE":
            character.delete()
            return ok({"ok": True})
        character = update_character(character, parse_body(request))
        return ok({"ok": True, "character": character_to_dict(character)})
    except Exception as exc:
        return fail(exc)

