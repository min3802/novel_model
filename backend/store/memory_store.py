"""Thread-safe in-memory repository for the MVP API.

This isolates demo persistence from the HTTP router and feature services.
The store intentionally remains process-local and resets on restart.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# In-memory storage (thread-safe)
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_works: list[dict[str, Any]] = []
_episodes: list[dict[str, Any]] = []
_translation_versions: list[dict[str, Any]] = []
_chat_messages: list[dict[str, Any]] = []
_cover_plans: list[dict[str, Any]] = []
_generated_assets: list[dict[str, Any]] = []
_localization_guides: list[dict[str, Any]] = []
_next_work_id = 1
_next_episode_id = 1
_next_translation_id = 1
_next_chat_id = 1
_next_cover_plan_id = 1
_next_asset_id = 1
_next_guide_id = 1

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _get_work(work_id: int) -> dict[str, Any] | None:
    for w in _works:
        if w["id"] == work_id:
            return w
    return None


def works_list() -> list[dict[str, Any]]:
    with _lock:
        rows: list[dict[str, Any]] = []
        for w in _works:
            work = dict(w)
            work["episode_count"] = sum(1 for e in _episodes if e["work_id"] == w["id"])
            rows.append(work)
        return rows


def dashboard_summary() -> dict[str, int]:
    with _lock:
        return {
            "workCount": len(_works),
            "episodeCount": len(_episodes),
            "guideCount": len(_localization_guides),
        }


def work_create(payload: dict[str, Any]) -> dict[str, Any]:
    global _next_work_id
    title = (payload.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    with _lock:
        wid = _next_work_id
        _next_work_id += 1
        work = {
            "id": wid,
            "title": title,
            "pen_name": (payload.get("pen_name") or "").strip() or "작가",
            "genre": payload.get("genre") or "미선택",
            "desc": (payload.get("desc") or "").strip(),
            "status": "회차 등록 필요",
            "created_at": datetime.now().strftime("%Y-%m-%d"),
        }
        _works.append(work)
        return dict(work)


def work_update(work_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        work = _get_work(work_id)
        if not work:
            raise ValueError(f"work {work_id} not found")

        title = (payload.get("title") or work["title"]).strip()
        if not title:
            raise ValueError("title is required")

        work["title"] = title
        work["pen_name"] = (payload.get("pen_name") or work.get("pen_name") or "작가").strip() or "작가"
        work["genre"] = payload.get("genre") or work.get("genre") or "미선택"
        work["desc"] = (payload.get("desc") or work.get("desc") or "").strip()

        status = (payload.get("status") or work.get("status") or "").strip()
        if status:
            work["status"] = status
        return dict(work)


def work_delete(work_id: int) -> None:
    global _works, _episodes, _translation_versions, _chat_messages, _cover_plans, _generated_assets, _localization_guides
    with _lock:
        work = _get_work(work_id)
        if not work:
            raise ValueError(f"work {work_id} not found")
        translation_ids = {
            row["id"] for row in _translation_versions if row.get("work_id") == work_id
        }
        _works = [w for w in _works if w["id"] != work_id]
        _episodes = [e for e in _episodes if e["work_id"] != work_id]
        _translation_versions = [row for row in _translation_versions if row.get("work_id") != work_id]
        _chat_messages = [row for row in _chat_messages if row.get("translation_id") not in translation_ids]
        _cover_plans = [row for row in _cover_plans if row.get("work_id") != work_id]
        _generated_assets = [row for row in _generated_assets if row.get("work_id") != work_id]
        _localization_guides = [row for row in _localization_guides if row.get("work_id") != work_id]


def work_get(work_id: int) -> dict[str, Any] | None:
    with _lock:
        w = _get_work(work_id)
        return dict(w) if w else None


def episodes_list(work_id: int) -> list[dict[str, Any]]:
    with _lock:
        return [dict(e) for e in _episodes if e["work_id"] == work_id]


def _get_episode(work_id: int, episode_id: int) -> dict[str, Any] | None:
    for ep in _episodes:
        if ep["work_id"] == work_id and ep["id"] == episode_id:
            return ep
    return None


def episode_create(work_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    global _next_episode_id
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if not title:
        raise ValueError("title is required")
    if not body:
        raise ValueError("body is required")
    with _lock:
        work = _get_work(work_id)
        if not work:
            raise ValueError(f"work {work_id} not found")
        now = datetime.now().strftime("%Y-%m-%d")
        eid = _next_episode_id
        _next_episode_id += 1
        ep = {
            "id": eid,
            "work_id": work_id,
            "title": title,
            "body": body,
            "status": "번역 전",
            "created_at": now,
            "updated_at": now,
        }
        _episodes.append(ep)
        work["status"] = "번역 가능"
        work["recent_episode_at"] = now
        return dict(ep)



def episode_update(work_id: int, episode_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > 30:
        raise ValueError("title must be 30 characters or fewer")
    if not body:
        raise ValueError("body is required")
    if len(body) > 8000:
        raise ValueError("body must be 8000 characters or fewer")
    with _lock:
        ep = _get_episode(work_id, episode_id)
        if not ep:
            raise ValueError(f"episode {episode_id} not found for work {work_id}")
        ep["title"] = title
        ep["body"] = body
        ep["updated_at"] = datetime.now().strftime("%Y-%m-%d")
        return dict(ep)


def episode_delete(work_id: int, episode_id: int) -> dict[str, Any]:
    global _episodes, _translation_versions, _chat_messages
    with _lock:
        ep = _get_episode(work_id, episode_id)
        if not ep:
            raise ValueError(f"episode {episode_id} not found for work {work_id}")
        translation_ids = {
            row["id"]
            for row in _translation_versions
            if row.get("work_id") == work_id and row.get("episode_id") == episode_id
        }
        _episodes = [row for row in _episodes if not (row["work_id"] == work_id and row["id"] == episode_id)]
        _translation_versions = [
            row for row in _translation_versions
            if not (row.get("work_id") == work_id and row.get("episode_id") == episode_id)
        ]
        _chat_messages = [row for row in _chat_messages if row.get("translation_id") not in translation_ids]
        return {"ok": True}

def _translation_public(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def translation_versions_list(work_id: int, episode_id: int, locale: str | None = None) -> list[dict[str, Any]]:
    with _lock:
        rows = [
            _translation_public(row)
            for row in _translation_versions
            if row["work_id"] == work_id and row["episode_id"] == episode_id
        ]
        if locale:
            rows = [row for row in rows if row["locale"] == locale]
        return sorted(rows, key=lambda row: (row["locale"], row["version_no"]))


def _get_translation_version(translation_id: int) -> dict[str, Any] | None:
    for row in _translation_versions:
        if row["id"] == translation_id:
            return row
    return None


def translation_version_get(translation_id: int) -> dict[str, Any]:
    with _lock:
        row = _get_translation_version(translation_id)
        if not row:
            raise ValueError(f"translation {translation_id} not found")
        return _translation_public(row)


def _save_translation_version_unlocked(
    *,
    work_id: int,
    episode_id: int,
    country: str,
    locale: str,
    source_text: str,
    final_translation: str,
    review_summary: str,
    workflow: dict[str, Any],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    global _next_translation_id, _translation_versions
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = [
        row
        for row in _translation_versions
        if row["work_id"] == work_id and row["episode_id"] == episode_id and row["locale"] == locale
    ]
    next_version = max([row["version_no"] for row in rows], default=0) + 1
    removed: list[dict[str, Any]] = []
    if len(rows) >= 3:
        oldest = sorted(rows, key=lambda row: row["created_at"])[0]
        removed.append(_translation_public(oldest))
        _translation_versions = [row for row in _translation_versions if row["id"] != oldest["id"]]
    record = {
        "id": _next_translation_id,
        "work_id": work_id,
        "episode_id": episode_id,
        "country": country,
        "locale": locale,
        "version_no": next_version,
        "sourceText": source_text,
        "finalTranslation": final_translation,
        "reviewSummary": review_summary,
        "workflow": workflow,
        "memory": memory,
        "created_at": now,
        "updated_at": now,
        "autoRemovedVersions": removed,
    }
    _next_translation_id += 1
    _translation_versions.append(record)
    return _translation_public(record)



def save_translation_version(
    *,
    work_id: int,
    episode_id: int,
    country: str,
    locale: str,
    source_text: str,
    final_translation: str,
    review_summary: str,
    workflow: dict[str, Any],
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    with _lock:
        return _save_translation_version_unlocked(
            work_id=work_id,
            episode_id=episode_id,
            country=country,
            locale=locale,
            source_text=source_text,
            final_translation=final_translation,
            review_summary=review_summary,
            workflow=workflow,
            memory=memory,
        )

def translation_version_delete(translation_id: int) -> dict[str, Any]:
    global _translation_versions, _chat_messages
    with _lock:
        row = _get_translation_version(translation_id)
        if not row:
            raise ValueError(f"translation {translation_id} not found")
        _translation_versions = [item for item in _translation_versions if item["id"] != translation_id]
        _chat_messages = [item for item in _chat_messages if item.get("translation_id") != translation_id]
        return {"ok": True}


def translation_chat_list(translation_id: int) -> list[dict[str, Any]]:
    with _lock:
        if not _get_translation_version(translation_id):
            raise ValueError(f"translation {translation_id} not found")
        return [
            dict(item)
            for item in sorted(_chat_messages, key=lambda row: row["created_at"])
            if item["translation_id"] == translation_id
        ]


def translation_chat_add(translation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    global _next_chat_id
    role = (payload.get("role") or "user").strip()
    content = (payload.get("content") or payload.get("message") or "").strip()
    if role not in {"user", "assistant"}:
        raise ValueError("role must be user or assistant")
    if not content:
        raise ValueError("content is required")
    if len(content) > 1000:
        raise ValueError("chat message must be 1000 characters or fewer")
    with _lock:
        if not _get_translation_version(translation_id):
            raise ValueError(f"translation {translation_id} not found")
        record = {
            "id": _next_chat_id,
            "translation_id": translation_id,
            "role": role,
            "content": content,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        _next_chat_id += 1
        _chat_messages.append(record)
        return dict(record)


def apply_chat_suggestion(translation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    suggestion = (payload.get("proposedTranslation") or payload.get("suggestion") or "").strip()
    if not suggestion:
        raise ValueError("proposedTranslation is required")
    with _lock:
        row = _get_translation_version(translation_id)
        if not row:
            raise ValueError(f"translation {translation_id} not found")
        row["finalTranslation"] = suggestion
        row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        row.setdefault("appliedChatSuggestions", []).append(
            {
                "proposedTranslation": suggestion,
                "reason": payload.get("reason") or payload.get("changeSummary") or "",
                "applied_at": row["updated_at"],
            }
        )
        workflow = row.get("workflow") or {}
        workflow["reviewed_translation"] = suggestion
        row["workflow"] = workflow
        return _translation_public(row)


def save_cover_plan(
    *,
    work_id: int,
    episode_ids: list[int],
    episode_summaries: list[dict[str, Any]],
    combined_summary: str,
    cover_brief: dict[str, Any],
    concepts: list[dict[str, Any]],
    recommended_concept_id: str,
    prompt: dict[str, Any],
) -> dict[str, Any]:
    global _next_cover_plan_id
    with _lock:
        record = {
            "id": _next_cover_plan_id,
            "work_id": work_id,
            "episodeIds": list(episode_ids),
            "episodeSummaries": list(episode_summaries),
            "combinedSummary": combined_summary,
            "coverBrief": dict(cover_brief),
            "concepts": list(concepts),
            "recommendedConceptId": recommended_concept_id,
            "prompt": dict(prompt),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        _next_cover_plan_id += 1
        _cover_plans.append(record)
        return dict(record)


def save_generated_asset(kind: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    global _next_asset_id
    work_id_raw = payload.get("workId") or payload.get("work_id")
    work_id = int(work_id_raw) if work_id_raw not in {None, ""} else None
    if work_id is not None and not _get_work(work_id):
        raise ValueError(f"work {work_id} not found")
    with _lock:
        record = {
            "id": _next_asset_id,
            "kind": kind,
            "work_id": work_id,
            "payload": dict(payload),
            "result": dict(result),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        _next_asset_id += 1
        _generated_assets.append(record)
        return dict(record)


def generated_assets_list(kind: str | None = None, work_id: int | None = None) -> list[dict[str, Any]]:
    with _lock:
        rows = [dict(row) for row in _generated_assets]
    if kind:
        rows = [row for row in rows if row.get("kind") == kind]
    if work_id is not None:
        rows = [row for row in rows if row.get("work_id") == work_id]
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)


def generated_asset_get(asset_id: int) -> dict[str, Any]:
    with _lock:
        for row in _generated_assets:
            if row["id"] == asset_id:
                return dict(row)
    raise ValueError(f"asset {asset_id} not found")


def generated_asset_delete(asset_id: int) -> dict[str, Any]:
    global _generated_assets
    with _lock:
        if not any(row["id"] == asset_id for row in _generated_assets):
            raise ValueError(f"asset {asset_id} not found")
        _generated_assets = [row for row in _generated_assets if row["id"] != asset_id]
        return {"ok": True}


def save_localization_guide(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    global _next_guide_id
    work_id_raw = payload.get("workId") or payload.get("work_id")
    work_id = int(work_id_raw) if work_id_raw not in {None, ""} else None
    if work_id is not None and not _get_work(work_id):
        raise ValueError(f"work {work_id} not found")
    with _lock:
        record = {
            "id": _next_guide_id,
            "work_id": work_id,
            "payload": dict(payload),
            "guide": dict(result),
            "country": result.get("country") or payload.get("targetCountry"),
            "genre": result.get("genre") or payload.get("genre"),
            "title": result.get("title") or "Localization Guide",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        _next_guide_id += 1
        _localization_guides.append(record)
        return dict(record)


def localization_guides_list(work_id: int | None = None) -> list[dict[str, Any]]:
    with _lock:
        rows = [dict(row) for row in _localization_guides]
    if work_id is not None:
        rows = [row for row in rows if row.get("work_id") == work_id]
    return sorted(rows, key=lambda row: row["created_at"], reverse=True)


def localization_guide_get(guide_id: int) -> dict[str, Any]:
    with _lock:
        for row in _localization_guides:
            if row["id"] == guide_id:
                return dict(row)
    raise ValueError(f"guide {guide_id} not found")


def localization_guide_delete(guide_id: int) -> dict[str, Any]:
    global _localization_guides
    with _lock:
        if not any(row["id"] == guide_id for row in _localization_guides):
            raise ValueError(f"guide {guide_id} not found")
        _localization_guides = [row for row in _localization_guides if row["id"] != guide_id]
        return {"ok": True}
