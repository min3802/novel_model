"""Minimal JSON API for the Next.js frontend.

Standard-library HTTP server — no FastAPI/uvicorn needed.
In-memory storage resets on restart (MVP/demo grade).
"""

from __future__ import annotations

import io
import json
import os
import re
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from dotenv import load_dotenv
from backend.services.cover_plan_service import cover_plan
from backend.services.glossary_api_service import (
    approve_glossary_candidate_handler,
    delete_or_deprecate_glossary_entry_handler,
    get_glossary_repository_status_handler,
    list_glossary_candidates_handler,
    list_glossary_entries_handler,
    reject_glossary_candidate_handler,
    upsert_glossary_entry_handler,
)
from backend.services.content_api_service import (
    archive_episode_handler,
    archive_work_handler,
    get_content_repository_status_handler,
    get_episode_handler,
    get_latest_translation_handler,
    get_translation_handler,
    get_work_handler,
    list_episodes_handler,
    list_translations_handler,
    list_works_handler,
    upsert_episode_handler,
    upsert_work_handler,
)
from backend.services.guide_service import guide
from backend.services.image_service import cover_image, relation_image, visual_prompt
from backend.services.translation_service import inspect_chat, translate

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# URL patterns for dynamic segments
_WORK_RE = re.compile(r"^/api/works/(\d+)$")
_EP_RE = re.compile(r"^/api/works/(\d+)/episodes$")
_EP_ITEM_RE = re.compile(r"^/api/works/(\d+)/episodes/(\d+)$")
_EP_TRANSLATIONS_RE = re.compile(r"^/api/works/(\d+)/episodes/(\d+)/translations$")
_EP_TRANSLATIONS_LATEST_RE = re.compile(r"^/api/works/(\d+)/episodes/(\d+)/translations/latest$")
_TRANSLATION_RE = re.compile(r"^/api/translations/(\d+)$")
_TRANSLATION_APPLY_CHAT_RE = re.compile(r"^/api/translations/(\d+)/apply-chat-suggestion$")
_TRANSLATION_CHAT_RE = re.compile(r"^/api/translations/(\d+)/chat$")
_WORK_COVER_PLAN_RE = re.compile(r"^/api/works/(\d+)/cover-plan$")
_ASSETS_RE = re.compile(r"^/api/generated-assets$")
_ASSET_RE = re.compile(r"^/api/generated-assets/(\d+)$")
_GUIDES_RE = re.compile(r"^/api/localization-guides$")
_GUIDE_RE = re.compile(r"^/api/localization-guides/(\d+)$")
_GUIDE_PDF_RE = re.compile(r"^/api/localization-guides/(\d+)/pdf$")
_CONTENT_REPOSITORY_STATUS_RE = re.compile(r"^/api/content/repository-status$")
_GLOSSARY_REPOSITORY_STATUS_RE = re.compile(r"^/api/glossary/repository-status$")
_GLOSSARY_CANDIDATES_RE = re.compile(r"^/api/works/([^/]+)/glossary/candidates$")
_GLOSSARY_CANDIDATE_APPROVE_RE = re.compile(r"^/api/works/([^/]+)/glossary/candidates/(\d+)/approve$")
_GLOSSARY_CANDIDATE_REJECT_RE = re.compile(r"^/api/works/([^/]+)/glossary/candidates/(\d+)/reject$")
_GLOSSARY_ENTRIES_RE = re.compile(r"^/api/works/([^/]+)/glossary/entries$")
_GLOSSARY_ENTRY_RE = re.compile(r"^/api/works/([^/]+)/glossary/entries/(\d+)$")

from backend.store.memory_store import (
    apply_chat_suggestion,
    dashboard_summary,
    episode_create,
    episode_delete,
    episode_update,
    episodes_list,
    generated_asset_delete,
    generated_asset_get,
    generated_assets_list,
    localization_guide_delete,
    localization_guide_get,
    localization_guides_list,
    save_generated_asset,
    save_localization_guide,
    translation_chat_add,
    translation_chat_list,
    translation_version_delete,
    translation_version_get,
    translation_versions_list,
    work_create,
    work_delete,
    work_get,
    work_update,
    works_list,
)


# ---------------------------------------------------------------------------
# AI pipeline helpers (unchanged)
# ---------------------------------------------------------------------------

def _json_default(value: Any) -> Any:
    try:
        return asdict(value)
    except Exception:
        return str(value)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:80] or "localization-guide"


def _pdf_escape(value: str) -> str:
    return value.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _guide_pdf_lines(guide: dict[str, Any], guide_id: int) -> list[str]:
    result = guide.get("guide") if isinstance(guide.get("guide"), dict) else guide
    title = str(result.get("title") or f"현지화 가이드 #{guide_id}")
    country = str(result.get("targetCountryDisplay") or result.get("displayCountry") or result.get("targetCountry") or result.get("country") or "미선택")
    genre = str(result.get("genre") or "미지정")
    created_at = str(result.get("createdAt") or guide.get("created_at") or "")
    lines = [
        title,
        "",
        f"대상 국가: {country}",
        f"장르: {genre}",
    ]
    if created_at:
        lines.append(f"생성 시각: {created_at}")
    if result.get("summary_text"):
        lines.extend(["", f"요약: {result['summary_text']}"])
    if result.get("recommended_country"):
        lines.append(f"추천 국가: {result.get('recommended_country_display') or result.get('recommended_country')}")
    if result.get("recommendation_reasons"):
        lines.extend(["", "추천 사유:"])
        for reason in result.get("recommendation_reasons") or []:
            lines.append(f"- {reason}")
    if result.get("limitation_notice"):
        lines.extend(["", f"제약 안내: {result['limitation_notice']}"])
    if result.get("translation_profile"):
        profile = result["translation_profile"] or {}
        lines.extend(["", "번역/표현 방향:"])
        for key, label in [
            ("tone", "톤"),
            ("dialogue_style", "대사"),
            ("narration_style", "서술"),
            ("localization_level", "현지화 수준"),
            ("proper_noun_policy", "고유명사"),
            ("culture_policy", "문화 요소"),
        ]:
            if profile.get(key):
                lines.append(f"- {label}: {profile[key]}")
        if profile.get("do_not"):
            lines.append(f"- 제외: {'; '.join(profile['do_not'])}")
    if result.get("sections"):
        lines.extend(["", "현지화 기준서 섹션:"])
        section_order = [
            "market_trend_fit",
            "genre_trope_alignment",
            "title_synopsis_localization",
            "terminology_glossary_risks",
            "content_rating_sensitivity",
            "adaptation_checklist",
            "evidence_used",
        ]
        sections = result.get("sections") or {}
        ordered = [key for key in section_order if key in sections] + [key for key in sections if key not in section_order]
        for key in ordered:
            section = sections[key] or {}
            lines.append(f"[{section.get('title') or key}]")
            for item in section.get("items") or []:
                lines.append(f"- {item}")
            lines.append("")
    if result.get("storageNotice"):
        notice = result["storageNotice"] or {}
        if notice.get("message"):
            lines.extend(["", f"보관 안내: {notice['message']}"])
    return [line for line in lines if line is not None]


def _load_pdf_font(size: int = 28):
    from PIL import ImageFont

    candidates = [
        r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\malgunbd.ttf",
        r"C:\Windows\Fonts\Arial Unicode.ttf",
        r"C:\Windows\Fonts\arialuni.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _build_pdf_bytes(lines: list[str]) -> bytes:
    from PIL import Image, ImageDraw

    page_width, page_height = 1240, 1754
    margin_x, margin_y = 84, 80
    font_title = _load_pdf_font(30)
    font_body = _load_pdf_font(22)

    pages = []
    current = Image.new("RGB", (page_width, page_height), "white")
    draw = ImageDraw.Draw(current)
    y = margin_y

    def flush_page(image: Image.Image) -> None:
        pages.append(image.convert("RGB"))

    def new_page() -> tuple[Image.Image, Any, int]:
        img = Image.new("RGB", (page_width, page_height), "white")
        return img, ImageDraw.Draw(img), margin_y

    current, draw, y = new_page()
    is_title_page = True
    for raw_line in lines:
        line = str(raw_line or "")
        if not line:
            y += 14
            continue
        if len(line) > 48:
            words = re.findall(r"\S+\s*", line)
            wrapped: list[str] = []
            buffer = ""
            for word in words:
                if len(buffer + word) > 48 and buffer:
                    wrapped.append(buffer.rstrip())
                    buffer = word
                else:
                    buffer += word
            if buffer:
                wrapped.append(buffer.rstrip())
        else:
            wrapped = [line]
        for segment in wrapped:
            font = font_title if is_title_page else font_body
            line_height = 40 if is_title_page else 32
            if y + line_height > page_height - margin_y:
                flush_page(current)
                current, draw, y = new_page()
                is_title_page = False
                font = font_body
                line_height = 32
            draw.text((margin_x, y), segment, fill="black", font=font)
            y += line_height
        is_title_page = False
    flush_page(current)

    output = io.BytesIO()
    if len(pages) == 1:
        pages[0].save(output, format="PDF")
    else:
        pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:])
    return output.getvalue()


def _send_binary(handler: BaseHTTPRequestHandler, status: int, body: bytes, *, content_type: str, filename: str | None = None) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)
    handler.wfile.flush()


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def _query_params(path: str) -> dict[str, str]:
    query = path.split("?", 1)[1] if "?" in path else ""
    params = parse_qs(query, keep_blank_values=True)
    return {key: values[-1] for key, values in params.items() if values}





# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ApiHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, {})

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            if path == "/api/health":
                self._send(200, {"ok": True, "service": "wlighter-api"})
            elif path == "/api/dashboard-summary":
                self._send(200, dashboard_summary())
            elif _CONTENT_REPOSITORY_STATUS_RE.match(path):
                result = get_content_repository_status_handler()
                self._send(int(result.get("status") or 200), result)
            elif path == "/api/works":
                result = list_works_handler(_query_params(self.path))
                self._send(int(result.get("status") or 200), result)
            elif m := _WORK_RE.match(path):
                wid = int(m.group(1))
                result = get_work_handler({"workId": wid})
                self._send(int(result.get("status") or 200), result)
            elif m := _EP_RE.match(path):
                wid = int(m.group(1))
                result = list_episodes_handler({"workId": wid, **_query_params(self.path)})
                self._send(int(result.get("status") or 200), result)
            elif m := _EP_ITEM_RE.match(path):
                wid, eid = map(int, m.groups())
                result = get_episode_handler({"workId": wid, "episodeId": eid})
                self._send(int(result.get("status") or 200), result)
            elif m := _EP_TRANSLATIONS_LATEST_RE.match(path):
                wid, eid = map(int, m.groups())
                params = _query_params(self.path)
                result = get_latest_translation_handler({"workId": wid, "episodeId": eid, **params})
                self._send(int(result.get("status") or 200), result)
            elif m := _EP_TRANSLATIONS_RE.match(path):
                wid, eid = map(int, m.groups())
                params = _query_params(self.path)
                result = list_translations_handler({"workId": wid, "episodeId": eid, **params})
                self._send(int(result.get("status") or 200), result)
            elif m := _TRANSLATION_CHAT_RE.match(path):
                tid = int(m.group(1))
                self._send(200, {"messages": translation_chat_list(tid)})
            elif m := _TRANSLATION_RE.match(path):
                tid = int(m.group(1))
                result = get_translation_handler({"translationId": tid})
                self._send(int(result.get("status") or 200), result)
            elif _ASSETS_RE.match(path):
                query = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
                kind = params.get("kind")
                work_id = int(params["workId"]) if params.get("workId") else None
                self._send(200, {"assets": generated_assets_list(kind=kind, work_id=work_id)})
            elif m := _ASSET_RE.match(path):
                aid = int(m.group(1))
                self._send(200, {"asset": generated_asset_get(aid)})
            elif _GUIDES_RE.match(path):
                query = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
                work_id = int(params["workId"]) if params.get("workId") else None
                self._send(200, {"guides": localization_guides_list(work_id=work_id)})
            elif m := _GUIDE_PDF_RE.match(path):
                gid = int(m.group(1))
                record = localization_guide_get(gid)
                guide = record.get("guide") if isinstance(record.get("guide"), dict) else record
                pdf_bytes = _build_pdf_bytes(_guide_pdf_lines(guide, gid))
                filename = f"localization-guide-{gid}.pdf"
                _send_binary(self, 200, pdf_bytes, content_type="application/pdf", filename=filename)
            elif m := _GUIDE_RE.match(path):
                gid = int(m.group(1))
                self._send(200, {"guide": localization_guide_get(gid)})
            elif _GLOSSARY_REPOSITORY_STATUS_RE.match(path):
                self._send(200, get_glossary_repository_status_handler())
            elif m := _GLOSSARY_CANDIDATES_RE.match(path):
                work_id = m.group(1)
                params = _query_params(self.path)
                result = list_glossary_candidates_handler(
                    {
                        "workId": work_id,
                        "targetCountry": params.get("targetCountry") or params.get("target_country"),
                        "targetLocale": params.get("targetLocale") or params.get("target_locale"),
                        "status": params.get("status"),
                    }
                )
                self._send(int(result.get("status") or 200), result)
            elif m := _GLOSSARY_ENTRIES_RE.match(path):
                work_id = m.group(1)
                params = _query_params(self.path)
                result = list_glossary_entries_handler(
                    {
                        "workId": work_id,
                        "targetCountry": params.get("targetCountry") or params.get("target_country"),
                        "targetLocale": params.get("targetLocale") or params.get("target_locale"),
                    }
                )
                self._send(int(result.get("status") or 200), result)
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            payload = _read_json(self)
            if path == "/api/translate":
                result = translate(payload)
                self._send(int(result.get("status") or 200), result)
            elif path == "/api/guide":
                result = guide(payload)
                result = dict(result)
                if not result.get("requiresSelection"):
                    saved = save_localization_guide(payload, result)
                    result["guideRecord"] = saved
                    if saved.get("storage_notice"):
                        result["storageNotice"] = saved["storage_notice"]
                self._send(200, result)
            elif path == "/api/inspect-chat":
                result = inspect_chat(payload)
                self._send(int(result.get("status") or 200), result)
            elif path == "/api/cover-prompt":
                self._send(200, visual_prompt(payload, "cover"))
            elif path == "/api/relation-prompt":
                self._send(200, visual_prompt(payload, "relation"))
            elif path == "/api/generate-cover-image":
                result = cover_image(payload)
                if not result.get("refusal"):
                    result = dict(result)
                    result["assetRecord"] = save_generated_asset("cover", payload, result)
                self._send(200, result)
            elif path == "/api/generate-relation-image":
                result = relation_image(payload)
                if not result.get("refusal"):
                    result = dict(result)
                    result["assetRecord"] = save_generated_asset("relation", payload, result)
                self._send(200, result)
            elif path == "/api/works":
                result = upsert_work_handler(payload)
                self._send(int(result.get("status") or 201), result)
            elif m := _WORK_COVER_PLAN_RE.match(path):
                wid = int(m.group(1))
                self._send(200, cover_plan(wid, payload))
            elif m := _TRANSLATION_APPLY_CHAT_RE.match(path):
                tid = int(m.group(1))
                self._send(200, {"translation": apply_chat_suggestion(tid, payload)})
            elif m := _TRANSLATION_CHAT_RE.match(path):
                tid = int(m.group(1))
                self._send(201, translation_chat_add(tid, payload))
            elif m := _EP_RE.match(path):
                wid = int(m.group(1))
                result = upsert_episode_handler({**payload, "workId": wid})
                self._send(int(result.get("status") or 201), result)
            elif m := _GLOSSARY_CANDIDATE_APPROVE_RE.match(path):
                work_id = m.group(1)
                candidate_id = m.group(2)
                result = approve_glossary_candidate_handler({**payload, "workId": work_id, "candidateId": candidate_id})
                self._send(int(result.get("status") or 200), result)
            elif m := _GLOSSARY_CANDIDATE_REJECT_RE.match(path):
                work_id = m.group(1)
                candidate_id = m.group(2)
                result = reject_glossary_candidate_handler({**payload, "workId": work_id, "candidateId": candidate_id})
                self._send(int(result.get("status") or 200), result)
            elif m := _GLOSSARY_ENTRIES_RE.match(path):
                work_id = m.group(1)
                params = _query_params(self.path)
                result = upsert_glossary_entry_handler(
                    {
                        **payload,
                        "workId": work_id,
                        "targetCountry": payload.get("targetCountry")
                        or payload.get("target_country")
                        or params.get("targetCountry")
                        or params.get("target_country"),
                        "targetLocale": payload.get("targetLocale")
                        or payload.get("target_locale")
                        or params.get("targetLocale")
                        or params.get("target_locale"),
                    }
                )
                self._send(int(result.get("status") or 200), result)
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def do_PATCH(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            payload = _read_json(self)
            if m := _WORK_RE.match(path):
                wid = int(m.group(1))
                result = upsert_work_handler({**payload, "workId": wid})
                self._send(int(result.get("status") or 200), result)
            elif m := _EP_ITEM_RE.match(path):
                wid, eid = map(int, m.groups())
                result = upsert_episode_handler({**payload, "workId": wid, "episodeId": eid})
                self._send(int(result.get("status") or 200), result)
            elif m := _GLOSSARY_ENTRY_RE.match(path):
                work_id = m.group(1)
                entry_id = m.group(2)
                params = _query_params(self.path)
                result = upsert_glossary_entry_handler(
                    {
                        **payload,
                        "workId": work_id,
                        "entryId": entry_id,
                        "targetCountry": payload.get("targetCountry")
                        or payload.get("target_country")
                        or params.get("targetCountry")
                        or params.get("target_country"),
                        "targetLocale": payload.get("targetLocale")
                        or payload.get("target_locale")
                        or params.get("targetLocale")
                        or params.get("target_locale"),
                    }
                )
                self._send(int(result.get("status") or 200), result)
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def do_PUT(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            payload = _read_json(self)
            if m := _EP_ITEM_RE.match(path):
                wid, eid = map(int, m.groups())
                result = upsert_episode_handler({**payload, "workId": wid, "episodeId": eid})
                self._send(int(result.get("status") or 200), result)
            elif m := _WORK_RE.match(path):
                wid = int(m.group(1))
                result = upsert_work_handler({**payload, "workId": wid})
                self._send(int(result.get("status") or 200), result)
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def do_DELETE(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            payload = _read_json(self)
            if m := _EP_ITEM_RE.match(path):
                wid, eid = map(int, m.groups())
                result = archive_episode_handler({"workId": wid, "episodeId": eid})
                self._send(int(result.get("status") or 200), result)
            elif m := _WORK_RE.match(path):
                wid = int(m.group(1))
                result = archive_work_handler({"workId": wid})
                self._send(int(result.get("status") or 200), result)
            elif m := _ASSET_RE.match(path):
                aid = int(m.group(1))
                self._send(200, generated_asset_delete(aid))
            elif m := _GUIDE_RE.match(path):
                gid = int(m.group(1))
                self._send(200, localization_guide_delete(gid))
            elif m := _TRANSLATION_RE.match(path):
                tid = int(m.group(1))
                self._send(405, {"ok": False, "errorCode": "method_not_allowed"})
            elif m := _GLOSSARY_ENTRY_RE.match(path):
                work_id = m.group(1)
                entry_id = m.group(2)
                params = _query_params(self.path)
                result = delete_or_deprecate_glossary_entry_handler(
                    {
                        "workId": work_id,
                        "targetCountry": params.get("targetCountry")
                        or params.get("target_country")
                        or payload.get("targetCountry")
                        or payload.get("target_country"),
                        "targetLocale": params.get("targetLocale")
                        or params.get("target_locale")
                        or payload.get("targetLocale")
                        or payload.get("target_locale"),
                        "entryId": entry_id,
                    }
                )
                self._send(int(result.get("status") or 200), result)
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    host = os.getenv("WLIGHTER_API_HOST", "127.0.0.1")
    port = int(os.getenv("WLIGHTER_API_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), ApiHandler)
    print(f"w.LiGHTER API listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
