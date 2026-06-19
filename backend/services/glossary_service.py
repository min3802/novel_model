from __future__ import annotations

import os
from typing import Any

from app.translation.glossary_store import (
    DEFAULT_CATEGORY,
    GlossaryEntryRecord,
    GlossaryRepository,
    WorkMemory,
    default_glossary_repository,
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


def list_glossary(
    work_id: str,
    country: str,
    *,
    repository: GlossaryRepository | None = None,
    limit: int = 50,
) -> list[GlossaryEntryRecord]:
    repo = repository or get_glossary_repository()
    return repo.list_glossary(work_id, country, limit=limit)


def upsert_entry(
    work_id: str,
    country: str,
    source: str,
    target: str,
    *,
    category: str = DEFAULT_CATEGORY,
    repository: GlossaryRepository | None = None,
) -> GlossaryEntryRecord:
    repo = repository or get_glossary_repository()
    return repo.upsert_entry(
        work_id=work_id,
        country=country,
        source=source,
        target=target,
        category=category,
    )


def get_entry(
    entry_id: int,
    *,
    repository: GlossaryRepository | None = None,
) -> GlossaryEntryRecord | None:
    repo = repository or get_glossary_repository()
    return repo.get_entry(entry_id)


def delete_entry(
    entry_id: int,
    *,
    repository: GlossaryRepository | None = None,
) -> bool:
    repo = repository or get_glossary_repository()
    return repo.delete_entry(entry_id)


def hydrate_work_memory(
    work_id: str,
    country: str,
    *,
    repository: GlossaryRepository | None = None,
    limit: int = 50,
) -> WorkMemory | None:
    repo = repository or get_glossary_repository()
    return repo.hydrate_work_memory(work_id, country, limit=limit)
