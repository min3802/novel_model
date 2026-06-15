import json

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import CoverImage, RelationshipMap
from .serializers import cover_image_to_dict, relationship_map_to_dict
from .services.image_generator import generate_cover_image
from .services.pdf_export import relationship_html_to_pdf_bytes
from .services.relation_extractor import extract_relation_data
from .services.relation_html_generator import generate_relationship_map


def get_work_model():
    model_path = getattr(settings, "WLIGHTER_WORK_MODEL", "works.Work")
    app_label, model_name = model_path.split(".", 1)
    return apps.get_model(app_label, model_name)


def get_work_or_404(work_id):
    return get_object_or_404(get_work_model(), pk=work_id)


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


@csrf_exempt
@require_http_methods(["GET", "POST"])
def cover_collection(request, work_id):
    work = get_work_or_404(work_id)
    try:
        if request.method == "GET":
            images = CoverImage.objects.filter(work=work)
            return ok({"ok": True, "images": [cover_image_to_dict(image) for image in images]})
        data = parse_body(request)
        image = generate_cover_image(work, data.get("target_country", "US"), data.get("extra_prompt", ""))
        return ok({"ok": True, "image": cover_image_to_dict(image)}, status=201)
    except Exception as exc:
        return fail(exc)


@csrf_exempt
@require_http_methods(["DELETE"])
def cover_delete(request, image_id):
    image = get_object_or_404(CoverImage, pk=image_id)
    image.delete()
    return ok({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def relation_extract(request, work_id):
    work = get_work_or_404(work_id)
    try:
        data = parse_body(request)
        return ok({"ok": True, "relation_data": extract_relation_data(work, character_ids=data.get("character_ids") or [])})
    except Exception as exc:
        return fail(exc)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def relation_map_collection(request, work_id):
    work = get_work_or_404(work_id)
    try:
        if request.method == "GET":
            maps = RelationshipMap.objects.filter(work=work)
            return ok({"ok": True, "relation_maps": [relationship_map_to_dict(item) for item in maps]})
        data = parse_body(request)
        relation_map = generate_relationship_map(work, data.get("title", ""), character_ids=data.get("character_ids") or [])
        return ok({"ok": True, "relation_map": relationship_map_to_dict(relation_map, include_html=True)}, status=201)
    except Exception as exc:
        return fail(exc)


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def relation_map_detail(request, relation_map_id):
    relation_map = get_object_or_404(RelationshipMap, pk=relation_map_id)
    if request.method == "DELETE":
        relation_map.delete()
        return ok({"ok": True})
    return ok({"ok": True, "relation_map": relationship_map_to_dict(relation_map, include_html=True)})


@require_http_methods(["GET"])
def relation_map_html(request, relation_map_id):
    relation_map = get_object_or_404(RelationshipMap, pk=relation_map_id)
    return HttpResponse(relation_map.html_content, content_type="text/html; charset=utf-8")


@require_http_methods(["GET"])
def relation_map_pdf(request, relation_map_id):
    relation_map = get_object_or_404(RelationshipMap, pk=relation_map_id)
    try:
        pdf_bytes = relationship_html_to_pdf_bytes(relation_map.html_content)
    except Exception as exc:
        return fail(exc, status=501)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="relationship_map_{relation_map.id}.pdf"'
    return response
