from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from .v3_literary_package import GlossaryEntry, WorkMemory

GLOSSARY_CATEGORIES = {
    "person",
    "place",
    "organization",
    "skill",
    "system_term",
    "genre_term",
    "honorific",
    "idiom",
    "title",
    "epithet",
    "other",
}
GLOSSARY_PRIORITIES = {"hard", "soft"}
GLOSSARY_STATUSES = {"candidate", "approved", "rejected", "deprecated"}
CANDIDATE_STATUSES = {"pending", "approved", "rejected", "merged"}
_CONTEXTUAL_REFERENCES_KO = {
    "그",
    "그녀",
    "남자",
    "여자",
    "저 남자",
    "그 남자",
    "이 남자",
    "저 여자",
    "그 여자",
    "이 여자",
    "그분",
    "이분",
    "저분",
    "이 사람",
    "저 사람",
    "그 사람",
    "그 자",
    "저 자",
    "이 자",
}
_KOREAN_REFERENCE_PARTICLES = ("은", "는", "이", "가", "을", "를", "에게", "한테", "께", "도", "만", "와", "과", "의")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def is_contextual_reference(text: str) -> bool:
    """Return True for clear Korean pronouns/deictic references.

    These references are intentionally excluded from persisted glossary aliases
    because their referent can change by episode or scene.
    """

    normalized = " ".join(_clean(text).split())
    if normalized in _CONTEXTUAL_REFERENCES_KO:
        return True
    for particle in _KOREAN_REFERENCE_PARTICLES:
        if normalized.endswith(particle) and normalized[: -len(particle)] in _CONTEXTUAL_REFERENCES_KO:
            return True
    return False


def _is_case_marked_variant(reference: str, canonical_source: str) -> bool:
    reference_text = _clean(reference)
    source_text = _clean(canonical_source)
    if not reference_text or not source_text or reference_text == source_text:
        return False
    for particle in _KOREAN_REFERENCE_PARTICLES:
        if reference_text == f"{source_text}{particle}":
            return True
    return False


def should_persist_as_glossary_candidate(source: str, category: str, confidence: float | None = None) -> bool:
    """Conservative persistence gate for glossary candidates.

    Proper names, titles, and repeated epithets can become long-term memory.
    Clear pronouns/deictic common nouns should remain source-analyzer evidence,
    not hard glossary aliases.
    """

    del confidence
    source_text = _clean(source)
    if not source_text or is_contextual_reference(source_text):
        return False
    normalized_category = _clean(category) or "other"
    if normalized_category not in GLOSSARY_CATEGORIES:
        normalized_category = "other"
    return True


@dataclass(slots=True)
class GlossaryAliasRecord:
    id: int | None
    glossary_entry_id: int
    alias_source: str
    alias_type: str = "other"
    note: str | None = None
    created_at: str = field(default_factory=_now_iso)


@dataclass(slots=True)
class GlossaryForbiddenTermRecord:
    id: int | None
    glossary_entry_id: int
    forbidden_target: str
    reason: str | None = None
    severity: str = "P1"
    created_at: str = field(default_factory=_now_iso)


@dataclass(slots=True)
class GlossaryEntryRecord:
    id: int | None
    work_id: str
    target_locale: str
    source: str
    target: str
    category: str = "other"
    priority: str = "soft"
    status: str = "approved"
    note: str | None = None
    created_by: str = "system"
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    aliases: list[GlossaryAliasRecord] = field(default_factory=list)
    forbidden_terms: list[GlossaryForbiddenTermRecord] = field(default_factory=list)


@dataclass(slots=True)
class GlossaryCandidateRecord:
    id: int | None
    work_id: str
    episode_id: str | None
    target_locale: str
    source: str
    suggested_target: str
    category: str = "other"
    confidence: float | None = None
    source_span: str | None = None
    reason: str | None = None
    aliases: list[str] = field(default_factory=list)
    status: str = "pending"
    merged_entry_id: int | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


class GlossaryRepository(Protocol):
    def upsert_entry(
        self,
        *,
        work_id: str,
        target_locale: str,
        source: str,
        target: str,
        category: str = "other",
        priority: str = "soft",
        status: str = "approved",
        note: str | None = None,
        created_by: str = "system",
        aliases: list[str] | None = None,
        forbidden: list[str] | None = None,
    ) -> GlossaryEntryRecord:
        ...

    def list_approved_glossary(self, work_id: str, target_locale: str, *, limit: int = 50) -> list[GlossaryEntryRecord]:
        ...

    def list_glossary_candidates(
        self,
        work_id: str,
        target_locale: str,
        *,
        status: str | None = None,
    ) -> list[GlossaryCandidateRecord]:
        ...

    def get_glossary_candidate(self, candidate_id: int) -> GlossaryCandidateRecord | None:
        ...

    def hydrate_work_memory(self, work_id: str, target_locale: str, *, limit: int = 50) -> WorkMemory | None:
        ...

    def create_glossary_candidate(self, **payload: Any) -> GlossaryCandidateRecord:
        ...

    def approve_glossary_candidate(self, candidate_id: int, target_override: str | None = None) -> GlossaryCandidateRecord:
        ...

    def reject_glossary_candidate(self, candidate_id: int) -> GlossaryCandidateRecord:
        ...


def glossary_record_to_work_memory_entry(record: GlossaryEntryRecord) -> GlossaryEntry:
    return GlossaryEntry(
        source=record.source,
        target=record.target,
        category=record.category if record.category in GLOSSARY_CATEGORIES else "other",
        priority=record.priority if record.priority in GLOSSARY_PRIORITIES else "soft",
        aliases=[
            row.alias_source
            for row in record.aliases
            if _clean(row.alias_source) and not is_contextual_reference(row.alias_source)
        ],
        forbidden=[row.forbidden_target for row in record.forbidden_terms if _clean(row.forbidden_target)],
        note=record.note,
    )


def hydrate_work_memory_from_records(
    work_id: str,
    target_locale: str,
    records: list[GlossaryEntryRecord],
    *,
    limit: int = 50,
) -> WorkMemory | None:
    approved = [row for row in records if row.status == "approved"]
    approved.sort(key=lambda row: (0 if row.priority == "hard" else 1, row.source.casefold(), row.category))
    selected = approved[: max(0, limit)]
    if not selected:
        return None
    return WorkMemory(
        workId=_clean(work_id) or None,
        targetLocale=_clean(target_locale),
        approvedGlossary=[glossary_record_to_work_memory_entry(row) for row in selected],
        styleMemory={},
        previousSummary=None,
    )


class InMemoryGlossaryRepository:
    """Process-local MVP glossary repository with RDB-shaped records.

    This mirrors the future MySQL schema without adding a database framework to a
    project that currently uses in-memory persistence.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[int, GlossaryEntryRecord] = {}
        self._candidates: dict[int, GlossaryCandidateRecord] = {}
        self._next_entry_id = 1
        self._next_alias_id = 1
        self._next_forbidden_id = 1
        self._next_candidate_id = 1

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._candidates.clear()
            self._next_entry_id = 1
            self._next_alias_id = 1
            self._next_forbidden_id = 1
            self._next_candidate_id = 1

    def upsert_entry(
        self,
        *,
        work_id: str,
        target_locale: str,
        source: str,
        target: str,
        category: str = "other",
        priority: str = "soft",
        status: str = "approved",
        note: str | None = None,
        created_by: str = "system",
        aliases: list[str] | None = None,
        forbidden: list[str] | None = None,
    ) -> GlossaryEntryRecord:
        work_id = _clean(work_id)
        target_locale = _clean(target_locale)
        source = _clean(source)
        target = _clean(target)
        if not work_id or not target_locale or not source or not target:
            raise ValueError("work_id, target_locale, source, and target are required")
        category = category if category in GLOSSARY_CATEGORIES else "other"
        priority = priority if priority in GLOSSARY_PRIORITIES else "soft"
        status = status if status in GLOSSARY_STATUSES else "candidate"
        if not should_persist_as_glossary_candidate(source, category):
            raise ValueError("source is a contextual reference and should not be persisted as a glossary entry")
        with self._lock:
            existing = next(
                (
                    row
                    for row in self._entries.values()
                    if row.work_id == work_id
                    and row.target_locale == target_locale
                    and row.source == source
                    and row.category == category
                ),
                None,
            )
            now = _now_iso()
            if existing is None:
                entry_id = self._next_entry_id
                self._next_entry_id += 1
                existing = GlossaryEntryRecord(
                    id=entry_id,
                    work_id=work_id,
                    target_locale=target_locale,
                    source=source,
                    target=target,
                    category=category,
                    priority=priority,
                    status=status,
                    note=note,
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                )
                self._entries[entry_id] = existing
            else:
                existing.target = target
                existing.priority = priority
                existing.status = status
                existing.note = note
                existing.created_by = created_by
                existing.updated_at = now
                existing.aliases.clear()
                existing.forbidden_terms.clear()
            for alias in aliases or []:
                alias_source = _clean(alias)
                if (
                    alias_source
                    and alias_source != source
                    and not _is_case_marked_variant(alias_source, source)
                    and should_persist_as_glossary_candidate(alias_source, "epithet")
                ):
                    existing.aliases.append(
                        GlossaryAliasRecord(id=self._next_alias_id, glossary_entry_id=int(existing.id), alias_source=alias_source)
                    )
                    self._next_alias_id += 1
            for forbidden_target in forbidden or []:
                forbidden_text = _clean(forbidden_target)
                if forbidden_text:
                    existing.forbidden_terms.append(
                        GlossaryForbiddenTermRecord(
                            id=self._next_forbidden_id,
                            glossary_entry_id=int(existing.id),
                            forbidden_target=forbidden_text,
                        )
                    )
                    self._next_forbidden_id += 1
            return self._clone_entry(existing)

    def list_approved_glossary(self, work_id: str, target_locale: str, *, limit: int = 50) -> list[GlossaryEntryRecord]:
        with self._lock:
            rows = [
                self._clone_entry(row)
                for row in self._entries.values()
                if row.work_id == _clean(work_id) and row.target_locale == _clean(target_locale) and row.status == "approved"
            ]
        rows.sort(key=lambda row: (0 if row.priority == "hard" else 1, row.source.casefold(), row.category))
        return rows[: max(0, limit)]

    def hydrate_work_memory(self, work_id: str, target_locale: str, *, limit: int = 50) -> WorkMemory | None:
        records = self.list_approved_glossary(work_id, target_locale, limit=limit)
        return hydrate_work_memory_from_records(work_id, target_locale, records, limit=limit)

    def create_glossary_candidate(self, **payload: Any) -> GlossaryCandidateRecord:
        work_id = _clean(payload.get("work_id") or payload.get("workId"))
        target_locale = _clean(payload.get("target_locale") or payload.get("targetLocale"))
        source = _clean(payload.get("source"))
        suggested_target = _clean(payload.get("suggested_target") or payload.get("suggestedTarget"))
        if not work_id or not target_locale or not source or not suggested_target:
            raise ValueError("work_id, target_locale, source, and suggested_target are required")
        category = _clean(payload.get("category") or "other")
        if category not in GLOSSARY_CATEGORIES:
            category = "other"
        if not should_persist_as_glossary_candidate(source, category, payload.get("confidence")):
            raise ValueError("source is a contextual reference and should not be persisted as a glossary candidate")
        aliases = [
            alias
            for raw_alias in (payload.get("aliases") or [])
            if (alias := _clean(raw_alias))
            and alias != source
            and not _is_case_marked_variant(alias, source)
            and should_persist_as_glossary_candidate(alias, "epithet", payload.get("confidence"))
        ]
        status = _clean(payload.get("status") or "pending")
        if status not in CANDIDATE_STATUSES:
            status = "pending"
        with self._lock:
            candidate_id = self._next_candidate_id
            self._next_candidate_id += 1
            row = GlossaryCandidateRecord(
                id=candidate_id,
                work_id=work_id,
                episode_id=_clean(payload.get("episode_id") or payload.get("episodeId")) or None,
                target_locale=target_locale,
                source=source,
                suggested_target=suggested_target,
                category=category,
                confidence=payload.get("confidence"),
                source_span=_clean(payload.get("source_span") or payload.get("sourceSpan")) or None,
                reason=_clean(payload.get("reason")) or None,
                aliases=aliases,
                status=status,
            )
            self._candidates[candidate_id] = row
            return self._clone_candidate(row)

    def list_glossary_candidates(
        self,
        work_id: str,
        target_locale: str,
        *,
        status: str | None = None,
    ) -> list[GlossaryCandidateRecord]:
        normalized_status = _clean(status) or None
        with self._lock:
            rows = [
                self._clone_candidate(row)
                for row in self._candidates.values()
                if row.work_id == _clean(work_id)
                and row.target_locale == _clean(target_locale)
                and (normalized_status is None or row.status == normalized_status)
            ]
        rows.sort(key=lambda row: (row.created_at, int(row.id or 0)))
        return rows

    def get_glossary_candidate(self, candidate_id: int) -> GlossaryCandidateRecord | None:
        with self._lock:
            row = self._candidates.get(candidate_id)
            return self._clone_candidate(row) if row is not None else None

    def approve_glossary_candidate(self, candidate_id: int, target_override: str | None = None) -> GlossaryCandidateRecord:
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                raise ValueError(f"glossary candidate {candidate_id} not found")
            if not should_persist_as_glossary_candidate(candidate.source, candidate.category, candidate.confidence):
                raise ValueError("contextual reference candidate cannot be approved")
            candidate.status = "approved"
            candidate.updated_at = _now_iso()
        entry = self.upsert_entry(
            work_id=candidate.work_id,
            target_locale=candidate.target_locale,
            source=candidate.source,
            target=_clean(target_override) or candidate.suggested_target,
            category=candidate.category,
            priority="soft",
            status="approved",
            note=candidate.reason,
            created_by="system",
            aliases=candidate.aliases,
        )
        with self._lock:
            candidate.merged_entry_id = entry.id
            candidate.status = "merged"
            candidate.updated_at = _now_iso()
            return self._clone_candidate(candidate)

    def reject_glossary_candidate(self, candidate_id: int) -> GlossaryCandidateRecord:
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                raise ValueError(f"glossary candidate {candidate_id} not found")
            candidate.status = "rejected"
            candidate.updated_at = _now_iso()
            return self._clone_candidate(candidate)

    @staticmethod
    def _clone_entry(row: GlossaryEntryRecord) -> GlossaryEntryRecord:
        data = asdict(row)
        data["aliases"] = [GlossaryAliasRecord(**alias) for alias in data["aliases"]]
        data["forbidden_terms"] = [GlossaryForbiddenTermRecord(**term) for term in data["forbidden_terms"]]
        return GlossaryEntryRecord(**data)

    @staticmethod
    def _clone_candidate(row: GlossaryCandidateRecord) -> GlossaryCandidateRecord:
        return GlossaryCandidateRecord(**asdict(row))


def collect_glossary_candidate_inputs(v3_result: Any) -> list[dict[str, Any]]:
    """Extract future glossary candidate payloads from a v3 result.

    The current v3 package does not auto-create glossary candidates. This
    helper reserves a stable adapter seam for later source-analyzer and
    failure-signal integrations.
    """

    result = asdict(v3_result) if hasattr(v3_result, "__dataclass_fields__") else dict(v3_result or {})
    internal = result.get("internal") or {}
    candidates = internal.get("glossaryCandidates") or internal.get("glossary_candidates") or []
    rows: list[dict[str, Any]] = []

    def append_candidate(raw: dict[str, Any], *, default_category: str = "other") -> None:
        source = _clean(raw.get("canonical_name_ko") or raw.get("canonicalNameKo") or raw.get("source"))
        suggested_target = _clean(
            raw.get("canonical_name_target")
            or raw.get("canonicalNameTarget")
            or raw.get("suggested_target")
            or raw.get("suggestedTarget")
            or raw.get("target")
        )
        category = _clean(raw.get("category") or default_category)
        if category not in GLOSSARY_CATEGORIES:
            category = default_category if default_category in GLOSSARY_CATEGORIES else "other"
        if not should_persist_as_glossary_candidate(source, category, raw.get("confidence")):
            return
        references = raw.get("references_ko") or raw.get("referencesKo") or raw.get("aliases") or []
        aliases = [
            _clean(reference)
            for reference in references
            if _clean(reference)
            and _clean(reference) != source
            and not _is_case_marked_variant(_clean(reference), source)
            and should_persist_as_glossary_candidate(_clean(reference), "epithet", raw.get("confidence"))
        ]
        row = dict(raw)
        row["source"] = source
        if suggested_target:
            row["suggested_target"] = suggested_target
        row["category"] = category
        if raw.get("sourceSpan") and not raw.get("source_span"):
            row["source_span"] = raw.get("sourceSpan")
        if aliases:
            row["aliases"] = aliases
        elif "aliases" in row:
            row["aliases"] = []
        rows.append(row)

    for candidate in candidates:
        if isinstance(candidate, dict):
            append_candidate(candidate)
    entity_groups = [
        internal.get("characterReferences") or [],
        internal.get("character_references") or [],
        internal.get("entityCandidates") or [],
        internal.get("entity_candidates") or [],
    ]
    for entity_group in entity_groups:
        for entity in entity_group:
            if isinstance(entity, dict):
                append_candidate(entity, default_category=_clean(entity.get("category") or "other"))
    return rows


default_glossary_repository = InMemoryGlossaryRepository()
