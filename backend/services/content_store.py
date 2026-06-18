from __future__ import annotations

import copy
import itertools
from datetime import datetime, timezone
from typing import Any, Protocol


JSON_FIELDS = {"translation_rationale", "qa_issues", "author_review_cards", "metadata", "internal"}


class ContentRepository(Protocol):
    def upsert_work(self, data: dict[str, Any]) -> dict[str, Any]: ...
    def get_work(self, work_id: int | str) -> dict[str, Any] | None: ...
    def list_works(self, user_id: int | str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]: ...
    def archive_work(self, work_id: int | str) -> dict[str, Any] | None: ...
    def upsert_episode(self, data: dict[str, Any]) -> dict[str, Any]: ...
    def get_episode(self, episode_id: int | str) -> dict[str, Any] | None: ...
    def list_episodes(self, work_id: int | str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]: ...
    def archive_episode(self, episode_id: int | str) -> dict[str, Any] | None: ...
    def save_translation_result(self, data: dict[str, Any]) -> dict[str, Any]: ...
    def get_translation(self, translation_id: int | str) -> dict[str, Any] | None: ...
    def list_translations(
        self,
        work_id: int | str | None = None,
        episode_id: int | str | None = None,
        target_country: str | None = None,
        target_locale: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...
    def get_latest_translation(
        self,
        episode_id: int | str,
        target_country: str | None = None,
        target_locale: str | None = None,
    ) -> dict[str, Any] | None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _int_id(value: int | str | None, *, field: str) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _copy(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return copy.deepcopy(row) if row is not None else None


class InMemoryContentRepository:
    backend = "memory"

    def __init__(self) -> None:
        self._work_ids = itertools.count(1)
        self._episode_ids = itertools.count(1)
        self._translation_ids = itertools.count(1)
        self._works: dict[int, dict[str, Any]] = {}
        self._episodes: dict[int, dict[str, Any]] = {}
        self._translations: dict[int, dict[str, Any]] = {}

    def clear(self) -> None:
        self.__init__()

    def upsert_work(self, data: dict[str, Any]) -> dict[str, Any]:
        work_id = data.get("work_id") or data.get("workId")
        if work_id is None:
            wid = next(self._work_ids)
            created_at = _now()
        else:
            wid = _int_id(work_id, field="work_id")
            created_at = self._works.get(wid, {}).get("created_at") or _now()
        row = dict(self._works.get(wid) or {})
        row.update(
            {
                "work_id": wid,
                "user_id": int(data.get("user_id") or data.get("userId") or row.get("user_id") or 1),
                "title": str(data.get("title") or row.get("title") or "").strip(),
                "pen_name": data.get("pen_name") or data.get("penName") or row.get("pen_name"),
                "genre": data.get("genre") or row.get("genre"),
                "synopsis": data.get("synopsis") or row.get("synopsis"),
                "source_locale": data.get("source_locale") or data.get("sourceLocale") or row.get("source_locale") or "KO",
                "default_target_country": data.get("default_target_country") or data.get("defaultTargetCountry") or row.get("default_target_country"),
                "status": data.get("status") or row.get("status") or "active",
                "created_at": created_at,
                "updated_at": _now(),
            }
        )
        if not row["title"]:
            raise ValueError("title is required")
        self._works[wid] = row
        return _copy(row)  # type: ignore[return-value]

    def get_work(self, work_id: int | str) -> dict[str, Any] | None:
        return _copy(self._works.get(_int_id(work_id, field="work_id")))

    def list_works(self, user_id: int | str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = list(self._works.values())
        if user_id is not None:
            uid = _int_id(user_id, field="user_id")
            rows = [row for row in rows if row.get("user_id") == uid]
        rows = [row for row in rows if row.get("status") != "archived"]
        rows.sort(key=lambda row: int(row["work_id"]))
        return copy.deepcopy(rows[offset : offset + limit])

    def archive_work(self, work_id: int | str) -> dict[str, Any] | None:
        row = self._works.get(_int_id(work_id, field="work_id"))
        if row is None:
            return None
        row["status"] = "archived"
        row["updated_at"] = _now()
        return _copy(row)

    def upsert_episode(self, data: dict[str, Any]) -> dict[str, Any]:
        work_id = _int_id(data.get("work_id") or data.get("workId"), field="work_id")
        if work_id not in self._works:
            raise ValueError("work not found")
        episode_id = data.get("episode_id") or data.get("episodeId")
        if episode_id is None:
            eid = next(self._episode_ids)
            created_at = _now()
        else:
            eid = _int_id(episode_id, field="episode_id")
            created_at = self._episodes.get(eid, {}).get("created_at") or _now()
        row = dict(self._episodes.get(eid) or {})
        original_text = data.get("original_text") if "original_text" in data else data.get("originalText", row.get("original_text", ""))
        row.update(
            {
                "episode_id": eid,
                "work_id": work_id,
                "episode_no": data.get("episode_no") if "episode_no" in data else data.get("episodeNo", row.get("episode_no")),
                "title": str(data.get("title") or row.get("title") or "").strip(),
                "original_text": str(original_text or ""),
                "source_text_hash": data.get("source_text_hash") or data.get("sourceTextHash") or row.get("source_text_hash"),
                "char_count": len(str(original_text or "")),
                "status": data.get("status") or row.get("status") or "ready",
                "created_at": created_at,
                "updated_at": _now(),
            }
        )
        if not row["title"]:
            raise ValueError("title is required")
        if not row["original_text"]:
            raise ValueError("original_text is required")
        self._episodes[eid] = row
        return _copy(row)  # type: ignore[return-value]

    def get_episode(self, episode_id: int | str) -> dict[str, Any] | None:
        return _copy(self._episodes.get(_int_id(episode_id, field="episode_id")))

    def list_episodes(self, work_id: int | str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        wid = _int_id(work_id, field="work_id")
        rows = [row for row in self._episodes.values() if row.get("work_id") == wid and row.get("status") != "archived"]
        rows.sort(key=lambda row: (row.get("episode_no") is None, row.get("episode_no") or 0, row["episode_id"]))
        return copy.deepcopy(rows[offset : offset + limit])

    def archive_episode(self, episode_id: int | str) -> dict[str, Any] | None:
        row = self._episodes.get(_int_id(episode_id, field="episode_id"))
        if row is None:
            return None
        row["status"] = "archived"
        row["updated_at"] = _now()
        return _copy(row)

    def save_translation_result(self, data: dict[str, Any]) -> dict[str, Any]:
        tid = next(self._translation_ids)
        row = {
            "translation_id": tid,
            "work_id": _int_id(data.get("work_id") or data.get("workId"), field="work_id"),
            "episode_id": _int_id(data.get("episode_id") or data.get("episodeId"), field="episode_id"),
            "target_country": data["target_country"],
            "target_locale": data["target_locale"],
            "pipeline": data.get("pipeline") or data.get("mode") or "unknown",
            "delivery_status": data.get("delivery_status") or data.get("deliveryStatus") or "deliverable",
            "translated_text": str(data.get("translated_text") if "translated_text" in data else data.get("finalTranslation", "")),
            "translation_rationale": data.get("translation_rationale"),
            "qa_issues": data.get("qa_issues"),
            "author_review_cards": data.get("author_review_cards"),
            "metadata": data.get("metadata"),
            "internal": data.get("internal"),
            "model_name": data.get("model_name") or data.get("modelName"),
            "source_text_hash": data.get("source_text_hash") or data.get("sourceTextHash"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        if row["work_id"] not in self._works:
            raise ValueError("work not found")
        if row["episode_id"] not in self._episodes:
            raise ValueError("episode not found")
        self._translations[tid] = row
        return _copy(row)  # type: ignore[return-value]

    def get_translation(self, translation_id: int | str) -> dict[str, Any] | None:
        return _copy(self._translations.get(_int_id(translation_id, field="translation_id")))

    def list_translations(
        self,
        work_id: int | str | None = None,
        episode_id: int | str | None = None,
        target_country: str | None = None,
        target_locale: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = list(self._translations.values())
        if work_id is not None:
            wid = _int_id(work_id, field="work_id")
            rows = [row for row in rows if row.get("work_id") == wid]
        if episode_id is not None:
            eid = _int_id(episode_id, field="episode_id")
            rows = [row for row in rows if row.get("episode_id") == eid]
        if target_country:
            rows = [row for row in rows if row.get("target_country") == target_country]
        if target_locale:
            rows = [row for row in rows if row.get("target_locale") == target_locale]
        rows.sort(key=lambda row: int(row["translation_id"]), reverse=True)
        return copy.deepcopy(rows[offset : offset + limit])

    def get_latest_translation(
        self,
        episode_id: int | str,
        target_country: str | None = None,
        target_locale: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.list_translations(episode_id=episode_id, target_country=target_country, target_locale=target_locale, limit=1)
        return rows[0] if rows else None


default_content_repository = InMemoryContentRepository()
