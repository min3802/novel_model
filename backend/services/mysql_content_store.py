"""MySQL implementation for core content persistence.

This module intentionally uses PyMySQL directly. It is a repository-layer
adapter only; application startup must not create or migrate schema.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

from backend.services.content_store import ContentRepository, JSON_FIELDS

try:  # optional dependency for memory-only development
    import pymysql  # type: ignore
    from pymysql.cursors import DictCursor  # type: ignore
except Exception:  # pragma: no cover - exercised by skip paths
    pymysql = None  # type: ignore
    DictCursor = None  # type: ignore


class MySQLContentRepository(ContentRepository):
    """Content repository backed by scripts/sql/core_schema_mysql.sql."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        charset: str = "utf8mb4",
        connect_timeout: int = 3,
    ) -> None:
        if pymysql is None:
            raise RuntimeError("PyMySQL is not installed")
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.charset = charset
        self.connect_timeout = connect_timeout

    @classmethod
    def from_env(cls) -> "MySQLContentRepository":
        database = os.getenv("MYSQL_DATABASE", "").strip()
        user = os.getenv("MYSQL_USER", "").strip()
        if not database or not user:
            raise RuntimeError("MYSQL_DATABASE and MYSQL_USER are required")
        return cls(
            host=os.getenv("MYSQL_HOST", "127.0.0.1").strip(),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            database=database,
            user=user,
            password=os.getenv("MYSQL_PASSWORD", ""),
            charset=os.getenv("MYSQL_CHARSET", "utf8mb4").strip() or "utf8mb4",
            connect_timeout=int(os.getenv("MYSQL_CONNECT_TIMEOUT", "3")),
        )

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            charset=self.charset,
            autocommit=False,
            connect_timeout=self.connect_timeout,
            cursorclass=DictCursor,
        )

    def ping(self) -> bool:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return bool(cur.fetchone())
        finally:
            conn.close()

    def _ensure_user(self, cur: Any, user_id: int) -> None:
        cur.execute(
            """
            INSERT IGNORE INTO users (user_id, email, nickname, status)
            VALUES (%s, %s, %s, 'active')
            """,
            (user_id, f"content-user-{user_id}@local.invalid", f"User {user_id}"),
        )

    def _row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        out: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (datetime, date)):
                out[key] = value.isoformat()
            elif key in JSON_FIELDS and isinstance(value, str):
                try:
                    out[key] = json.loads(value)
                except Exception:
                    out[key] = value
            else:
                out[key] = value
        return out

    def _json_value(self, value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def upsert_work(self, data: dict[str, Any]) -> dict[str, Any]:
        user_id = int(data.get("user_id") or 1)
        work_id = data.get("work_id")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                self._ensure_user(cur, user_id)
                if work_id:
                    cur.execute(
                        """
                        UPDATE works
                           SET user_id=%s, title=%s, pen_name=%s, genre=%s, synopsis=%s,
                               source_locale=%s, default_target_country=%s, status=%s
                         WHERE work_id=%s
                        """,
                        (
                            user_id,
                            str(data.get("title") or "").strip(),
                            data.get("pen_name"),
                            data.get("genre"),
                            data.get("synopsis"),
                            data.get("source_locale") or "KO",
                            data.get("default_target_country"),
                            data.get("status") or "active",
                            int(work_id),
                        ),
                    )
                    new_id = int(work_id)
                else:
                    cur.execute(
                        """
                        INSERT INTO works
                            (user_id, title, pen_name, genre, synopsis, source_locale, default_target_country, status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            user_id,
                            str(data.get("title") or "").strip(),
                            data.get("pen_name"),
                            data.get("genre"),
                            data.get("synopsis"),
                            data.get("source_locale") or "KO",
                            data.get("default_target_country"),
                            data.get("status") or "active",
                        ),
                    )
                    new_id = int(cur.lastrowid)
            conn.commit()
            item = self.get_work(new_id)
            if not item:
                raise RuntimeError("work upsert did not return a row")
            return item
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_work(self, work_id: Any) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM works WHERE work_id=%s", (int(work_id),))
                return self._row(cur.fetchone())
        finally:
            conn.close()

    def list_works(self, user_id: Any = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if user_id is None:
                    cur.execute("SELECT * FROM works ORDER BY work_id DESC LIMIT %s OFFSET %s", (int(limit), int(offset)))
                else:
                    cur.execute(
                        "SELECT * FROM works WHERE user_id=%s ORDER BY work_id DESC LIMIT %s OFFSET %s",
                        (int(user_id), int(limit), int(offset)),
                    )
                return [self._row(row) or {} for row in cur.fetchall()]
        finally:
            conn.close()

    def archive_work(self, work_id: Any) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE works SET status='archived' WHERE work_id=%s", (int(work_id),))
            conn.commit()
            return self.get_work(work_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def upsert_episode(self, data: dict[str, Any]) -> dict[str, Any]:
        episode_id = data.get("episode_id")
        original_text = str(data.get("original_text") or "")
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                if episode_id:
                    cur.execute(
                        """
                        UPDATE episodes
                           SET work_id=%s, episode_no=%s, title=%s, original_text=%s,
                               source_text_hash=%s, char_count=%s, status=%s
                         WHERE episode_id=%s
                        """,
                        (
                            int(data["work_id"]),
                            data.get("episode_no"),
                            str(data.get("title") or "").strip(),
                            original_text,
                            data.get("source_text_hash"),
                            data.get("char_count") if data.get("char_count") is not None else len(original_text),
                            data.get("status") or "ready",
                            int(episode_id),
                        ),
                    )
                    new_id = int(episode_id)
                else:
                    cur.execute(
                        """
                        INSERT INTO episodes
                            (work_id, episode_no, title, original_text, source_text_hash, char_count, status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            int(data["work_id"]),
                            data.get("episode_no"),
                            str(data.get("title") or "").strip(),
                            original_text,
                            data.get("source_text_hash"),
                            data.get("char_count") if data.get("char_count") is not None else len(original_text),
                            data.get("status") or "ready",
                        ),
                    )
                    new_id = int(cur.lastrowid)
            conn.commit()
            item = self.get_episode(new_id)
            if not item:
                raise RuntimeError("episode upsert did not return a row")
            return item
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_episode(self, episode_id: Any) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM episodes WHERE episode_id=%s", (int(episode_id),))
                return self._row(cur.fetchone())
        finally:
            conn.close()

    def list_episodes(self, work_id: Any, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM episodes WHERE work_id=%s ORDER BY episode_no IS NULL, episode_no, episode_id LIMIT %s OFFSET %s",
                    (int(work_id), int(limit), int(offset)),
                )
                return [self._row(row) or {} for row in cur.fetchall()]
        finally:
            conn.close()

    def archive_episode(self, episode_id: Any) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE episodes SET status='archived' WHERE episode_id=%s", (int(episode_id),))
            conn.commit()
            return self.get_episode(episode_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def save_translation_result(self, data: dict[str, Any]) -> dict[str, Any]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO translation_results
                        (work_id, episode_id, target_country, target_locale, pipeline, delivery_status,
                         translated_text, translation_rationale, qa_issues, author_review_cards,
                         metadata, internal, model_name, source_text_hash)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        int(data["work_id"]),
                        int(data["episode_id"]),
                        data["target_country"],
                        data["target_locale"],
                        data.get("pipeline") or data.get("mode") or "unknown",
                        data.get("delivery_status") or "deliverable",
                        str(data.get("translated_text") or ""),
                        self._json_value(data.get("translation_rationale")),
                        self._json_value(data.get("qa_issues")),
                        self._json_value(data.get("author_review_cards")),
                        self._json_value(data.get("metadata")),
                        self._json_value(data.get("internal")),
                        data.get("model_name"),
                        data.get("source_text_hash"),
                    ),
                )
                new_id = int(cur.lastrowid)
            conn.commit()
            item = self.get_translation(new_id)
            if not item:
                raise RuntimeError("translation save did not return a row")
            return item
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_translation(self, translation_id: Any) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM translation_results WHERE translation_id=%s", (int(translation_id),))
                return self._row(cur.fetchone())
        finally:
            conn.close()

    def list_translations(
        self,
        work_id: Any = None,
        episode_id: Any = None,
        target_country: str | None = None,
        target_locale: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if work_id is not None:
            clauses.append("work_id=%s")
            params.append(int(work_id))
        if episode_id is not None:
            clauses.append("episode_id=%s")
            params.append(int(episode_id))
        if target_country:
            clauses.append("target_country=%s")
            params.append(target_country)
        if target_locale:
            clauses.append("target_locale=%s")
            params.append(target_locale)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([int(limit), int(offset)])
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM translation_results{where} ORDER BY translation_id DESC LIMIT %s OFFSET %s",
                    tuple(params),
                )
                return [self._row(row) or {} for row in cur.fetchall()]
        finally:
            conn.close()

    def get_latest_translation(
        self, episode_id: Any, target_country: str | None = None, target_locale: str | None = None
    ) -> dict[str, Any] | None:
        rows = self.list_translations(
            episode_id=episode_id,
            target_country=target_country,
            target_locale=target_locale,
            limit=1,
            offset=0,
        )
        return rows[0] if rows else None
