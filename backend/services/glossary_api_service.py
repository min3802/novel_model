from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.translation.glossary import (
    DEFAULT_CATEGORY,
    GLOSSARY_CATEGORIES,
    GlossaryEntryRecord,
    GlossaryRepository,
    is_contextual_reference,
)
from app.translation.infra.locale_utils import LocaleNormalizationError, normalize_target_fields
from backend.services.glossary_service import (
    delete_entry,
    get_glossary_repository,
    get_glossary_repository_status,
    list_glossary,
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _payload_value(payload: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    if not isinstance(payload, dict):
        return default
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _entry_dict(entry: GlossaryEntryRecord) -> dict[str, Any]:
    return asdict(entry)


def _repository_meta(repository: GlossaryRepository | None = None) -> dict[str, Any]:
    status = get_glossary_repository_status()
    backend = status.get("effective") or status.get("backend") or "memory"
    return {
        "backend": backend,
        "available": bool(status.get("available", True)),
        "mysqlAvailable": bool(status.get("mysqlAvailable", False)),
        "fallback": bool(status.get("fallback", False)),
    }


def _repository_requires_numeric_ids(repository: GlossaryRepository | None = None) -> bool:
    if repository is not None and type(repository).__name__ == "MySQLGlossaryRepository":
        return True
    return _repository_meta(repository).get("backend") == "mysql"


def _validate_mysql_work_id(work_id: Any, repository: GlossaryRepository | None = None) -> dict[str, Any] | None:
    if not _repository_requires_numeric_ids(repository):
        return None
    try:
        normalized = int(str(work_id).strip())
    except (TypeError, ValueError):
        return _error("invalid_work_id", "workId must be a numeric works.work_id for the MySQL glossary backend.")
    if normalized <= 0:
        return _error("invalid_work_id", "workId must be a positive numeric works.work_id for the MySQL glossary backend.")
    return None


def _error(error_code: str, message: str, *, status: int = 400) -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "errorCode": error_code,
        "message": message,
    }


def _repository_error(exc: Exception) -> dict[str, Any]:
    message = str(exc) or type(exc).__name__
    lowered = message.lower()
    if isinstance(exc, LocaleNormalizationError):
        return _error(exc.error_code, exc.message)
    if "contextual reference" in lowered:
        return _error("contextual_reference_not_allowed", "Contextual references cannot be stored as glossary entries.")
    if "entry" in lowered and "not found" in lowered:
        return _error("entry_not_found", "Glossary entry was not found.", status=404)
    if "work_id must be" in lowered:
        return _error("invalid_work_id", message)
    if "work_id" in lowered and "country" in lowered:
        return _error("invalid_payload", message)
    return _error("repository_error", "Glossary repository operation failed.")


def _normalized_category(value: Any) -> str | None:
    """Return a valid category, or None when an explicit value is unsupported."""

    category = _clean(value).lower()
    if not category:
        return DEFAULT_CATEGORY
    return category if category in GLOSSARY_CATEGORIES else None


def _require_work_scope(payload: dict[str, Any] | None) -> tuple[str, str] | dict[str, Any]:
    work_id = _clean(_payload_value(payload, "workId", "work_id"))
    if not work_id:
        return _error("missing_work_id", "workId is required.")
    try:
        normalized = normalize_target_fields(payload)
    except LocaleNormalizationError as exc:
        return _repository_error(exc)
    country = normalized["targetCountry"]
    return work_id, country


def list_glossary_entries_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    scope = _require_work_scope(payload)
    if isinstance(scope, dict):
        return scope
    work_id, country = scope
    repo = repository or get_glossary_repository()
    invalid_work = _validate_mysql_work_id(work_id, repo)
    if invalid_work is not None:
        return invalid_work
    try:
        items = list_glossary(work_id, country, repository=repo)
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)
    return {
        "ok": True,
        "items": [_entry_dict(item) for item in items],
        "count": len(items),
        "repository": _repository_meta(repo),
    }


def upsert_glossary_entry_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    scope = _require_work_scope(payload)
    if isinstance(scope, dict):
        return scope
    work_id, country = scope
    repo = repository or get_glossary_repository()
    invalid_work = _validate_mysql_work_id(work_id, repo)
    if invalid_work is not None:
        return invalid_work

    existing_entry: GlossaryEntryRecord | None = None
    entry_id_raw = _payload_value(payload, "entryId", "entry_id")
    if entry_id_raw is not None:
        try:
            entry_id = int(entry_id_raw)
        except (TypeError, ValueError):
            return _error("invalid_payload", "entryId must be an integer.")
        existing_entry = repo.get_entry(entry_id)
        if existing_entry is None:
            return _error("entry_not_found", "Glossary entry was not found.", status=404)

    source = _clean(_payload_value(payload, "source")) or (existing_entry.source if existing_entry else "")
    target = _clean(_payload_value(payload, "target")) or (existing_entry.target if existing_entry else "")
    category_raw = _payload_value(payload, "category")
    if category_raw is None and existing_entry is not None:
        category_raw = existing_entry.category
    category = _normalized_category(category_raw)

    if not source:
        return _error("invalid_payload", "source is required.")
    if not target:
        return _error("invalid_payload", "target is required.")
    if category is None:
        return _error(
            "invalid_category",
            "category must be one of: " + ", ".join(sorted(GLOSSARY_CATEGORIES)) + ".",
        )
    if is_contextual_reference(source):
        return _error("contextual_reference_not_allowed", "Contextual references cannot be stored as glossary entries.")

    try:
        entry = repo.upsert_entry(
            work_id=work_id,
            country=country,
            source=source,
            target=target,
            category=category,
        )
    except ValueError as exc:
        return _repository_error(exc)
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)
    return {
        "ok": True,
        "entry": _entry_dict(entry),
        "repository": _repository_meta(repo),
    }


def delete_glossary_entry_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    scope = _require_work_scope(payload)
    if isinstance(scope, dict):
        return scope
    work_id, _country = scope
    entry_id_raw = _payload_value(payload, "entryId", "entry_id")
    if entry_id_raw is None:
        return _error("invalid_payload", "entryId is required.")
    try:
        entry_id = int(entry_id_raw)
    except (TypeError, ValueError):
        return _error("invalid_payload", "entryId must be an integer.")
    repo = repository or get_glossary_repository()
    invalid_work = _validate_mysql_work_id(work_id, repo)
    if invalid_work is not None:
        return invalid_work
    existing_entry = repo.get_entry(entry_id)
    if existing_entry is None:
        return _error("entry_not_found", "Glossary entry was not found.", status=404)
    try:
        deleted = delete_entry(entry_id, repository=repo)
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)
    return {
        "ok": True,
        "deleted": bool(deleted),
        "entry": _entry_dict(existing_entry),
        "repository": _repository_meta(repo),
    }


def get_glossary_repository_status_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    del payload, repository
    status = get_glossary_repository_status()
    return {
        "ok": True,
        "backend": status.get("effective") or status.get("backend") or "memory",
        "mysqlAvailable": bool(status.get("mysqlAvailable", False)),
        "fallback": bool(status.get("fallback", False)),
        "available": bool(status.get("available", True)),
    }
