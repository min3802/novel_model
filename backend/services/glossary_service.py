from __future__ import annotations

import os
from typing import Any

from app.translation.glossary_store import (
    GlossaryCandidateRecord,
    GlossaryEntryRecord,
    GlossaryRepository,
    WorkMemory,
    collect_glossary_candidate_inputs,
    default_glossary_repository,
    is_contextual_reference,
    should_persist_as_glossary_candidate,
)

_repository_cache: GlossaryRepository | None = None
_repository_cache_backend: str | None = None
_repository_factory_error: str = ""


def get_glossary_repository(*, refresh: bool = False) -> GlossaryRepository:
    """Return the configured glossary repository.

    Defaults to the process-local in-memory repository. Set
    GLOSSARY_STORE_BACKEND=mysql to use MySQLGlossaryRepository. If the MySQL
    adapter cannot be imported or configured, this falls back to memory so
    translation requests remain deliverable.
    """

    global _repository_cache, _repository_cache_backend, _repository_factory_error
    backend = os.getenv("GLOSSARY_STORE_BACKEND", "memory").strip().lower() or "memory"
    if not refresh and _repository_cache is not None and _repository_cache_backend == backend:
        return _repository_cache
    _repository_factory_error = ""
    if backend == "mysql":
        try:
            from app.translation.mysql_glossary_store import MySQLGlossaryRepository

            mysql_repository = MySQLGlossaryRepository.from_env()
            mysql_repository.ping()
            _repository_cache = mysql_repository
            _repository_cache_backend = backend
            return _repository_cache
        except Exception as exc:
            _repository_factory_error = f"mysql_repository_unavailable:{type(exc).__name__}"
            _repository_cache = default_glossary_repository
            _repository_cache_backend = backend
            return _repository_cache
    if backend != "memory":
        _repository_factory_error = f"unknown_glossary_backend:{backend}"
    _repository_cache = default_glossary_repository
    _repository_cache_backend = backend
    return _repository_cache


def get_glossary_repository_status() -> dict[str, Any]:
    backend = os.getenv("GLOSSARY_STORE_BACKEND", "memory").strip().lower() or "memory"
    if backend == "mysql" and (_repository_cache is None or _repository_cache_backend != backend):
        get_glossary_repository()
    effective = "memory" if _repository_factory_error else backend
    return {
        "backend": backend,
        "effective": effective,
        "available": True,
        "mysqlAvailable": backend == "mysql" and effective == "mysql",
        "fallback": backend == "mysql" and effective != "mysql",
        "error": _repository_factory_error,
    }


def list_approved_glossary(
    work_id: str,
    target_locale: str,
    *,
    repository: GlossaryRepository | None = None,
    limit: int = 50,
) -> list[GlossaryEntryRecord]:
    repo = repository or get_glossary_repository()
    return repo.list_approved_glossary(work_id, target_locale, limit=limit)


def hydrate_work_memory(
    work_id: str,
    target_locale: str,
    *,
    repository: GlossaryRepository | None = None,
    limit: int = 50,
) -> WorkMemory | None:
    repo = repository or get_glossary_repository()
    return repo.hydrate_work_memory(work_id, target_locale, limit=limit)


def create_glossary_candidate(
    payload: dict[str, Any] | None = None,
    *,
    repository: GlossaryRepository | None = None,
    **kwargs: Any,
) -> GlossaryCandidateRecord:
    repo = repository or get_glossary_repository()
    merged = {**(payload or {}), **kwargs}
    return repo.create_glossary_candidate(**merged)


def list_glossary_candidates(
    work_id: str,
    target_locale: str,
    *,
    status: str | None = None,
    repository: GlossaryRepository | None = None,
) -> list[GlossaryCandidateRecord]:
    repo = repository or get_glossary_repository()
    return repo.list_glossary_candidates(work_id, target_locale, status=status)


def list_pending_candidates(
    work_id: str,
    target_locale: str,
    *,
    repository: GlossaryRepository | None = None,
) -> list[GlossaryCandidateRecord]:
    return list_glossary_candidates(work_id, target_locale, status="pending", repository=repository)


def get_glossary_candidate(
    candidate_id: int,
    *,
    repository: GlossaryRepository | None = None,
) -> GlossaryCandidateRecord | None:
    repo = repository or get_glossary_repository()
    return repo.get_glossary_candidate(candidate_id)


def _increment(skipped_reasons: dict[str, int], reason: str) -> None:
    skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1


def _candidate_key(row: Any) -> tuple[str, str]:
    return (str(getattr(row, "source", "") or "").strip(), str(getattr(row, "category", "") or "other").strip())


def capture_candidates_from_v3_result(
    v3_result: Any,
    work_id: str,
    episode_id: str | None,
    target_locale: str,
    *,
    repository: GlossaryRepository | None = None,
) -> dict[str, Any]:
    repo = repository or get_glossary_repository()
    candidates = collect_glossary_candidate_inputs(v3_result)
    skipped_reasons: dict[str, int] = {}
    saved = 0

    approved_keys = {_candidate_key(row) for row in repo.list_approved_glossary(work_id, target_locale, limit=500)}
    pending_keys = {_candidate_key(row) for row in repo.list_glossary_candidates(work_id, target_locale, status="pending")}

    for candidate in candidates:
        source = str(candidate.get("source") or "").strip()
        category = str(candidate.get("category") or "other").strip() or "other"
        suggested_target = str(
            candidate.get("suggested_target")
            or candidate.get("suggestedTarget")
            or candidate.get("target")
            or ""
        ).strip()
        if not source:
            _increment(skipped_reasons, "empty_source")
            continue
        if is_contextual_reference(source):
            _increment(skipped_reasons, "contextual_reference")
            continue
        if not should_persist_as_glossary_candidate(source, category, candidate.get("confidence")):
            _increment(skipped_reasons, "not_persistable")
            continue
        if not suggested_target:
            _increment(skipped_reasons, "missing_suggested_target")
            continue
        key = (source, category)
        if key in approved_keys:
            _increment(skipped_reasons, "already_approved")
            continue
        if key in pending_keys:
            _increment(skipped_reasons, "duplicate_candidate")
            continue
        repo.create_glossary_candidate(
            work_id=work_id,
            episode_id=episode_id,
            target_locale=target_locale,
            source=source,
            suggested_target=suggested_target,
            category=category,
            confidence=candidate.get("confidence"),
            source_span=candidate.get("source_span") or candidate.get("sourceSpan"),
            reason=candidate.get("reason"),
            aliases=candidate.get("aliases") or [],
            status="pending",
        )
        pending_keys.add(key)
        saved += 1

    skipped = sum(skipped_reasons.values())
    return {
        "enabled": True,
        "collectedCount": len(candidates),
        "savedCount": saved,
        "skippedCount": skipped,
        "skippedReasons": skipped_reasons,
    }


def approve_glossary_candidate(
    candidate_id: int,
    target_override: str | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> GlossaryCandidateRecord:
    repo = repository or get_glossary_repository()
    return repo.approve_glossary_candidate(candidate_id, target_override=target_override)


def approve_candidate(
    candidate_id: int,
    target_override: str | None = None,
    *,
    repository: GlossaryRepository | None = None,
) -> GlossaryCandidateRecord:
    return approve_glossary_candidate(candidate_id, target_override=target_override, repository=repository)


def reject_glossary_candidate(
    candidate_id: int,
    *,
    repository: GlossaryRepository | None = None,
) -> GlossaryCandidateRecord:
    repo = repository or get_glossary_repository()
    return repo.reject_glossary_candidate(candidate_id)


def reject_candidate(
    candidate_id: int,
    *,
    repository: GlossaryRepository | None = None,
) -> GlossaryCandidateRecord:
    return reject_glossary_candidate(candidate_id, repository=repository)
