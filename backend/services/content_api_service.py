"""HTTP-facing handlers for works, episodes, and translation_results."""

from __future__ import annotations

import hashlib
from typing import Any

from app.translation.locale_utils import LocaleNormalizationError
from backend.services.content_service import (
    ContentServiceError,
    get_content_repository,
    get_content_repository_status,
    normalize_content_target_fields,
    validate_original_text,
)


def _ok_item(item: dict[str, Any] | None, *, status: int = 200) -> dict[str, Any]:
    return {"ok": True, "status": status, "item": item}


def _ok_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"ok": True, "items": items, "count": len(items)}


def _error(error_code: str, message: str, *, status: int = 400) -> dict[str, Any]:
    return {"ok": False, "status": status, "errorCode": error_code, "message": message}


def _int_payload(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if payload.get(key) is not None and payload.get(key) != "":
            return int(payload[key])
    return None


def _str_payload(payload: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        if payload.get(key) is not None:
            return str(payload[key])
    return default


def _repo_call(fn):
    try:
        return fn()
    except LocaleNormalizationError as exc:
        return _error(exc.error_code, exc.message)
    except ContentServiceError as exc:
        return _error(exc.error_code, exc.message, status=exc.status)
    except ValueError as exc:
        return _error("invalid_payload", str(exc))
    except Exception as exc:
        return _error("repository_error", f"{type(exc).__name__}: {exc}", status=500)


def get_content_repository_status_handler(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, **get_content_repository_status(refresh=bool((payload or {}).get("refresh")))}


def _work_data(payload: dict[str, Any]) -> dict[str, Any]:
    title = _str_payload(payload, "title").strip()
    if not title:
        raise ContentServiceError("invalid_payload", "title is required")
    return {
        "work_id": _int_payload(payload, "workId", "work_id"),
        "user_id": _int_payload(payload, "userId", "user_id") or 1,
        "title": title,
        "pen_name": _str_payload(payload, "penName", "pen_name", default="").strip() or None,
        "genre": _str_payload(payload, "genre", default="").strip() or None,
        "synopsis": _str_payload(payload, "synopsis", default="").strip() or None,
        "source_locale": _str_payload(payload, "sourceLocale", "source_locale", default="KO").strip() or "KO",
        "default_target_country": _str_payload(
            payload, "defaultTargetCountry", "default_target_country", default=""
        ).strip()
        or None,
        "status": _str_payload(payload, "status", default="active").strip() or "active",
    }


def upsert_work_handler(payload: dict[str, Any]) -> dict[str, Any]:
    return _repo_call(lambda: _ok_item(get_content_repository().upsert_work(_work_data(payload)), status=201))


def get_work_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        work_id = _int_payload(payload, "workId", "work_id")
        if work_id is None:
            raise ContentServiceError("missing_work_id", "workId is required")
        item = get_content_repository().get_work(work_id)
        if not item:
            return _error("work_not_found", "work not found", status=404)
        return _ok_item(item)

    return _repo_call(run)


def list_works_handler(payload: dict[str, Any]) -> dict[str, Any]:
    return _repo_call(
        lambda: _ok_items(
            get_content_repository().list_works(
                user_id=_int_payload(payload, "userId", "user_id"),
                limit=int(payload.get("limit") or 50),
                offset=int(payload.get("offset") or 0),
            )
        )
    )


def archive_work_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        work_id = _int_payload(payload, "workId", "work_id")
        if work_id is None:
            raise ContentServiceError("missing_work_id", "workId is required")
        item = get_content_repository().archive_work(work_id)
        if not item:
            return _error("work_not_found", "work not found", status=404)
        return _ok_item(item)

    return _repo_call(run)


def _episode_data(payload: dict[str, Any]) -> dict[str, Any]:
    work_id = _int_payload(payload, "workId", "work_id")
    if work_id is None:
        raise ContentServiceError("missing_work_id", "workId is required")
    original_text = validate_original_text(_str_payload(payload, "originalText", "original_text"))
    title = _str_payload(payload, "title", default="").strip()
    if not title:
        raise ContentServiceError("invalid_payload", "title is required")
    return {
        "episode_id": _int_payload(payload, "episodeId", "episode_id"),
        "work_id": work_id,
        "episode_no": _int_payload(payload, "episodeNo", "episode_no"),
        "title": title,
        "original_text": original_text,
        "source_text_hash": hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
        "char_count": len(original_text),
        "status": _str_payload(payload, "status", default="ready").strip() or "ready",
    }


def upsert_episode_handler(payload: dict[str, Any]) -> dict[str, Any]:
    return _repo_call(lambda: _ok_item(get_content_repository().upsert_episode(_episode_data(payload)), status=201))


def get_episode_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        episode_id = _int_payload(payload, "episodeId", "episode_id")
        if episode_id is None:
            raise ContentServiceError("missing_episode_id", "episodeId is required")
        item = get_content_repository().get_episode(episode_id)
        if not item:
            return _error("episode_not_found", "episode not found", status=404)
        return _ok_item(item)

    return _repo_call(run)


def list_episodes_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        work_id = _int_payload(payload, "workId", "work_id")
        if work_id is None:
            raise ContentServiceError("missing_work_id", "workId is required")
        return _ok_items(
            get_content_repository().list_episodes(
                work_id,
                limit=int(payload.get("limit") or 100),
                offset=int(payload.get("offset") or 0),
            )
        )

    return _repo_call(run)


def archive_episode_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        episode_id = _int_payload(payload, "episodeId", "episode_id")
        if episode_id is None:
            raise ContentServiceError("missing_episode_id", "episodeId is required")
        item = get_content_repository().archive_episode(episode_id)
        if not item:
            return _error("episode_not_found", "episode not found", status=404)
        return _ok_item(item)

    return _repo_call(run)


def get_translation_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        translation_id = _int_payload(payload, "translationId", "translation_id")
        if translation_id is None:
            raise ContentServiceError("translation_not_found", "translationId is required", status=404)
        item = get_content_repository().get_translation(translation_id)
        if not item:
            return _error("translation_not_found", "translation not found", status=404)
        return _ok_item(item)

    return _repo_call(run)


def list_translations_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        normalized: dict[str, str] = {}
        if any(k in payload for k in ("targetCountry", "target_country", "targetLocale", "target_locale")):
            normalized = normalize_content_target_fields(payload)
        return _ok_items(
            get_content_repository().list_translations(
                work_id=_int_payload(payload, "workId", "work_id"),
                episode_id=_int_payload(payload, "episodeId", "episode_id"),
                target_country=normalized.get("targetCountry"),
                target_locale=normalized.get("targetLocale"),
                limit=int(payload.get("limit") or 50),
                offset=int(payload.get("offset") or 0),
            )
        )

    return _repo_call(run)


def get_latest_translation_handler(payload: dict[str, Any]) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        episode_id = _int_payload(payload, "episodeId", "episode_id")
        if episode_id is None:
            raise ContentServiceError("missing_episode_id", "episodeId is required")
        normalized: dict[str, str] = {}
        if any(k in payload for k in ("targetCountry", "target_country", "targetLocale", "target_locale")):
            normalized = normalize_content_target_fields(payload)
        item = get_content_repository().get_latest_translation(
            episode_id,
            target_country=normalized.get("targetCountry"),
            target_locale=normalized.get("targetLocale"),
        )
        if not item:
            return _error("translation_not_found", "translation not found", status=404)
        return _ok_item(item)

    return _repo_call(run)
