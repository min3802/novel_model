from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .consistency_checker import check_translation_consistency
except Exception:  # pragma: no cover - fallback for standalone smoke tests
    def check_translation_consistency(**kwargs):
        return {"checked": [], "issues": [], "summary": "checker unavailable"}

try:
    from .terminology import (
        TERMINOLOGY_POLICY_LOCKED,
        TERMINOLOGY_POLICY_PREFERRED,
        TERMINOLOGY_STATUS_CONFIRMED,
        terminology_rows_for_locale,
    )
except Exception:  # pragma: no cover
    TERMINOLOGY_POLICY_LOCKED = "locked"
    TERMINOLOGY_POLICY_PREFERRED = "preferred"
    TERMINOLOGY_STATUS_CONFIRMED = "confirmed"

    def terminology_rows_for_locale(payload_terms, locale, confirmed_only=False):
        if not payload_terms:
            return []
        if isinstance(payload_terms, dict):
            payload_terms = payload_terms.get("items") or payload_terms.get("terms") or []
        return payload_terms if isinstance(payload_terms, list) else []


CONSISTENCY_DIR_NAME = "translation_consistency"
GLOSSARY_FILE = "glossary.json"
TRANSLATION_MEMORY_FILE = "translation_memory.json"
USER_OVERRIDES_FILE = "user_overrides.json"
CHAT_EDITS_FILE = "chat_edits.json"
CONSISTENCY_REPORT_PREFIX = "consistency_report"

_CATEGORY_BY_TYPE = {
    "person_name": "character_name",
    "proper_noun": "proper_noun",
    "organization_name": "organization_name",
    "place_name": "place_name",
    "business_place_name": "place_name",
    "common_noun": "term",
    "term": "term",
}

_TRANSLATION_SPAN_REJECT = {"", "-", "—", "N/A", "n/a", "none", "None", "same", "unchanged"}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, list):
        return " / ".join(_clean(item) for item in value if _clean(item)).strip()
    if isinstance(value, dict):
        preferred = value.get("ko") or value.get("source") or value.get("text") or value.get("value")
        if preferred:
            return _clean(preferred)
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _now() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_default(default: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(default, ensure_ascii=False))


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return _json_default(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        broken = path.with_suffix(path.suffix + f".broken_{_now().replace(':', '')}")
        try:
            path.replace(broken)
        except Exception:
            pass
        return _json_default(default)
    return data if isinstance(data, dict) else _json_default(default)


def write_json(path: Path | None, data: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _safe_id(value: int | str | None) -> str:
    if value in {None, ""}:
        return ""
    return re.sub(r"[^0-9A-Za-z_\-]", "_", str(value))


def default_media_root() -> Path:
    env_root = os.getenv("WLIGHTER_CONSISTENCY_ROOT") or os.getenv("WLIGHTER_MEDIA_ROOT")
    if env_root:
        return Path(env_root)
    return Path.cwd() / "media" / "works"


def consistency_dir(work_id: int | str | None, *, root: Path | None = None) -> Path | None:
    safe = _safe_id(work_id)
    if not safe:
        return None
    base = Path(root) if root else default_media_root()
    return base / safe / CONSISTENCY_DIR_NAME


def _default_glossary(work_id: int | str | None) -> dict[str, Any]:
    return {"work_id": _safe_id(work_id), "items": [], "conflicts": [], "updated_at": ""}


def _default_memory(work_id: int | str | None) -> dict[str, Any]:
    return {"work_id": _safe_id(work_id), "items": [], "updated_at": ""}


def _default_overrides(work_id: int | str | None) -> dict[str, Any]:
    return {"work_id": _safe_id(work_id), "items": [], "updated_at": ""}


def _default_chat_edits(work_id: int | str | None) -> dict[str, Any]:
    return {"work_id": _safe_id(work_id), "items": [], "updated_at": ""}


@dataclass(slots=True)
class TranslationConsistencyManager:
    work_id: int | str | None
    target_locale: str
    target_language: str
    root: Path | None = None

    @property
    def base_dir(self) -> Path | None:
        return consistency_dir(self.work_id, root=self.root)

    @property
    def enabled(self) -> bool:
        return self.base_dir is not None

    def glossary_path(self) -> Path | None:
        return None if self.base_dir is None else self.base_dir / GLOSSARY_FILE

    def memory_path(self) -> Path | None:
        return None if self.base_dir is None else self.base_dir / TRANSLATION_MEMORY_FILE

    def overrides_path(self) -> Path | None:
        return None if self.base_dir is None else self.base_dir / USER_OVERRIDES_FILE

    def chat_edits_path(self) -> Path | None:
        return None if self.base_dir is None else self.base_dir / CHAT_EDITS_FILE

    def report_path(self, episode_id: int | str | None) -> Path | None:
        if self.base_dir is None:
            return None
        suffix = _safe_id(episode_id) or "unknown"
        return self.base_dir / f"{CONSISTENCY_REPORT_PREFIX}_{suffix}_{self.target_locale}.json"

    def load_glossary(self) -> dict[str, Any]:
        return read_json(self.glossary_path(), _default_glossary(self.work_id)) if self.glossary_path() else _default_glossary(self.work_id)

    def load_memory(self) -> dict[str, Any]:
        return read_json(self.memory_path(), _default_memory(self.work_id)) if self.memory_path() else _default_memory(self.work_id)

    def load_overrides(self) -> dict[str, Any]:
        return read_json(self.overrides_path(), _default_overrides(self.work_id)) if self.overrides_path() else _default_overrides(self.work_id)

    def load_chat_edits(self) -> dict[str, Any]:
        return read_json(self.chat_edits_path(), _default_chat_edits(self.work_id)) if self.chat_edits_path() else _default_chat_edits(self.work_id)

    def load_runtime_terms(self, source_text: str, payload_terms: Any = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_sources: set[str] = set()

        for raw in self.load_overrides().get("items", []):
            row = self._storage_row_to_terminology(raw, source="user_override")
            if self._is_active_row(row, source_text) and row["source"] not in seen_sources:
                rows.append(row)
                seen_sources.add(row["source"])

        for raw in self.load_glossary().get("items", []):
            row = self._storage_row_to_terminology(raw, source="glossary")
            if self._is_active_row(row, source_text) and row["source"] not in seen_sources:
                rows.append(row)
                seen_sources.add(row["source"])

        for row in terminology_rows_for_locale(payload_terms, self.target_locale, confirmed_only=False):
            source = _clean(row.get("source"))
            if not source or source in seen_sources:
                continue
            if source_text and source not in source_text:
                continue
            rows.append(row)
            seen_sources.add(source)

        return rows

    def build_runtime_context(self, source_text: str, payload_terms: Any = None) -> dict[str, Any]:
        terms = self.load_runtime_terms(source_text, payload_terms)
        return {"terms": terms, "term_count": len(terms), "enabled": self.enabled}

    def render_prompt_context(self, source_text: str, payload_terms: Any = None, limit: int = 80) -> str:
        terms = self.load_runtime_terms(source_text, payload_terms)[:limit]
        if not terms:
            return ""
        lines = [
            "[TRANSLATION_CONSISTENCY_GLOSSARY]",
            "Use the following established translations exactly when the source expression appears.",
        ]
        for row in terms:
            source = _clean(row.get("source"))
            target = _clean(row.get("target"))
            category = _clean(row.get("type")) or "term"
            store = _clean(row.get("sourceStore"))
            if source and target:
                mark = "USER_OVERRIDE" if store == "user_override" else "GLOSSARY"
                lines.append(f"- {source} => {target} ({category}, {mark})")
        return "\n".join(lines).strip()

    def update_after_translation(
        self,
        *,
        source_text: str,
        translated_text: str,
        episode_id: int | str | None,
        draft: dict[str, Any] | None = None,
        active_terminology: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "added": 0, "updated": 0, "conflicts": [], "checked": [], "issues": []}

        glossary = self.load_glossary()
        memory = self.load_memory()
        now = _now()
        added = 0
        updated = 0
        conflicts: list[dict[str, Any]] = []

        for pair in self._pairs_from_translation_decisions(draft or {}):
            result = self._upsert_glossary_pair(glossary, pair, episode_id=episode_id, source="translation_decision", now=now)
            added += int(result == "added")
            updated += int(result == "updated")
            if isinstance(result, dict):
                conflicts.append(result)

        for row in active_terminology or []:
            source = _clean(row.get("source"))
            target = _clean(row.get("target") or row.get("recommendedTranslation"))
            if not source or source not in source_text:
                continue
            if target and target in translated_text:
                result = self._upsert_glossary_pair(
                    glossary,
                    {
                        "source_text_ko": source,
                        "target_text": target,
                        "category": _CATEGORY_BY_TYPE.get(_clean(row.get("type")), _clean(row.get("type")) or "term"),
                        "policy": _clean(row.get("policy")) or TERMINOLOGY_POLICY_LOCKED,
                    },
                    episode_id=episode_id,
                    source="runtime_reuse",
                    now=now,
                )
                added += int(result == "added")
                updated += int(result == "updated")
                if isinstance(result, dict):
                    conflicts.append(result)

        glossary["updated_at"] = now
        write_json(self.glossary_path(), glossary)

        self._append_memory(memory, source_text=source_text, translated_text=translated_text, episode_id=episode_id, now=now)
        write_json(self.memory_path(), memory)

        check_terms = {"terms": [self._storage_row_to_terminology(item, source="glossary") for item in glossary.get("items", []) if isinstance(item, dict)]}
        check = check_translation_consistency(source_text=source_text, translated_text=translated_text, locale=self.target_locale, terminology=check_terms)
        report = {
            "enabled": True,
            "episode_id": episode_id,
            "target_locale": self.target_locale,
            "added": added,
            "updated": updated,
            "conflicts": conflicts,
            "checked": check.get("checked", []),
            "issues": check.get("issues", []),
            "summary": check.get("summary", ""),
            "updated_at": now,
        }
        write_json(self.report_path(episode_id), report)
        return report

    def apply_user_override(self, *, source_text_ko: str, target_text: str, category: str = "term", reason_ko: str = "사용자 수정 내역") -> dict[str, Any]:
        overrides = self.load_overrides()
        now = _now()
        source = _clean(source_text_ko)
        target = _clean(target_text)
        if not source or not target:
            return {"status": "skipped", "reason": "empty source or target"}
        items = overrides.setdefault("items", [])
        for item in items:
            if _clean(item.get("source_text_ko")) == source and _clean(item.get("target_language")) == self.target_language:
                item.update({"target_text": target, "category": category or item.get("category") or "term", "reason_ko": reason_ko, "source": "user_edit", "locked": True, "priority": "highest", "updated_at": now})
                break
        else:
            items.append({"source_text_ko": source, "target_language": self.target_language, "target_text": target, "category": category or "term", "reason_ko": reason_ko, "source": "user_edit", "locked": True, "priority": "highest", "created_at": now, "updated_at": now})
        overrides["updated_at"] = now
        write_json(self.overrides_path(), overrides)
        return {"status": "saved", "source_text_ko": source, "target_text": target}

    def save_chat_edit(self, *, episode_id: int | str | None, user_message: str, answer: str, change_summary: str, proposed_translation: str, applied: bool) -> dict[str, Any]:
        data = self.load_chat_edits()
        now = _now()
        item = {"episode_id": episode_id, "target_locale": self.target_locale, "user_message": _clean(user_message), "answer": _clean(answer), "change_summary": _clean(change_summary), "proposed_translation_length": len(proposed_translation or ""), "applied": bool(applied), "created_at": now}
        data.setdefault("items", []).append(item)
        data["updated_at"] = now
        write_json(self.chat_edits_path(), data)
        return item

    def _storage_row_to_terminology(self, row: dict[str, Any], *, source: str) -> dict[str, Any]:
        source_text = _clean(row.get("source_text_ko") or row.get("source") or row.get("term_ko"))
        target_text = _clean(row.get("target_text") or row.get("target") or row.get("translation"))
        category = _clean(row.get("category") or row.get("type")) or "term"
        policy = TERMINOLOGY_POLICY_LOCKED if bool(row.get("locked", True)) else TERMINOLOGY_POLICY_PREFERRED
        return {"source": source_text, "target": target_text, "allowedTranslations": [target_text] if target_text else [], "type": category, "policy": policy, "status": TERMINOLOGY_STATUS_CONFIRMED if target_text else "candidate", "sourceStore": source}

    @staticmethod
    def _is_active_row(row: dict[str, Any], source_text: str) -> bool:
        source = _clean(row.get("source"))
        target = _clean(row.get("target"))
        return bool(source and target and (not source_text or source in source_text))

    def _pairs_from_translation_decisions(self, draft: dict[str, Any]) -> list[dict[str, Any]]:
        pairs: list[dict[str, Any]] = []
        for decision in draft.get("translation_decisions") or []:
            if not isinstance(decision, dict):
                continue
            source = _clean(decision.get("source_span"))
            target = _clean(decision.get("translated_span"))
            if not self._valid_pair(source, target):
                continue
            pairs.append({"source_text_ko": source, "target_text": target, "category": self._category_from_source(source, decision), "policy": TERMINOLOGY_POLICY_LOCKED, "reason_ko": _clean(decision.get("reason"))})
        return self._dedupe_pairs(pairs)

    @staticmethod
    def _valid_pair(source: str, target: str) -> bool:
        if not source or not target or target in _TRANSLATION_SPAN_REJECT:
            return False
        if len(source) > 40 or len(target) > 100:
            return False
        # Avoid saving full sentences as glossary entries.
        if len(source) > 18 and any(mark in source for mark in (" ", "\n", "다.", "요.", "했다", "였다")):
            return False
        return True

    @staticmethod
    def _category_from_source(source: str, decision: dict[str, Any]) -> str:
        decision_type = _clean(decision.get("decision_type")).lower()
        if "name" in decision_type:
            return "proper_noun"
        if "term" in decision_type:
            return "term"
        if re.fullmatch(r"[가-힣]{2,4}", source):
            return "character_name"
        if any(token in source for token in ("팀", "구단", "회사", "그룹", "재단", "학원", "학교", "길드", "왕국", "제국", "연맹", "협회")):
            return "organization_name"
        if any(token in source for token in ("동", "시", "군", "구", "역", "산", "강", "마을", "거리", "궁", "성", "광장", "공원")):
            return "place_name"
        return "term"

    @staticmethod
    def _dedupe_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str]] = set()
        result: list[dict[str, Any]] = []
        for pair in pairs:
            key = (_clean(pair.get("source_text_ko")), _clean(pair.get("target_text")))
            if key[0] and key[1] and key not in seen:
                seen.add(key)
                result.append(pair)
        return result

    def _upsert_glossary_pair(self, glossary: dict[str, Any], pair: dict[str, Any], *, episode_id: int | str | None, source: str, now: str) -> str | dict[str, Any]:
        source_text = _clean(pair.get("source_text_ko"))
        target_text = _clean(pair.get("target_text"))
        if not source_text or not target_text:
            return "skipped"
        items = glossary.setdefault("items", [])
        for item in items:
            if _clean(item.get("source_text_ko")) != source_text or _clean(item.get("target_language")) != self.target_language:
                continue
            existing_target = _clean(item.get("target_text"))
            if existing_target and existing_target != target_text:
                conflict = {"type": "glossary_translation_conflict", "source_text_ko": source_text, "existing_target": existing_target, "new_target": target_text, "episode_id": episode_id, "source": source, "created_at": now}
                glossary.setdefault("conflicts", []).append(conflict)
                return conflict
            item.update({"target_text": target_text, "category": _clean(item.get("category") or pair.get("category")) or "term", "last_used_episode_id": episode_id, "use_count": int(item.get("use_count") or 0) + 1, "updated_at": now})
            return "updated"
        items.append({"source_text_ko": source_text, "target_language": self.target_language, "target_text": target_text, "category": _clean(pair.get("category")) or "term", "policy": _clean(pair.get("policy")) or TERMINOLOGY_POLICY_LOCKED, "locked": True, "source": source, "reason_ko": _clean(pair.get("reason_ko")), "first_episode_id": episode_id, "last_used_episode_id": episode_id, "use_count": 1, "created_at": now, "updated_at": now})
        return "added"

    def _append_memory(self, memory: dict[str, Any], *, source_text: str, translated_text: str, episode_id: int | str | None, now: str) -> None:
        items = memory.setdefault("items", [])
        key = (str(episode_id), self.target_language)
        for item in items:
            if (str(item.get("episode_id")), _clean(item.get("target_language"))) == key:
                item.update({"source_length": len(source_text or ""), "target_length": len(translated_text or ""), "updated_at": now})
                memory["updated_at"] = now
                return
        items.append({"episode_id": episode_id, "target_language": self.target_language, "source_length": len(source_text or ""), "target_length": len(translated_text or ""), "source": "translation_result", "created_at": now, "updated_at": now})
        memory["updated_at"] = now
