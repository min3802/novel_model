from __future__ import annotations

import importlib
import json
import os
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Iterator

from .glossary_store import (
    CANDIDATE_STATUSES,
    GLOSSARY_CATEGORIES,
    GLOSSARY_PRIORITIES,
    GLOSSARY_STATUSES,
    GlossaryAliasRecord,
    GlossaryCandidateRecord,
    GlossaryEntryRecord,
    GlossaryForbiddenTermRecord,
    GlossaryRepository,
    WorkMemory,
    _clean,
    _is_case_marked_variant,
    hydrate_work_memory_from_records,
    should_persist_as_glossary_candidate,
)


class MySQLDriverUnavailable(RuntimeError):
    pass


def normalize_mysql_work_id(value: Any) -> int:
    """Return a numeric works.work_id for the final MySQL glossary schema."""

    if value is None or value == "":
        raise ValueError("work_id is required")
    try:
        work_id = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("work_id must be a numeric works.work_id for the MySQL glossary backend") from exc
    if work_id <= 0:
        raise ValueError("work_id must be a positive numeric works.work_id for the MySQL glossary backend")
    return work_id


def normalize_optional_episode_id(value: Any) -> int | None:
    """Return a nullable numeric episodes.episode_id for MySQL glossary candidates."""

    if value is None or value == "":
        return None
    try:
        episode_id = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("episode_id must be a numeric episodes.episode_id for the MySQL glossary backend") from exc
    if episode_id <= 0:
        raise ValueError("episode_id must be a positive numeric episodes.episode_id for the MySQL glossary backend")
    return episode_id


def _load_driver() -> tuple[str, Any]:
    """Load an installed MySQL DB-API driver without requiring a dependency.

    Preference is PyMySQL because it is pure Python and declared in
    requirements.txt, then mysql-connector-python if present.
    """

    try:
        return "pymysql", importlib.import_module("pymysql")
    except ImportError:
        pass
    try:
        return "mysql.connector", importlib.import_module("mysql.connector")
    except ImportError as exc:
        raise MySQLDriverUnavailable(
            "No MySQL client installed. Install PyMySQL or mysql-connector-python to use MySQLGlossaryRepository."
        ) from exc


class MySQLGlossaryRepository(GlossaryRepository):
    """MySQL 8.x implementation of the glossary repository contract.

    This class assumes the current glossary DDL in docs/glossary_rdb_schema.md
    has already been applied after the core content schema. It intentionally
    does not create or migrate schema.

    The final MySQL path expects numeric IDs aligned with the content ERD:
    ``work_id`` is ``works.work_id`` and candidate ``episode_id`` is nullable
    ``episodes.episode_id``. The in-memory repository may still accept legacy
    string IDs for tests and development.
    """

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        charset: str | None = None,
        connect_timeout: int | None = None,
    ) -> None:
        self.host = host or os.getenv("MYSQL_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("MYSQL_PORT", "3306"))
        self.database = database or os.getenv("MYSQL_DATABASE", "")
        self.user = user or os.getenv("MYSQL_USER", "")
        self.password = password if password is not None else os.getenv("MYSQL_PASSWORD", "")
        self.charset = charset or os.getenv("MYSQL_CHARSET", "utf8mb4")
        self.connect_timeout = int(connect_timeout or os.getenv("MYSQL_CONNECT_TIMEOUT", "3"))
        self._driver_name, self._driver = _load_driver()
        if not self.database or not self.user:
            raise ValueError("MYSQL_DATABASE and MYSQL_USER are required for MySQLGlossaryRepository")

    @classmethod
    def from_env(cls) -> "MySQLGlossaryRepository":
        return cls()

    def ping(self) -> None:
        """Open a connection and run a tiny query.

        The application never creates schema automatically. This check only
        proves that the configured driver, credentials, host, and database are
        usable before the repository factory advertises MySQL as available.
        """

        with self._connect() as conn, self._cursor(conn) as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._driver_name == "pymysql":
            conn = self._driver.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                charset=self.charset,
                autocommit=False,
                cursorclass=self._driver.cursors.DictCursor,
                connect_timeout=self.connect_timeout,
            )
        else:
            conn = self._driver.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                charset=self.charset,
                autocommit=False,
                connection_timeout=self.connect_timeout,
            )
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _cursor(self, conn: Any) -> Iterator[Any]:
        if self._driver_name == "mysql.connector":
            cur = conn.cursor(dictionary=True)
        else:
            cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    @staticmethod
    def _candidate_aliases(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, tuple):
            raw_items = list(value)
        else:
            raw_items = str(value).split("|")
        return [_clean(item) for item in raw_items if _clean(item)]

    @staticmethod
    def _normalize_entry_payload(
        *,
        work_id: str,
        target_locale: str,
        source: str,
        target: str,
        category: str,
        priority: str,
        status: str,
        note: str | None,
        created_by: str,
    ) -> dict[str, Any]:
        normalized = {
            "work_id": normalize_mysql_work_id(work_id),
            "target_locale": _clean(target_locale),
            "source": _clean(source),
            "target": _clean(target),
            "category": category if category in GLOSSARY_CATEGORIES else "other",
            "priority": priority if priority in GLOSSARY_PRIORITIES else "soft",
            "status": status if status in GLOSSARY_STATUSES else "candidate",
            "note": note,
            "created_by": created_by if created_by in {"user", "system", "admin"} else "system",
        }
        if not normalized["target_locale"] or not normalized["source"] or not normalized["target"]:
            raise ValueError("work_id, target_locale, source, and target are required")
        if not should_persist_as_glossary_candidate(normalized["source"], normalized["category"]):
            raise ValueError("source is a contextual reference and should not be persisted as a glossary entry")
        return normalized

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
        payload = self._normalize_entry_payload(
            work_id=work_id,
            target_locale=target_locale,
            source=source,
            target=target,
            category=category,
            priority=priority,
            status=status,
            note=note,
            created_by=created_by,
        )
        filtered_aliases = [
            alias
            for raw_alias in aliases or []
            if (alias := _clean(raw_alias))
            and alias != payload["source"]
            and not _is_case_marked_variant(alias, payload["source"])
            and should_persist_as_glossary_candidate(alias, "epithet")
        ]
        filtered_forbidden = [_clean(item) for item in forbidden or [] if _clean(item)]
        with self._connect() as conn:
            try:
                with self._cursor(conn) as cur:
                    cur.execute(
                        """
                        SELECT id FROM glossary_entries
                        WHERE work_id=%s AND target_locale=%s AND source=%s AND category=%s
                        LIMIT 1
                        """,
                        (payload["work_id"], payload["target_locale"], payload["source"], payload["category"]),
                    )
                    existing = cur.fetchone()
                    if existing:
                        entry_id = int(existing["id"])
                        cur.execute(
                            """
                            UPDATE glossary_entries
                            SET target=%s, priority=%s, status=%s, note=%s, created_by=%s
                            WHERE id=%s
                            """,
                            (
                                payload["target"],
                                payload["priority"],
                                payload["status"],
                                payload["note"],
                                payload["created_by"],
                                entry_id,
                            ),
                        )
                        cur.execute("DELETE FROM glossary_aliases WHERE glossary_entry_id=%s", (entry_id,))
                        cur.execute("DELETE FROM glossary_forbidden_terms WHERE glossary_entry_id=%s", (entry_id,))
                    else:
                        cur.execute(
                            """
                            INSERT INTO glossary_entries
                            (work_id, target_locale, source, target, category, priority, status, note, created_by)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (
                                payload["work_id"],
                                payload["target_locale"],
                                payload["source"],
                                payload["target"],
                                payload["category"],
                                payload["priority"],
                                payload["status"],
                                payload["note"],
                                payload["created_by"],
                            ),
                        )
                        entry_id = int(cur.lastrowid)
                    for alias in filtered_aliases:
                        cur.execute(
                            """
                            INSERT INTO glossary_aliases (glossary_entry_id, alias_source, alias_type)
                            VALUES (%s,%s,%s)
                            """,
                            (entry_id, alias, "other"),
                        )
                    for forbidden_target in filtered_forbidden:
                        cur.execute(
                            """
                            INSERT INTO glossary_forbidden_terms (glossary_entry_id, forbidden_target, severity)
                            VALUES (%s,%s,%s)
                            """,
                            (entry_id, forbidden_target, "P1"),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        rows = self._fetch_entries_by_ids([entry_id])
        return rows[0]

    def list_approved_glossary(self, work_id: str, target_locale: str, *, limit: int = 50) -> list[GlossaryEntryRecord]:
        normalized_work_id = normalize_mysql_work_id(work_id)
        with self._connect() as conn, self._cursor(conn) as cur:
            cur.execute(
                """
                SELECT * FROM glossary_entries
                WHERE work_id=%s AND target_locale=%s AND status='approved'
                ORDER BY CASE priority WHEN 'hard' THEN 0 ELSE 1 END, source, category
                LIMIT %s
                """,
                (normalized_work_id, _clean(target_locale), max(0, int(limit))),
            )
            entry_rows = cur.fetchall()
        return self._rows_to_entries(entry_rows)

    def hydrate_work_memory(self, work_id: str, target_locale: str, *, limit: int = 50) -> WorkMemory | None:
        records = self.list_approved_glossary(work_id, target_locale, limit=limit)
        return hydrate_work_memory_from_records(work_id, target_locale, records, limit=limit)

    def create_glossary_candidate(self, **payload: Any) -> GlossaryCandidateRecord:
        work_id = normalize_mysql_work_id(payload.get("work_id") or payload.get("workId"))
        episode_id = normalize_optional_episode_id(payload.get("episode_id") or payload.get("episodeId"))
        target_locale = _clean(payload.get("target_locale") or payload.get("targetLocale"))
        source = _clean(payload.get("source"))
        suggested_target = _clean(payload.get("suggested_target") or payload.get("suggestedTarget"))
        category = _clean(payload.get("category") or "other")
        if category not in GLOSSARY_CATEGORIES:
            category = "other"
        if not target_locale or not source or not suggested_target:
            raise ValueError("work_id, target_locale, source, and suggested_target are required")
        if not should_persist_as_glossary_candidate(source, category, payload.get("confidence")):
            raise ValueError("source is a contextual reference and should not be persisted as a glossary candidate")
        aliases = [
            alias
            for raw_alias in self._candidate_aliases(payload.get("aliases"))
            if (alias := _clean(raw_alias))
            and alias != source
            and not _is_case_marked_variant(alias, source)
            and should_persist_as_glossary_candidate(alias, "epithet", payload.get("confidence"))
        ]
        status = _clean(payload.get("status") or "pending")
        if status not in CANDIDATE_STATUSES:
            status = "pending"
        with self._connect() as conn:
            try:
                with self._cursor(conn) as cur:
                    cur.execute(
                        """
                        INSERT INTO glossary_candidates
                        (work_id, episode_id, target_locale, source, suggested_target, category,
                         confidence, source_span, reason, aliases, status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            work_id,
                            episode_id,
                            target_locale,
                            source,
                            suggested_target,
                            category,
                            payload.get("confidence"),
                            _clean(payload.get("source_span") or payload.get("sourceSpan")) or None,
                            _clean(payload.get("reason")) or None,
                            json.dumps(aliases, ensure_ascii=False) if aliases else None,
                            status,
                        ),
                    )
                    candidate_id = int(cur.lastrowid)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        row = self.get_glossary_candidate(candidate_id)
        if row is None:
            raise RuntimeError(f"glossary candidate {candidate_id} was not found after insert")
        if aliases and not row.aliases:
            row.aliases = aliases
        return row

    def list_glossary_candidates(
        self,
        work_id: str,
        target_locale: str,
        *,
        status: str | None = None,
    ) -> list[GlossaryCandidateRecord]:
        params: list[Any] = [normalize_mysql_work_id(work_id), _clean(target_locale)]
        status_clause = ""
        if _clean(status):
            status_clause = " AND status=%s"
            params.append(_clean(status))
        with self._connect() as conn, self._cursor(conn) as cur:
            cur.execute(
                f"""
                SELECT * FROM glossary_candidates
                WHERE work_id=%s AND target_locale=%s{status_clause}
                ORDER BY created_at, id
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def get_glossary_candidate(self, candidate_id: int) -> GlossaryCandidateRecord | None:
        with self._connect() as conn, self._cursor(conn) as cur:
            cur.execute("SELECT * FROM glossary_candidates WHERE id=%s", (candidate_id,))
            row = cur.fetchone()
        return self._row_to_candidate(row) if row else None

    def approve_glossary_candidate(self, candidate_id: int, target_override: str | None = None) -> GlossaryCandidateRecord:
        candidate = self.get_glossary_candidate(candidate_id)
        if candidate is None:
            raise ValueError(f"glossary candidate {candidate_id} not found")
        if not should_persist_as_glossary_candidate(candidate.source, candidate.category, candidate.confidence):
            raise ValueError("contextual reference candidate cannot be approved")
        target = _clean(target_override) or candidate.suggested_target
        work_id = normalize_mysql_work_id(candidate.work_id)
        with self._connect() as conn:
            try:
                with self._cursor(conn) as cur:
                    cur.execute(
                        """
                        SELECT id FROM glossary_entries
                        WHERE work_id=%s AND target_locale=%s AND source=%s AND category=%s
                        LIMIT 1
                        """,
                        (work_id, candidate.target_locale, candidate.source, candidate.category),
                    )
                    existing = cur.fetchone()
                    if existing:
                        entry_id = int(existing["id"])
                        cur.execute(
                            """
                            UPDATE glossary_entries
                            SET target=%s, priority=%s, status='approved', note=%s, created_by='system'
                            WHERE id=%s
                            """,
                            (target, "soft", candidate.reason, entry_id),
                        )
                        cur.execute("DELETE FROM glossary_aliases WHERE glossary_entry_id=%s", (entry_id,))
                    else:
                        cur.execute(
                            """
                            INSERT INTO glossary_entries
                            (work_id, target_locale, source, target, category, priority, status, note, created_by)
                            VALUES (%s,%s,%s,%s,%s,%s,'approved',%s,'system')
                            """,
                            (
                                work_id,
                                candidate.target_locale,
                                candidate.source,
                                target,
                                candidate.category,
                                "soft",
                                candidate.reason,
                            ),
                        )
                        entry_id = int(cur.lastrowid)
                    for alias in candidate.aliases:
                        if (
                            _clean(alias)
                            and _clean(alias) != candidate.source
                            and not _is_case_marked_variant(_clean(alias), candidate.source)
                            and should_persist_as_glossary_candidate(_clean(alias), "epithet", candidate.confidence)
                        ):
                            cur.execute(
                                """
                                INSERT INTO glossary_aliases (glossary_entry_id, alias_source, alias_type)
                                VALUES (%s,%s,%s)
                                """,
                                (entry_id, _clean(alias), "other"),
                            )
                    cur.execute(
                        """
                        UPDATE glossary_candidates
                        SET status='merged', merged_entry_id=%s
                        WHERE id=%s
                        """,
                        (entry_id, candidate_id),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        updated = self.get_glossary_candidate(candidate_id)
        if updated is None:
            raise RuntimeError(f"glossary candidate {candidate_id} was not found after approve")
        return updated

    def reject_glossary_candidate(self, candidate_id: int) -> GlossaryCandidateRecord:
        with self._connect() as conn:
            try:
                with self._cursor(conn) as cur:
                    cur.execute("UPDATE glossary_candidates SET status='rejected' WHERE id=%s", (candidate_id,))
                    if cur.rowcount == 0:
                        raise ValueError(f"glossary candidate {candidate_id} not found")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        row = self.get_glossary_candidate(candidate_id)
        if row is None:
            raise RuntimeError(f"glossary candidate {candidate_id} was not found after reject")
        return row

    def _fetch_entries_by_ids(self, entry_ids: list[int]) -> list[GlossaryEntryRecord]:
        if not entry_ids:
            return []
        placeholders = ",".join(["%s"] * len(entry_ids))
        with self._connect() as conn, self._cursor(conn) as cur:
            cur.execute(f"SELECT * FROM glossary_entries WHERE id IN ({placeholders})", tuple(entry_ids))
            rows = cur.fetchall()
        return self._rows_to_entries(rows)

    def _rows_to_entries(self, entry_rows: list[dict[str, Any]]) -> list[GlossaryEntryRecord]:
        if not entry_rows:
            return []
        entry_ids = [int(row["id"]) for row in entry_rows]
        placeholders = ",".join(["%s"] * len(entry_ids))
        with self._connect() as conn, self._cursor(conn) as cur:
            cur.execute(
                f"SELECT * FROM glossary_aliases WHERE glossary_entry_id IN ({placeholders}) ORDER BY id",
                tuple(entry_ids),
            )
            alias_rows = cur.fetchall()
            cur.execute(
                f"SELECT * FROM glossary_forbidden_terms WHERE glossary_entry_id IN ({placeholders}) ORDER BY id",
                tuple(entry_ids),
            )
            forbidden_rows = cur.fetchall()
        aliases_by_entry: dict[int, list[GlossaryAliasRecord]] = {}
        for row in alias_rows:
            aliases_by_entry.setdefault(int(row["glossary_entry_id"]), []).append(
                GlossaryAliasRecord(
                    id=int(row["id"]),
                    glossary_entry_id=int(row["glossary_entry_id"]),
                    alias_source=str(row["alias_source"]),
                    alias_type=str(row.get("alias_type") or "other"),
                    note=row.get("note"),
                    created_at=str(row.get("created_at") or ""),
                )
            )
        forbidden_by_entry: dict[int, list[GlossaryForbiddenTermRecord]] = {}
        for row in forbidden_rows:
            forbidden_by_entry.setdefault(int(row["glossary_entry_id"]), []).append(
                GlossaryForbiddenTermRecord(
                    id=int(row["id"]),
                    glossary_entry_id=int(row["glossary_entry_id"]),
                    forbidden_target=str(row["forbidden_target"]),
                    reason=row.get("reason"),
                    severity=str(row.get("severity") or "P1"),
                    created_at=str(row.get("created_at") or ""),
                )
            )
        entries = [self._row_to_entry(row, aliases_by_entry, forbidden_by_entry) for row in entry_rows]
        entries.sort(key=lambda row: (0 if row.priority == "hard" else 1, row.source.casefold(), row.category))
        return entries

    @staticmethod
    def _row_to_entry(
        row: dict[str, Any],
        aliases_by_entry: dict[int, list[GlossaryAliasRecord]],
        forbidden_by_entry: dict[int, list[GlossaryForbiddenTermRecord]],
    ) -> GlossaryEntryRecord:
        entry_id = int(row["id"])
        return GlossaryEntryRecord(
            id=entry_id,
            work_id=str(row["work_id"]),
            target_locale=str(row["target_locale"]),
            source=str(row["source"]),
            target=str(row["target"]),
            category=str(row.get("category") or "other"),
            priority=str(row.get("priority") or "soft"),
            status=str(row.get("status") or "approved"),
            note=row.get("note"),
            created_by=str(row.get("created_by") or "system"),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
            aliases=aliases_by_entry.get(entry_id, []),
            forbidden_terms=forbidden_by_entry.get(entry_id, []),
        )

    @classmethod
    def _row_to_candidate(cls, row: dict[str, Any]) -> GlossaryCandidateRecord:
        aliases: list[str] = []
        aliases_value = row.get("aliases")
        if isinstance(aliases_value, str) and aliases_value.strip():
            try:
                parsed_aliases = json.loads(aliases_value)
            except json.JSONDecodeError:
                parsed_aliases = aliases_value.split("|")
            aliases = cls._candidate_aliases(parsed_aliases)
        return GlossaryCandidateRecord(
            id=int(row["id"]),
            work_id=str(row["work_id"]),
            episode_id=str(row["episode_id"]) if row.get("episode_id") is not None else None,
            target_locale=str(row["target_locale"]),
            source=str(row["source"]),
            suggested_target=str(row["suggested_target"]),
            category=str(row.get("category") or "other"),
            confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
            source_span=row.get("source_span"),
            reason=row.get("reason"),
            aliases=aliases,
            status=str(row.get("status") or "pending"),
            merged_entry_id=int(row["merged_entry_id"]) if row.get("merged_entry_id") is not None else None,
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )


def as_debug_dict(row: Any) -> dict[str, Any]:
    return asdict(row) if hasattr(row, "__dataclass_fields__") else dict(row or {})
