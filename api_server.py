"""Minimal JSON API for the Next.js frontend.

Standard-library HTTP server — no FastAPI/uvicorn needed.
In-memory storage resets on restart (MVP/demo grade).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from dotenv import load_dotenv
from backend.services.cover_plan_service import cover_plan
from backend.services.guide_service import guide
from backend.services.image_service import cover_image, relation_image, visual_prompt
from backend.services.translation_service import inspect_chat, translate, work_memory_extract, work_memory_get, work_memory_update

load_dotenv()

# URL patterns for dynamic segments
_WORK_RE = re.compile(r"^/api/works/(\d+)$")
_EP_RE = re.compile(r"^/api/works/(\d+)/episodes$")
_EP_ITEM_RE = re.compile(r"^/api/works/(\d+)/episodes/(\d+)$")
_EP_TRANSLATIONS_RE = re.compile(r"^/api/works/(\d+)/episodes/(\d+)/translations$")
_TRANSLATION_RE = re.compile(r"^/api/translations/(\d+)$")
_TRANSLATION_APPLY_CHAT_RE = re.compile(r"^/api/translations/(\d+)/apply-chat-suggestion$")
_TRANSLATION_CHAT_RE = re.compile(r"^/api/translations/(\d+)/chat$")
_WORK_MEMORY_RE = re.compile(r"^/api/works/(\d+)/memory$")
_WORK_MEMORY_EXTRACT_RE = re.compile(r"^/api/works/(\d+)/memory/extract$")
_WORK_COVER_PLAN_RE = re.compile(r"^/api/works/(\d+)/cover-plan$")
_ASSETS_RE = re.compile(r"^/api/generated-assets$")
_ASSET_RE = re.compile(r"^/api/generated-assets/(\d+)$")
_GUIDES_RE = re.compile(r"^/api/localization-guides$")
_GUIDE_RE = re.compile(r"^/api/localization-guides/(\d+)$")

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


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")





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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
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
            elif path == "/api/works":
                self._send(200, {"works": works_list()})
            elif m := _WORK_MEMORY_RE.match(path):
                wid = int(m.group(1))
                self._send(200, {"memory": work_memory_get(wid)})
            elif m := _WORK_RE.match(path):
                wid = int(m.group(1))
                work = work_get(wid)
                if work:
                    eps = episodes_list(wid)
                    self._send(200, {"work": work, "episodeCount": len(eps)})
                else:
                    self._send(404, {"error": "work not found"})
            elif m := _EP_RE.match(path):
                wid = int(m.group(1))
                self._send(200, {"episodes": episodes_list(wid)})
            elif m := _EP_ITEM_RE.match(path):
                wid, eid = map(int, m.groups())
                episode = next((row for row in episodes_list(wid) if row["id"] == eid), None)
                if episode:
                    self._send(200, {"episode": episode})
                else:
                    self._send(404, {"error": "episode not found"})
            elif m := _EP_TRANSLATIONS_RE.match(path):
                wid, eid = map(int, m.groups())
                query = self.path.split("?", 1)[1] if "?" in self.path else ""
                locale = None
                for part in query.split("&"):
                    if part.startswith("locale="):
                        locale = part.split("=", 1)[1]
                self._send(200, {"translations": translation_versions_list(wid, eid, locale=locale)})
            elif m := _TRANSLATION_CHAT_RE.match(path):
                tid = int(m.group(1))
                self._send(200, {"messages": translation_chat_list(tid)})
            elif m := _TRANSLATION_RE.match(path):
                tid = int(m.group(1))
                self._send(200, {"translation": translation_version_get(tid)})
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
            elif m := _GUIDE_RE.match(path):
                gid = int(m.group(1))
                self._send(200, {"guide": localization_guide_get(gid)})
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            payload = _read_json(self)
            if path == "/api/translate":
                self._send(200, translate(payload))
            elif path == "/api/guide":
                result = guide(payload)
                saved = save_localization_guide(payload, result)
                result = dict(result)
                result["guideRecord"] = saved
                self._send(200, result)
            elif path == "/api/inspect-chat":
                self._send(200, inspect_chat(payload))
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
                self._send(201, work_create(payload))
            elif m := _WORK_MEMORY_EXTRACT_RE.match(path):
                wid = int(m.group(1))
                self._send(200, work_memory_extract(wid, payload))
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
                self._send(201, episode_create(wid, payload))
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
                self._send(200, episode_update(wid, eid, payload))
            elif m := _WORK_RE.match(path):
                wid = int(m.group(1))
                self._send(200, work_update(wid, payload))
            elif m := _WORK_MEMORY_RE.match(path):
                wid = int(m.group(1))
                self._send(200, {"memory": work_memory_update(wid, payload)})
            else:
                self._send(404, {"error": "not found"})
        except Exception as exc:
            self._send(400, {"error": str(exc)})

    def do_DELETE(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        try:
            if m := _EP_ITEM_RE.match(path):
                wid, eid = map(int, m.groups())
                self._send(200, episode_delete(wid, eid))
            elif m := _WORK_RE.match(path):
                wid = int(m.group(1))
                work_delete(wid)
                self._send(200, {"ok": True})
            elif m := _ASSET_RE.match(path):
                aid = int(m.group(1))
                self._send(200, generated_asset_delete(aid))
            elif m := _GUIDE_RE.match(path):
                gid = int(m.group(1))
                self._send(200, localization_guide_delete(gid))
            elif m := _TRANSLATION_RE.match(path):
                tid = int(m.group(1))
                self._send(200, translation_version_delete(tid))
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
