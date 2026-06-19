"""Service-layer factory and validation for core content persistence."""

from __future__ import annotations

import os
from typing import Any

from app.translation.infra.locale_utils import normalize_target_fields
from backend.services.content_store import ContentRepository, InMemoryContentRepository, default_content_repository

MAX_ORIGINAL_TEXT_CHARS = 8000
_repository: ContentRepository | None = None
_repository_status: dict[str, Any] | None = None


class ContentServiceError(ValueError):
    def __init__(self, error_code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status = status


def _requested_backend() -> str:
    return (os.getenv("CONTENT_STORE_BACKEND") or "memory").strip().lower() or "memory"


def get_content_repository(refresh: bool = False) -> ContentRepository:
    global _repository, _repository_status
    if _repository is not None and not refresh:
        return _repository
    requested = _requested_backend()
    if requested == "mysql":
        try:
            from backend.services.mysql_content_store import MySQLContentRepository

            repo = MySQLContentRepository.from_env()
            repo.ping()
            _repository = repo
            _repository_status = {
                "backend": "mysql",
                "requestedBackend": requested,
                "available": True,
                "mysqlAvailable": True,
                "fallback": False,
            }
            return repo
        except Exception as exc:
            _repository = InMemoryContentRepository()
            _repository_status = {
                "backend": "memory",
                "requestedBackend": requested,
                "available": True,
                "mysqlAvailable": False,
                "fallback": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
            return _repository
    _repository = default_content_repository if not refresh else InMemoryContentRepository()
    _repository_status = {
        "backend": "memory",
        "requestedBackend": requested,
        "available": True,
        "mysqlAvailable": False,
        "fallback": False,
    }
    return _repository


def get_content_repository_status(refresh: bool = False) -> dict[str, Any]:
    if refresh or _repository_status is None:
        get_content_repository(refresh=refresh)
    return dict(_repository_status or {})


def validate_original_text(text: Any) -> str:
    value = str(text or "")
    if not value.strip():
        raise ContentServiceError("invalid_payload", "originalText is required")
    if len(value) > MAX_ORIGINAL_TEXT_CHARS:
        raise ContentServiceError("text_too_long", "originalText exceeds 8000 characters")
    return value


def normalize_content_target_fields(payload: dict[str, Any]) -> dict[str, str]:
    return normalize_target_fields(payload)
