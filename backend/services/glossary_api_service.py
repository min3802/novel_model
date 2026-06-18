from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.translation.glossary_store import (
    GLOSSARY_CATEGORIES,
    GLOSSARY_PRIORITIES,
    GlossaryCandidateRecord,
    GlossaryEntryRecord,
    GlossaryRepository,
    is_contextual_reference,
    should_persist_as_glossary_candidate,
)
from app.translation.locale_utils import LocaleNormalizationError, normalize_target_fields
from backend.services.glossary_service import (
    approve_candidate,
    get_glossary_repository,
    get_glossary_repository_status,
    list_approved_glossary,
    list_glossary_candidates,
    reject_candidate,
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


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        raw_items = [value]
    items: list[str] = []
    for raw in raw_items:
        cleaned = _clean(raw)
        if cleaned:
            items.append(cleaned)
    return items


def _normalized_category(value: Any) -> str:
    category = _clean(value) or "other"
    return category if category in GLOSSARY_CATEGORIES else "other"


def _normalized_priority(value: Any) -> str:
    priority = _clean(value) or "soft"
    return priority if priority in GLOSSARY_PRIORITIES else "soft"


def _candidate_dict(candidate: GlossaryCandidateRecord) -> dict[str, Any]:
    return asdict(candidate)


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
    if "candidate" in lowered and "not found" in lowered:
        return _error("candidate_not_found", "Glossary candidate was not found.", status=404)
    if "entry" in lowered and "not found" in lowered:
        return _error("entry_not_found", "Glossary entry was not found.", status=404)
    if "work_id must be" in lowered:
        return _error("invalid_work_id", message)
    if "episode_id must be" in lowered:
        return _error("invalid_episode_id", message)
    if "work_id" in lowered and "target_locale" in lowered:
        return _error("invalid_payload", message)
    return _error("repository_error", "Glossary repository operation failed.")


def _require_work_scope(payload: dict[str, Any] | None) -> tuple[str, str] | dict[str, Any]:
    work_id = _clean(_payload_value(payload, "workId", "work_id"))
    if not work_id:
        return _error("missing_work_id", "workId is required.")
    try:
        normalized = normalize_target_fields(payload)
    except LocaleNormalizationError as exc:
        return _repository_error(exc)
    target_locale = normalized["targetLocale"]
    return work_id, target_locale


def _candidate_to_entry_payload(candidate: GlossaryCandidateRecord, *, target: str | None = None) -> dict[str, Any]:
    return {
        "work_id": candidate.work_id,
        "target_locale": candidate.target_locale,
        "source": candidate.source,
        "target": _clean(target) or candidate.suggested_target,
        "category": candidate.category,
        "priority": "soft",
        "status": "approved",
        "note": candidate.reason,
        "created_by": "system",
        "aliases": list(candidate.aliases or []),
        "forbidden": [],
    }


def _find_entry_by_id(entries: list[GlossaryEntryRecord], entry_id: int | None) -> GlossaryEntryRecord | None:
    if entry_id is None:
        return None
    for entry in entries:
        if int(entry.id or 0) == int(entry_id):
            return entry
    return None


def list_glossary_candidates_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    scope = _require_work_scope(payload)
    if isinstance(scope, dict):
        return scope
    work_id, target_locale = scope
    repo = repository or get_glossary_repository()
    invalid_work = _validate_mysql_work_id(work_id, repo)
    if invalid_work is not None:
        return invalid_work
    status = _clean(_payload_value(payload, "status")) or None
    try:
        items = list_glossary_candidates(work_id, target_locale, status=status, repository=repo)
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)
    return {
        "ok": True,
        "items": [_candidate_dict(item) for item in items],
        "count": len(items),
        "repository": _repository_meta(repo),
    }


def approve_glossary_candidate_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    candidate_id_raw = _payload_value(payload, "candidateId", "candidate_id")
    if candidate_id_raw is None:
        return _error("invalid_payload", "candidateId is required.")
    try:
        candidate_id = int(candidate_id_raw)
    except (TypeError, ValueError):
        return _error("invalid_payload", "candidateId must be an integer.")

    repo = repository or get_glossary_repository()
    work_id = _payload_value(payload, "workId", "work_id")
    if work_id is not None:
        invalid_work = _validate_mysql_work_id(work_id, repo)
        if invalid_work is not None:
            return invalid_work
    target_override = _clean(_payload_value(payload, "targetOverride", "target_override")) or None
    priority_payload = _payload_value(payload, "priority")
    priority_override = _normalized_priority(priority_payload) if priority_payload is not None else None
    note_override = _clean(_payload_value(payload, "note")) or None
    approved_entry: GlossaryEntryRecord | None = None
    try:
        candidate = approve_candidate(candidate_id, target_override=target_override, repository=repo)
        approved_entries = list_approved_glossary(candidate.work_id, candidate.target_locale, repository=repo, limit=500)
        approved_entry = _find_entry_by_id(approved_entries, candidate.merged_entry_id)
        if approved_entry is not None and (
            priority_override is not None
            or note_override is not None
            or target_override is not None
        ):
            payload_entry = _candidate_to_entry_payload(candidate, target=target_override or approved_entry.target)
            payload_entry["priority"] = priority_override or approved_entry.priority
            payload_entry["note"] = note_override or approved_entry.note
            payload_entry["aliases"] = [row.alias_source for row in approved_entry.aliases]
            payload_entry["forbidden"] = [row.forbidden_target for row in approved_entry.forbidden_terms]
            approved_entry = repo.upsert_entry(**payload_entry)
    except ValueError as exc:
        return _repository_error(exc)
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)

    approved_entries = list_approved_glossary(candidate.work_id, candidate.target_locale, repository=repo, limit=500)
    approved_entry = _find_entry_by_id(approved_entries, candidate.merged_entry_id) or approved_entry
    return {
        "ok": True,
        "candidate": _candidate_dict(candidate),
        "approvedEntry": _entry_dict(approved_entry) if approved_entry is not None else None,
        "repository": _repository_meta(repo),
    }


def reject_glossary_candidate_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    candidate_id_raw = _payload_value(payload, "candidateId", "candidate_id")
    if candidate_id_raw is None:
        return _error("invalid_payload", "candidateId is required.")
    try:
        candidate_id = int(candidate_id_raw)
    except (TypeError, ValueError):
        return _error("invalid_payload", "candidateId must be an integer.")
    repo = repository or get_glossary_repository()
    work_id = _payload_value(payload, "workId", "work_id")
    if work_id is not None:
        invalid_work = _validate_mysql_work_id(work_id, repo)
        if invalid_work is not None:
            return invalid_work
    try:
        candidate = reject_candidate(candidate_id, repository=repo)
    except ValueError as exc:
        return _repository_error(exc)
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)
    return {
        "ok": True,
        "candidate": _candidate_dict(candidate),
        "repository": _repository_meta(repo),
    }


def list_glossary_entries_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    scope = _require_work_scope(payload)
    if isinstance(scope, dict):
        return scope
    work_id, target_locale = scope
    repo = repository or get_glossary_repository()
    invalid_work = _validate_mysql_work_id(work_id, repo)
    if invalid_work is not None:
        return invalid_work
    try:
        items = list_approved_glossary(work_id, target_locale, repository=repo)
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
    work_id, target_locale = scope
    repo = repository or get_glossary_repository()
    invalid_work = _validate_mysql_work_id(work_id, repo)
    if invalid_work is not None:
        return invalid_work

    entry_id_raw = _payload_value(payload, "entryId", "entry_id")
    existing_entry: GlossaryEntryRecord | None = None
    if entry_id_raw is not None:
        try:
            entry_id = int(entry_id_raw)
        except (TypeError, ValueError):
            return _error("invalid_payload", "entryId must be an integer.")
        existing_entry = _find_entry_by_id(list_approved_glossary(work_id, target_locale, repository=repo, limit=500), entry_id)
        if existing_entry is None:
            return _error("entry_not_found", "Glossary entry was not found.", status=404)

    source = _clean(_payload_value(payload, "source")) or (existing_entry.source if existing_entry else "")
    target = _clean(_payload_value(payload, "target")) or (existing_entry.target if existing_entry else "")
    category = _normalized_category(_payload_value(payload, "category") or (existing_entry.category if existing_entry else "other"))
    priority = _normalized_priority(_payload_value(payload, "priority") or (existing_entry.priority if existing_entry else "soft"))
    note = _payload_value(payload, "note")
    note = _clean(note) or (existing_entry.note if existing_entry else None)
    created_by = _clean(_payload_value(payload, "createdBy", "created_by")) or (existing_entry.created_by if existing_entry else "system")
    aliases = _string_list(_payload_value(payload, "aliases"))
    forbidden = _string_list(_payload_value(payload, "forbidden"))

    if not source:
        return _error("invalid_payload", "source is required.")
    if not target:
        return _error("invalid_payload", "target is required.")
    if is_contextual_reference(source) or not should_persist_as_glossary_candidate(source, category):
        return _error("contextual_reference_not_allowed", "Contextual references cannot be stored as glossary entries.")
    if existing_entry is not None and not aliases:
        aliases = [row.alias_source for row in existing_entry.aliases]
    if existing_entry is not None and not forbidden:
        forbidden = [row.forbidden_target for row in existing_entry.forbidden_terms]

    try:
        entry = repo.upsert_entry(
            work_id=work_id,
            target_locale=target_locale,
            source=source,
            target=target,
            category=category,
            priority=priority,
            status="approved",
            note=note,
            created_by=created_by,
            aliases=aliases,
            forbidden=forbidden,
        )
    except ValueError as exc:
        return _repository_error(exc)
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)
    return {
        "ok": True,
        "entry": _entry_dict(entry),
        "approvedEntry": _entry_dict(entry),
        "repository": _repository_meta(repo),
    }


def delete_or_deprecate_glossary_entry_handler(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    scope = _require_work_scope(payload)
    if isinstance(scope, dict):
        return scope
    work_id, target_locale = scope
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
    approved_entries = list_approved_glossary(work_id, target_locale, repository=repo, limit=500)
    existing_entry = _find_entry_by_id(approved_entries, entry_id)
    if existing_entry is None:
        return _error("entry_not_found", "Glossary entry was not found.", status=404)
    try:
        deprecated = repo.upsert_entry(
            work_id=work_id,
            target_locale=target_locale,
            source=existing_entry.source,
            target=existing_entry.target,
            category=existing_entry.category,
            priority=existing_entry.priority,
            status="deprecated",
            note=existing_entry.note,
            created_by=existing_entry.created_by,
            aliases=[row.alias_source for row in existing_entry.aliases],
            forbidden=[row.forbidden_target for row in existing_entry.forbidden_terms],
        )
    except Exception as exc:  # pragma: no cover - exercised in integration paths
        return _repository_error(exc)
    return {
        "ok": True,
        "entry": _entry_dict(deprecated),
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
