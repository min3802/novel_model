from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
API_SERVER = ROOT / "api_server.py"
DEFAULT_INPUT_DIR = ROOT / "test_inputs" / "webnovel_20"
DEFAULT_REPORT_DIR = ROOT / "reports" / "batch_eval"
DEFAULT_WORK_IDENTITY_REGISTRY = ROOT / "reports" / "work_identity_registry.json"  # batch-eval-only cache
MAX_ORIGINAL_TEXT_CHARS = 8000
DEFAULT_REQUEST_TIMEOUT_SECONDS = 120.0
load_dotenv(ROOT / ".env")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.translation.locale_utils import country_to_locale  # noqa: E402


@dataclass(slots=True)
class HttpResponse:
    status: int
    body: bytes

    def json(self) -> dict[str, Any]:
        return json.loads(self.body.decode("utf-8") or "{}")


@dataclass(slots=True)
class EpisodeSource:
    episode_no: int
    path: Path
    title: str
    original_text: str

    @property
    def char_count(self) -> int:
        return len(self.original_text)


SEED_APPROVED_GLOSSARY: tuple[dict[str, str], ...] = (
    {"source": "낙원동", "target": "ナクウォンドン", "category": "place"},
    {"source": "강도윤", "target": "カン・ドユン", "category": "person"},
    {"source": "도윤", "target": "ドユン", "category": "person"},
    {"source": "윤서하", "target": "ユン・ソハ", "category": "person"},
    {"source": "민하린", "target": "ミン・ハリン", "category": "person"},
    {"source": "차민혁", "target": "チャ・ミンヒョク", "category": "person"},
    {"source": "한재민", "target": "ハン・ジェミン", "category": "person"},
    {"source": "철수", "target": "チョルス", "category": "person"},
    {"source": "콩이", "target": "コンイ", "category": "person"},
    {"source": "밤이", "target": "パミ", "category": "person"},
    {"source": "누수령", "target": "ヌスリョン", "category": "place"},
    {"source": "블루 타론", "target": "ブルータロン", "category": "organization"},
    {"source": "상태창", "target": "ステータスウィンドウ", "category": "system_term"},
    {"source": "헌터 협회", "target": "ハンター協会", "category": "organization"},
    {"source": "핵심 균열문", "target": "核心亀裂門", "category": "system_term"},
    {"source": "지하상가", "target": "地下商店街", "category": "place"},
)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_request(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> HttpResponse:
    headers = {"Accept": "application/json"}
    data = None
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False, default=_json_default).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return HttpResponse(status=int(response.status), body=response.read())
    except HTTPError as exc:
        return HttpResponse(status=int(exc.code), body=exc.read())


def _request_json(
    method: str,
    base_url: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout: float = 60,
) -> dict[str, Any]:
    response = _http_request(method, f"{base_url}{path}", json_body=json_body, timeout=timeout)
    payload = response.json()
    payload["_http_status"] = response.status
    return payload


def _request_error_details(exc: BaseException, *, operation: str, timeout: float) -> tuple[str, str]:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return f"{operation}_timeout", f"{operation.replace('_', ' ').title()} request timed out after {timeout:g} seconds"
    if isinstance(exc, HTTPError):
        return f"{operation}_http_error", f"{operation.replace('_', ' ').title()} request failed with HTTP {exc.code}"
    if isinstance(exc, AssertionError):
        return f"{operation}_error", f"{operation.replace('_', ' ').title()} request was rejected by the API"
    if isinstance(exc, URLError):
        reason = getattr(exc, "reason", None)
        reason_name = type(reason).__name__ if reason is not None else type(exc).__name__
        return f"{operation}_network_error", f"{operation.replace('_', ' ').title()} request failed: {reason_name}"
    if isinstance(exc, OSError):
        return f"{operation}_network_error", f"{operation.replace('_', ' ').title()} request failed: {type(exc).__name__}"
    return f"{operation}_error", f"{operation.replace('_', ' ').title()} request failed: {type(exc).__name__}"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _ensure_ok(payload: dict[str, Any], *, status: int = 200) -> dict[str, Any]:
    _assert(payload.get("_http_status") == status, f"expected HTTP {status}, got {payload.get('_http_status')}: {payload}")
    _assert(payload.get("ok") is True, f"expected ok=true, got {payload}")
    return payload


def _load_work_identity_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "keys": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "keys": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "keys": {}}
    keys = payload.get("keys")
    if not isinstance(keys, dict):
        payload["keys"] = {}
    payload.setdefault("version", 1)
    return payload


def _save_work_identity_registry(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n")


def _work_registry_scope(work_key: str, target_locale: str) -> str:
    return f"{target_locale}:{work_key.strip()}"


def _get_work(base_url: str, work_id: int, *, timeout: float = 60) -> dict[str, Any] | None:
    payload = _request_json("GET", base_url, f"/api/works/{work_id}", timeout=timeout)
    if payload.get("_http_status") == 404:
        return None
    return _ensure_ok(payload).get("item") or {}


def _create_work(
    base_url: str,
    *,
    work_title: str,
    pen_name: str,
    genre: str,
    user_id: int,
    target_locale: str,
    timeout: float = 60,
) -> int:
    body: dict[str, Any] = {
        "title": work_title,
        "penName": pen_name,
        "genre": genre,
        "synopsis": f"Batch evaluation for {work_title}",
        "userId": user_id,
    }
    work_resp = _ensure_ok(_request_json("POST", base_url, "/api/works", json_body=body, timeout=timeout), status=201)
    work = work_resp.get("item") or {}
    return int(work.get("work_id"))


def _resolve_work_identity(
    *,
    base_url: str,
    existing_summary: dict[str, Any] | None,
    batch_key: dict[str, Any],
    work_id: int | None,
    work_key: str | None,
    work_identity_registry: Path,
    work_title: str,
    pen_name: str,
    genre: str,
    user_id: int,
    target_locale: str,
    timeout: float,
) -> tuple[int, str, dict[str, Any]]:
    metadata: dict[str, Any] = {
        "workKey": work_key,
        "registryPath": str(work_identity_registry),
    }
    if work_id is not None:
        existing = _get_work(base_url, int(work_id), timeout=timeout)
        _assert(existing is not None, f"work_id {work_id} not found")
        metadata["source"] = "cli_work_id"
        return int(work_id), "cli_work_id", metadata

    if work_key:
        registry = _load_work_identity_registry(work_identity_registry)
        scope = _work_registry_scope(work_key, target_locale)
        entry = registry["keys"].get(scope)
        if isinstance(entry, dict) and entry.get("work_id") is not None:
            candidate_id = int(entry["work_id"])
            if _get_work(base_url, candidate_id, timeout=timeout) is not None:
                metadata["source"] = "work_key_registry_reuse"
                metadata["registryEntry"] = entry
                return candidate_id, "work_key_registry_reuse", metadata
        created_id = _create_work(
            base_url,
            work_title=work_title,
            pen_name=pen_name,
            genre=genre,
            user_id=user_id,
            target_locale=target_locale,
            timeout=timeout,
        )
        registry["keys"][scope] = {
            "work_id": created_id,
            "work_key": work_key,
            "target_locale": target_locale,
            "work_title": work_title,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _save_work_identity_registry(work_identity_registry, registry)
        metadata["source"] = "work_key_registry_created"
        metadata["registryEntry"] = registry["keys"][scope]
        return created_id, "work_key_registry_created", metadata

    if _batch_matches(existing_summary, batch_key):
        reused_id = int(existing_summary["work_id"])
        metadata["source"] = "previous_batch_summary"
        return reused_id, "previous_batch_summary", metadata

    created_id = _create_work(
        base_url,
        work_title=work_title,
        pen_name=pen_name,
        genre=genre,
        user_id=user_id,
        target_locale=target_locale,
        timeout=timeout,
    )
    metadata["source"] = "created_per_run_fallback"
    return created_id, "created_per_run_fallback", metadata


def _seed_approved_glossary(base_url: str, work_id: int, target_locale: str, *, timeout: float = 60) -> dict[str, Any]:
    seeded: list[dict[str, Any]] = []
    for row in SEED_APPROVED_GLOSSARY:
        payload = {
            "targetLocale": target_locale,
            "source": row["source"],
            "target": row["target"],
            "category": row["category"],
            "priority": "hard",
            "status": "approved",
            "note": "batch-eval approved glossary seed",
            "createdBy": "batch_eval_seed",
        }
        response = _ensure_ok(
            _request_json("POST", base_url, f"/api/works/{work_id}/glossary/entries", json_body=payload, timeout=timeout),
            status=200,
        )
        entry = response.get("entry") or response.get("item") or {}
        seeded.append({"source": row["source"], "target": row["target"], "entryId": entry.get("id") or entry.get("entry_id")})
    return {"enabled": True, "seededCount": len(seeded), "entries": seeded}


@contextmanager
def _started_server(mock_mode: bool = True) -> Iterator[str]:
    port = _pick_free_port()
    env = os.environ.copy()
    env["WLIGHTER_API_HOST"] = "127.0.0.1"
    env["WLIGHTER_API_PORT"] = str(port)
    if mock_mode:
        env["WLIGHTER_MOCK_MODE"] = "true"
    proc = subprocess.Popen(
        [sys.executable, str(API_SERVER)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 20
        last_error = ""
        while time.time() < deadline:
            if proc.poll() is not None:
                output = proc.stdout.read() if proc.stdout else ""
                raise RuntimeError(f"api_server.py exited early with code {proc.returncode}: {output}")
            try:
                response = _http_request("GET", f"{base_url}/api/health")
                if response.status == 200:
                    yield base_url
                    return
            except (OSError, URLError) as exc:
                last_error = str(exc)
            time.sleep(0.2)
        raise TimeoutError(f"api_server.py did not start within 20s: {last_error}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        if proc.stdout is not None:
            proc.stdout.close()


def _is_mock_mode() -> bool:
    return os.getenv("WLIGHTER_MOCK_MODE", "").strip().lower() == "true"


def _looks_like_chapter_heading(line: str) -> bool:
    value = line.strip()
    if not value:
        return False
    return bool(
        re.match(
            r"^(?:\d+\s*화|화\s*\d+|episode\b|ep\b|chapter\b|ch\.?\b|part\b|시즌\b|프롤로그\b|에필로그\b)",
            value,
            re.IGNORECASE,
        )
        or re.match(r"^\[?\d{1,3}\]?[\.\-:)]\s*\S+", value)
    )


def _parse_episode_source(path: Path, episode_no: int) -> EpisodeSource:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    nonempty_indexes = [index for index, line in enumerate(lines) if line.strip()]
    if not nonempty_indexes:
        title = f"Episode {episode_no:03d}"
        original_text = ""
        return EpisodeSource(episode_no=episode_no, path=path, title=title, original_text=original_text)

    first_idx = nonempty_indexes[0]
    title_line = lines[first_idx].strip()
    body_start = first_idx + 1
    if len(nonempty_indexes) >= 2:
        second_idx = nonempty_indexes[1]
        second_line = lines[second_idx].strip()
        if _looks_like_chapter_heading(second_line):
            title_line = second_line
            body_start = second_idx + 1

    original_text = "\n".join(lines[body_start:]).strip()
    if not original_text and body_start < len(lines):
        original_text = "\n".join(lines[body_start:]).strip()
    title = title_line or f"Episode {episode_no:03d}"
    return EpisodeSource(episode_no=episode_no, path=path, title=title, original_text=original_text)


def _parse_episode_nos(value: str | None) -> list[int] | None:
    if not value:
        return None
    episode_nos: list[int] = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            episode_no = int(item)
        except ValueError as exc:
            raise ValueError(f"invalid episode number: {item}") from exc
        if episode_no <= 0:
            raise ValueError(f"episode number must be positive: {item}")
        if episode_no not in episode_nos:
            episode_nos.append(episode_no)
    return episode_nos or None


def _collect_episode_sources(input_dir: Path, limit: int, episode_nos: list[int] | None = None) -> list[EpisodeSource]:
    files = sorted(
        input_dir.glob("*.txt"),
        key=lambda path: (
            int(path.stem) if path.stem.isdigit() else 10**9,
            path.stem,
        ),
    )
    if episode_nos:
        requested = set(episode_nos)
        files = [path for path in files if path.stem.isdigit() and int(path.stem) in requested]
    selected = files[: max(limit, 0)]
    episodes: list[EpisodeSource] = []
    for index, path in enumerate(selected, start=1):
        episode_no = int(path.stem) if path.stem.isdigit() else index
        episodes.append(_parse_episode_source(path, episode_no))
    return episodes


def _batch_key(
    *,
    input_dir: Path,
    work_title: str,
    target_country: str,
    genre: str,
    pen_name: str,
    limit: int,
    episode_nos: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "inputDir": str(input_dir.resolve()),
        "workTitle": work_title,
        "targetCountry": target_country,
        "genre": genre,
        "penName": pen_name,
        "limit": limit,
        "episodeNos": episode_nos or [],
    }


def _summary_path(report_dir: Path) -> Path:
    return report_dir / "latest_summary.json"


def _load_existing_summary(report_dir: Path) -> dict[str, Any] | None:
    path = _summary_path(report_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _batch_matches(existing: dict[str, Any] | None, batch_key: dict[str, Any]) -> bool:
    if not existing:
        return False
    return existing.get("batchKey") == batch_key and isinstance(existing.get("work_id"), int)


def _existing_episode_status(existing_summary: dict[str, Any] | None, episode_no: int) -> dict[str, Any] | None:
    if not existing_summary:
        return None
    for row in existing_summary.get("per_episode") or []:
        if isinstance(row, dict) and row.get("episode_no") == episode_no:
            return row
    return None


def _ensure_report_dirs(report_dir: Path) -> dict[str, Path]:
    raw_dir = report_dir / "raw"
    translations_dir = report_dir / "translations"
    raw_dir.mkdir(parents=True, exist_ok=True)
    translations_dir.mkdir(parents=True, exist_ok=True)
    return {"report": report_dir, "raw": raw_dir, "translations": translations_dir}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_error_summary(exc: Exception) -> str:
    message = str(exc).strip()
    return f"{type(exc).__name__}{(': ' + message) if message else ''}"


def _source_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _episode_payload(source: EpisodeSource) -> dict[str, Any]:
    return {
        "title": source.title,
        "episodeNo": source.episode_no,
        "originalText": source.original_text,
    }


def _list_work_episodes(base_url: str, work_id: int, *, timeout: float = 60) -> list[dict[str, Any]]:
    payload = _ensure_ok(
        _request_json(
            "GET",
            base_url,
            f"/api/works/{work_id}/episodes?{urlencode({'limit': 1000})}",
            timeout=timeout,
        )
    )
    items = payload.get("items") or []
    return [row for row in items if isinstance(row, dict)]


def _find_existing_episode(
    base_url: str,
    work_id: int,
    episode_no: int,
    *,
    timeout: float = 60,
) -> dict[str, Any] | None:
    for episode in _list_work_episodes(base_url, work_id, timeout=timeout):
        if episode.get("episode_no") == episode_no or episode.get("episodeNo") == episode_no:
            return episode
    return None


def _latest_translation_exists(
    base_url: str,
    work_id: int,
    episode_id: int,
    target_locale: str,
    *,
    timeout: float = 60,
) -> dict[str, Any] | None:
    payload = _request_json(
        "GET",
        base_url,
        f"/api/works/{work_id}/episodes/{episode_id}/translations/latest?{urlencode({'targetLocale': target_locale})}",
        timeout=timeout,
    )
    if payload.get("_http_status") == 200 and payload.get("ok") is True and isinstance(payload.get("item"), dict):
        return payload["item"]
    if payload.get("_http_status") == 404 or payload.get("errorCode") == "translation_not_found":
        return None
    _ensure_ok(payload)
    return None


def _episode_source_warnings(source: EpisodeSource, episode: dict[str, Any] | None) -> list[str]:
    if not episode:
        return []
    warnings: list[str] = []
    expected_hash = _source_text_hash(source.original_text)
    stored_hash = str(episode.get("source_text_hash") or episode.get("sourceTextHash") or "").strip()
    stored_text = str(episode.get("original_text") or episode.get("originalText") or "")
    if stored_hash and stored_hash != expected_hash:
        warnings.append("source_text_hash_mismatch")
    elif not stored_hash and stored_text and stored_text != source.original_text:
        warnings.append("original_text_mismatch")
    if str(episode.get("title") or "") != source.title:
        warnings.append("title_mismatch")
    stored_char_count = episode.get("char_count") if "char_count" in episode else episode.get("charCount")
    if stored_char_count is not None:
        try:
            if int(stored_char_count) != source.char_count:
                warnings.append("char_count_mismatch")
        except (TypeError, ValueError):
            warnings.append("char_count_mismatch")
    return warnings


def _update_existing_episode(
    base_url: str,
    work_id: int,
    episode_id: int,
    source: EpisodeSource,
    *,
    timeout: float = 60,
) -> dict[str, Any]:
    return _ensure_ok(
        _request_json(
            "POST",
            base_url,
            f"/api/works/{work_id}/episodes",
            json_body={**_episode_payload(source), "episodeId": episode_id},
            timeout=timeout,
        ),
        status=201,
    ).get("item") or {}


def _ensure_episode(
    *,
    base_url: str,
    work_id: int,
    source: EpisodeSource,
    update_existing_episodes: bool,
    timeout: float,
) -> tuple[int, str, list[str], dict[str, Any] | None]:
    existing = _find_existing_episode(base_url, work_id, source.episode_no, timeout=timeout)
    if existing:
        episode_id = int(existing.get("episode_id") or existing.get("episodeId"))
        warnings = _episode_source_warnings(source, existing)
        episode = existing
        if update_existing_episodes and warnings:
            episode = _update_existing_episode(base_url, work_id, episode_id, source, timeout=timeout)
            warnings.append("existing_episode_updated")
        return episode_id, "reused", warnings, episode

    payload = _episode_payload(source)
    try:
        episode_resp = _ensure_ok(
            _request_json(
                "POST",
                base_url,
                f"/api/works/{work_id}/episodes",
                json_body=payload,
                timeout=timeout,
            ),
            status=201,
        )
        episode = episode_resp.get("item") or {}
        return int(episode.get("episode_id") or episode.get("episodeId")), "created", [], episode
    except (TimeoutError, socket.timeout, URLError, HTTPError, OSError, ValueError, AssertionError):
        # A duplicate unique-key failure can surface as an API AssertionError because
        # some backends return repository_error for duplicate episode_no. Re-check
        # the server state before treating it as a real create failure.
        duplicate = _find_existing_episode(base_url, work_id, source.episode_no, timeout=timeout)
        if duplicate:
            episode_id = int(duplicate.get("episode_id") or duplicate.get("episodeId"))
            warnings = _episode_source_warnings(source, duplicate)
            warnings.append("episode_create_duplicate_recovered")
            episode = duplicate
            if update_existing_episodes and warnings:
                episode = _update_existing_episode(base_url, work_id, episode_id, source, timeout=timeout)
                warnings.append("existing_episode_updated")
            return episode_id, "reused_after_create_error", warnings, episode
        raise


def _write_episode_raw(
    raw_dir: Path,
    episode_no: int,
    *,
    source: EpisodeSource,
    payload: dict[str, Any] | None,
    response: dict[str, Any] | None,
    status: str,
    error_code: str | None = None,
    error: str | None = None,
    elapsed_seconds: float | None = None,
) -> Path:
    raw_path = raw_dir / f"{episode_no:03d}.json"
    data = {
        "episode_no": episode_no,
        "source_path": str(source.path),
        "title": source.title,
        "char_count": source.char_count,
        "status": status,
        "request": payload,
        "response": response,
        "errorCode": error_code,
        "error": error,
        "elapsed_seconds": round(elapsed_seconds or 0.0, 3),
    }
    _write_text(raw_path, json.dumps(data, ensure_ascii=False, indent=2, default=_json_default) + "\n")
    return raw_path


def _render_markdown(report: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")

    lines = [
        "# Web Novel Batch Evaluation Summary",
        "",
        f"- Work ID: {report.get('work_id')}",
        f"- Work title: {report.get('work_title')}",
        f"- Target country: {report.get('target_country')}",
        f"- Target locale: {report.get('target_locale')}",
        f"- Input dir: {report.get('input_dir')}",
        f"- Dry-run: {report.get('dry_run')}",
        f"- Mock mode: {report.get('mock_mode')}",
        f"- Request timeout seconds: {report.get('request_timeout_seconds')}",
        f"- Save results: {report.get('save_results')}",
        f"- Capture glossary candidates: {report.get('capture_glossary_candidates')}",
        f"- Total episodes: {report.get('total_episodes')}",
        f"- Succeeded: {report.get('succeeded')}",
        f"- Failed: {report.get('failed')}",
        f"- Blocked: {report.get('blocked')}",
        f"- Episode reused: {report.get('episode_reused')}",
        f"- Episode updated: {report.get('episode_updated')}",
        f"- Source mismatch warnings: {report.get('source_mismatch_warnings')}",
        f"- QA warnings: {report.get('qa_warning_count')}",
        f"- Deliverable: {report.get('deliverable_count')}",
        f"- Total pending glossary candidates: {report.get('total_pending_glossary_candidates')}",
        "",
        "## Per episode",
        "",
        "| Episode | Title | Status | Episode | Warnings | Delivery | Saved ID | QA Issues | Glossary Saved | Seconds | Error |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("per_episode") or []:
        capture = row.get("glossary_candidate_capture") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    esc(row.get("episode_no")),
                    esc(row.get("title")),
                    esc(row.get("status")),
                    esc(row.get("episode_reuse_status")),
                    esc(",".join(row.get("episode_warnings") or [])),
                    esc(row.get("delivery_status")),
                    esc(row.get("saved_translation_id")),
                    esc(row.get("qa_issue_count")),
                    esc(capture.get("savedCount")),
                    esc(row.get("elapsed_seconds")),
                    esc(row.get("errorCode") or row.get("error")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Output files",
            "",
            f"- JSON summary: `{report.get('summary_json_path')}`",
            f"- Markdown summary: `{report.get('summary_md_path')}`",
            "",
        ]
    )
    return "\n".join(lines)


def _count_pending_candidates(base_url: str, work_id: int, target_locale: str, *, timeout: float = 60) -> int:
    payload = _ensure_ok(
        _request_json(
            "GET",
            base_url,
            f"/api/works/{work_id}/glossary/candidates?{urlencode({'targetLocale': target_locale, 'status': 'pending'})}",
            timeout=timeout,
        )
    )
    return int(payload.get("count") or len(payload.get("items") or []))


def _build_translation_payload(
    *,
    source_text: str,
    target_country: str,
    work_id: int,
    episode_id: int,
    save_results: bool,
    capture_glossary_candidates: bool,
    genre: str,
    pen_name: str,
    title: str,
    debug_capture_model_outputs: bool = False,
    debug_artifact_dir: Path | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "v3_literary_package",
        "sourceText": source_text,
        "targetCountry": target_country,
        "workId": work_id,
        "episodeId": episode_id,
        "genre": genre,
        "penName": pen_name,
        "title": title,
    }
    if save_results:
        payload["saveTranslationResult"] = True
    if capture_glossary_candidates:
        payload["captureGlossaryCandidates"] = True
    if debug_capture_model_outputs and debug_artifact_dir is not None:
        payload["debugCaptureModelOutputs"] = True
        payload["debugArtifactDir"] = str(debug_artifact_dir)
    return payload


def _summarize_episode_result(
    *,
    source: EpisodeSource,
    response: dict[str, Any] | None,
    error_code: str | None = None,
    error: str | None = None,
    status: str,
    elapsed_seconds: float,
    raw_path: Path | None = None,
    translation_path: Path | None = None,
    episode_id: int | None = None,
    episode_reuse_status: str | None = None,
    episode_warnings: list[str] | None = None,
) -> dict[str, Any]:
    workflow = response.get("workflow") if isinstance(response, dict) and isinstance(response.get("workflow"), dict) else {}
    internal = response.get("internal") if isinstance(response, dict) and isinstance(response.get("internal"), dict) else {}
    translation_rationale = response.get("translationRationale") if isinstance(response, dict) and isinstance(response.get("translationRationale"), dict) else {}
    capture = internal.get("glossaryCandidateCapture") if isinstance(internal.get("glossaryCandidateCapture"), dict) else {}
    metadata = response.get("metadata") if isinstance(response, dict) and isinstance(response.get("metadata"), dict) else {}
    delivery_status = str(response.get("deliveryStatus") or workflow.get("deliveryStatus") or "").strip() if response else ""
    saved_translation_id = metadata.get("savedTranslationId") if metadata else None
    if saved_translation_id is None and isinstance(response, dict):
        saved_translation_id = response.get("savedTranslationId")
    qa_issues = response.get("qaIssues") if isinstance(response, dict) else None
    if not isinstance(qa_issues, list):
        qa_issues = workflow.get("qaIssues") if isinstance(workflow.get("qaIssues"), list) else []
    return {
        "episode_no": source.episode_no,
        "episode_id": episode_id,
        "episode_reuse_status": episode_reuse_status,
        "episode_warnings": episode_warnings or [],
        "title": source.title,
        "char_count": source.char_count,
        "status": status,
        "delivery_status": delivery_status,
        "saved_translation_id": saved_translation_id,
        "final_translation_length": len(str(response.get("finalTranslation") or "")) if response else 0,
        "qa_issue_count": len(qa_issues),
        "rationale_item_count": len(translation_rationale.get("items") or []) if translation_rationale else 0,
        "glossary_candidate_capture": capture,
        "errorCode": error_code,
        "error": error,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "raw_path": str(raw_path) if raw_path else None,
        "translation_path": str(translation_path) if translation_path else None,
    }


def run_batch_eval(
    *,
    input_dir: Path,
    target_country: str = "JP",
    work_title: str = "Batch Eval Novel",
    genre: str = "fantasy",
    pen_name: str = "tester",
    save_results: bool = False,
    capture_glossary_candidates: bool = False,
    skip_existing: bool = False,
    update_existing_episodes: bool = False,
    limit: int | None = None,
    dry_run: bool = False,
    confirm_real_run: bool = False,
    report_dir: Path = DEFAULT_REPORT_DIR,
    verbose: bool = False,
    base_url: str | None = None,
    user_id: int = 1,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    episode_nos: list[int] | None = None,
    debug_capture_model_outputs: bool = False,
    work_id: int | None = None,
    work_key: str | None = None,
    work_identity_registry: Path = DEFAULT_WORK_IDENTITY_REGISTRY,
    seed_approved_glossary: bool = False,
) -> dict[str, Any]:
    input_dir = input_dir.resolve()
    report_dir = report_dir.resolve()
    work_identity_registry = work_identity_registry.resolve()
    paths = _ensure_report_dirs(report_dir)
    target_locale = country_to_locale(target_country)
    effective_limit = len(episode_nos) if limit is None and episode_nos else (20 if limit is None else limit)
    batch_key = _batch_key(
        input_dir=input_dir,
        work_title=work_title,
        target_country=target_country,
        genre=genre,
        pen_name=pen_name,
        limit=effective_limit,
        episode_nos=episode_nos,
    )
    existing_summary = _load_existing_summary(report_dir)
    planned_sources = _collect_episode_sources(input_dir, effective_limit, episode_nos=episode_nos)

    if not input_dir.exists():
        raise FileNotFoundError(f"input dir not found: {input_dir}")

    if dry_run:
        per_episode = []
        for source in planned_sources:
            status = "validation_error" if source.char_count > MAX_ORIGINAL_TEXT_CHARS or not source.original_text.strip() else "planned"
            error_code = "text_too_long" if source.char_count > MAX_ORIGINAL_TEXT_CHARS else ("validation_error" if status != "planned" else None)
            error = (
                "originalText exceeds 8000 characters"
                if error_code == "text_too_long"
                else ("originalText is required" if error_code == "validation_error" else None)
            )
            per_episode.append(
                {
                    "episode_no": source.episode_no,
                    "episode_id": None,
                    "episode_reuse_status": None,
                    "episode_warnings": [],
                    "title": source.title,
                    "char_count": source.char_count,
                    "status": status,
                    "delivery_status": "",
                    "saved_translation_id": None,
                    "final_translation_length": 0,
                    "qa_issue_count": 0,
                    "rationale_item_count": 0,
                    "glossary_candidate_capture": {"enabled": False, "reason": "dry_run"},
                    "errorCode": error_code,
                    "error": error,
                    "elapsed_seconds": 0.0,
                    "raw_path": None,
                    "translation_path": None,
                }
            )
        report = {
            "batchKey": batch_key,
            "work_id": work_id if work_id is not None else (existing_summary.get("work_id") if _batch_matches(existing_summary, batch_key) else None),
            "work_key": work_key,
            "workIdentitySource": "cli_work_id" if work_id is not None else ("work_key_dry_run" if work_key else ("previous_batch_summary" if _batch_matches(existing_summary, batch_key) else None)),
            "workIdentityRegistryPath": str(work_identity_registry),
            "work_title": work_title,
            "target_country": target_country,
            "target_locale": target_locale,
            "input_dir": str(input_dir),
            "total_episodes": len(planned_sources),
            "succeeded": 0,
            "failed": sum(1 for row in per_episode if row["status"] == "validation_error"),
            "blocked": 0,
            "skipped_existing": 0,
            "episode_reused": 0,
            "episode_updated": 0,
            "source_mismatch_warnings": 0,
            "update_existing_episodes": update_existing_episodes,
            "qa_warning_count": 0,
            "deliverable_count": 0,
            "total_pending_glossary_candidates": 0,
            "save_results": save_results,
            "capture_glossary_candidates": capture_glossary_candidates,
            "dry_run": True,
            "mock_mode": _is_mock_mode(),
            "request_timeout_seconds": request_timeout,
            "episode_nos": episode_nos or [],
            "effective_limit": effective_limit,
            "seedApprovedGlossary": {"enabled": bool(seed_approved_glossary), "reason": "dry_run"},
            "per_episode": per_episode,
        }
        report["summary_json_path"] = str(_summary_path(report_dir))
        report["summary_md_path"] = str(report_dir / "latest_summary.md")
        _write_text(_summary_path(report_dir), json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n")
        _write_text(report_dir / "latest_summary.md", _render_markdown(report))
        return report

    if not _is_mock_mode() and not confirm_real_run:
        raise SystemExit("Real model batch may cost money. Re-run with --confirm-real-run to continue.")

    started_server = False
    server_context = None
    if not base_url:
        server_context = _started_server(mock_mode=_is_mock_mode())
        base_url = server_context.__enter__()
        started_server = True

    try:
        content_status = _ensure_ok(_request_json("GET", base_url, "/api/content/repository-status", timeout=request_timeout))
        glossary_status = _ensure_ok(_request_json("GET", base_url, "/api/glossary/repository-status", timeout=request_timeout))
        if verbose:
            print(f"content repository backend={content_status.get('backend')} fallback={content_status.get('fallback')}")
            print(f"glossary repository backend={glossary_status.get('backend')} fallback={glossary_status.get('fallback')}")

        resolved_work_id, work_identity_source, work_identity_metadata = _resolve_work_identity(
            base_url=base_url,
            existing_summary=existing_summary,
            batch_key=batch_key,
            work_id=work_id,
            work_key=work_key,
            work_identity_registry=work_identity_registry,
            work_title=work_title,
            pen_name=pen_name,
            genre=genre,
            user_id=user_id,
            target_locale=target_locale,
            timeout=request_timeout,
        )
        work_id = resolved_work_id
        if verbose:
            print(f"using work_id={work_id} source={work_identity_source}")

        seed_summary = {"enabled": False}
        if seed_approved_glossary:
            seed_summary = _seed_approved_glossary(base_url, work_id, target_locale, timeout=request_timeout)
            if verbose:
                print(f"seeded approved glossary entries={seed_summary.get('seededCount')}")

        per_episode: list[dict[str, Any]] = []
        succeeded = 0
        failed = 0
        blocked = 0
        deliverable_count = 0
        qa_warning_count = 0
        skipped_existing_count = 0
        episode_reused_count = 0
        episode_updated_count = 0
        source_mismatch_warning_count = 0

        for index, source in enumerate(planned_sources, start=1):
            started = time.perf_counter()
            existing_row = _existing_episode_status(existing_summary if _batch_matches(existing_summary, batch_key) else None, source.episode_no)
            raw_path = paths["raw"] / f"{source.episode_no:03d}.json"
            translation_path = paths["translations"] / f"{source.episode_no:03d}.txt"

            if not source.original_text.strip():
                error = "originalText is required"
                per_episode.append(
                    {
                        "episode_no": source.episode_no,
                        "episode_id": None,
                        "episode_reuse_status": None,
                        "episode_warnings": [],
                        "title": source.title,
                        "char_count": source.char_count,
                        "status": "validation_error",
                        "delivery_status": "",
                        "saved_translation_id": None,
                        "final_translation_length": 0,
                        "qa_issue_count": 0,
                        "rationale_item_count": 0,
                        "glossary_candidate_capture": {"enabled": False, "reason": "validation_error"},
                        "errorCode": "validation_error",
                        "error": error,
                        "elapsed_seconds": round(time.perf_counter() - started, 3),
                        "raw_path": str(_write_episode_raw(paths["raw"], source.episode_no, source=source, payload=None, response=None, status="validation_error", error_code="validation_error", error=error, elapsed_seconds=time.perf_counter() - started)),
                        "translation_path": None,
                    }
                )
                failed += 1
                continue

            if source.char_count > MAX_ORIGINAL_TEXT_CHARS:
                error = "originalText exceeds 8000 characters"
                per_episode.append(
                    {
                        "episode_no": source.episode_no,
                        "episode_id": None,
                        "episode_reuse_status": None,
                        "episode_warnings": [],
                        "title": source.title,
                        "char_count": source.char_count,
                        "status": "validation_error",
                        "delivery_status": "",
                        "saved_translation_id": None,
                        "final_translation_length": 0,
                        "qa_issue_count": 0,
                        "rationale_item_count": 0,
                        "glossary_candidate_capture": {"enabled": False, "reason": "text_too_long"},
                        "errorCode": "text_too_long",
                        "error": error,
                        "elapsed_seconds": round(time.perf_counter() - started, 3),
                        "raw_path": str(_write_episode_raw(paths["raw"], source.episode_no, source=source, payload=None, response=None, status="validation_error", error_code="text_too_long", error=error, elapsed_seconds=time.perf_counter() - started)),
                        "translation_path": None,
                    }
                )
                failed += 1
                continue

            if skip_existing and raw_path.exists() and translation_path.exists():
                skipped_existing_count += 1
                per_episode.append(
                    {
                        "episode_no": source.episode_no,
                        "episode_id": existing_row.get("episode_id") if existing_row else None,
                        "episode_reuse_status": "skipped_before_episode_lookup",
                        "episode_warnings": [],
                        "title": source.title,
                        "char_count": source.char_count,
                        "status": "skipped_existing",
                        "delivery_status": existing_row.get("delivery_status") if existing_row else "",
                        "saved_translation_id": existing_row.get("saved_translation_id") if existing_row else None,
                        "final_translation_length": existing_row.get("final_translation_length") if existing_row else 0,
                        "qa_issue_count": existing_row.get("qa_issue_count") if existing_row else 0,
                        "rationale_item_count": existing_row.get("rationale_item_count") if existing_row else 0,
                        "glossary_candidate_capture": existing_row.get("glossary_candidate_capture") if existing_row else {"enabled": False, "reason": "skipped_existing"},
                        "errorCode": None,
                        "error": None,
                        "elapsed_seconds": 0.0,
                        "raw_path": str(raw_path),
                        "translation_path": str(translation_path),
                    }
                )
                continue

            episode_id: int | None = None
            episode_reuse_status: str | None = None
            episode_warnings: list[str] = []
            try:
                episode_id, episode_reuse_status, episode_warnings, _episode = _ensure_episode(
                    base_url=base_url,
                    work_id=work_id,
                    source=source,
                    update_existing_episodes=update_existing_episodes,
                    timeout=request_timeout,
                )
            except (TimeoutError, socket.timeout, URLError, HTTPError, OSError, ValueError, AssertionError) as exc:
                error_code, error = _request_error_details(exc, operation="episode_create", timeout=request_timeout)
                elapsed = time.perf_counter() - started
                raw_path = _write_episode_raw(
                    paths["raw"],
                    source.episode_no,
                    source=source,
                    payload=None,
                    response=None,
                    status="failed",
                    error_code=error_code,
                    error=error,
                    elapsed_seconds=elapsed,
                )
                per_episode.append(
                    _summarize_episode_result(
                        source=source,
                        response=None,
                        error_code=error_code,
                        error=error,
                        status="failed",
                        elapsed_seconds=elapsed,
                        raw_path=raw_path,
                        translation_path=None,
                        episode_id=None,
                        episode_reuse_status=None,
                        episode_warnings=[],
                    )
                )
                failed += 1
                if verbose:
                    print(f"episode {source.episode_no:03d} failed: {error_code} - {error}")
                continue
            if episode_reuse_status and episode_reuse_status != "created":
                episode_reused_count += 1
            if "existing_episode_updated" in episode_warnings:
                episode_updated_count += 1
            if any(warning.endswith("_mismatch") for warning in episode_warnings):
                source_mismatch_warning_count += 1

            if skip_existing and episode_id is not None:
                latest_translation = None
                try:
                    latest_translation = _latest_translation_exists(
                        base_url,
                        work_id,
                        episode_id,
                        target_locale,
                        timeout=request_timeout,
                    )
                except (TimeoutError, socket.timeout, URLError, HTTPError, OSError, ValueError, AssertionError) as exc:
                    if verbose:
                        error_code, error = _request_error_details(exc, operation="translation_lookup", timeout=request_timeout)
                        print(f"translation lookup failed for episode {source.episode_no:03d}: {error_code} - {error}")
                if latest_translation or (raw_path.exists() and translation_path.exists()):
                    skipped_existing_count += 1
                    saved_translation_id = (
                        latest_translation.get("translation_id")
                        if latest_translation
                        else (existing_row.get("saved_translation_id") if existing_row else None)
                    )
                    per_episode.append(
                        {
                            "episode_no": source.episode_no,
                            "episode_id": episode_id,
                            "episode_reuse_status": episode_reuse_status,
                            "episode_warnings": episode_warnings,
                            "title": source.title,
                            "char_count": source.char_count,
                            "status": "skipped_existing",
                            "delivery_status": (latest_translation or {}).get("delivery_status") or (existing_row.get("delivery_status") if existing_row else ""),
                            "saved_translation_id": saved_translation_id,
                            "final_translation_length": len(str((latest_translation or {}).get("translated_text") or "")) if latest_translation else (existing_row.get("final_translation_length") if existing_row else 0),
                            "qa_issue_count": len((latest_translation or {}).get("qa_issues") or []) if latest_translation else (existing_row.get("qa_issue_count") if existing_row else 0),
                            "rationale_item_count": existing_row.get("rationale_item_count") if existing_row else 0,
                            "glossary_candidate_capture": existing_row.get("glossary_candidate_capture") if existing_row else {"enabled": False, "reason": "skipped_existing"},
                            "errorCode": None,
                            "error": None,
                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                            "raw_path": str(raw_path),
                            "translation_path": str(translation_path),
                        }
                    )
                    continue
            translation_payload = _build_translation_payload(
                source_text=source.original_text,
                target_country=target_country,
                work_id=work_id,
                episode_id=episode_id,
                save_results=save_results,
                capture_glossary_candidates=capture_glossary_candidates,
                genre=genre,
                pen_name=pen_name,
                title=source.title,
                debug_capture_model_outputs=debug_capture_model_outputs,
                debug_artifact_dir=paths["report"] / "debug" / f"episode_{source.episode_no:03d}",
            )
            try:
                translation_resp = _request_json(
                    "POST",
                    base_url,
                    "/api/translate",
                    json_body=translation_payload,
                    timeout=request_timeout,
                )
            except (TimeoutError, socket.timeout, URLError, HTTPError, OSError, ValueError) as exc:
                error_code, error = _request_error_details(exc, operation="translation", timeout=request_timeout)
                elapsed = time.perf_counter() - started
                raw_path = _write_episode_raw(
                    paths["raw"],
                    source.episode_no,
                    source=source,
                    payload=translation_payload,
                    response=None,
                    status="failed",
                    error_code=error_code,
                    error=error,
                    elapsed_seconds=elapsed,
                )
                per_episode.append(
                    _summarize_episode_result(
                        source=source,
                        response=None,
                        error_code=error_code,
                        error=error,
                        status="failed",
                        elapsed_seconds=elapsed,
                        raw_path=raw_path,
                        translation_path=None,
                        episode_id=episode_id,
                        episode_reuse_status=episode_reuse_status,
                        episode_warnings=episode_warnings,
                    )
                )
                failed += 1
                if verbose:
                    print(f"episode {source.episode_no:03d} failed: {error_code} - {error}")
                continue
            status = "translation_error"
            error_code = None
            error = None
            translation_path_written: Path | None = None
            response_ok = translation_resp.get("_http_status") == 200 and translation_resp.get("ok") is not False
            counted_success = False
            counted_delivery_status = ""
            if response_ok:
                delivery_status = str(translation_resp.get("deliveryStatus") or "").strip()
                if delivery_status == "deliverable":
                    status = "deliverable"
                    deliverable_count += 1
                    succeeded += 1
                    counted_success = True
                    counted_delivery_status = delivery_status
                elif delivery_status == "qa_warning":
                    status = "qa_warning"
                    qa_warning_count += 1
                    succeeded += 1
                    counted_success = True
                    counted_delivery_status = delivery_status
                elif delivery_status.startswith("blocked_translation_"):
                    status = "integrity_blocked" if delivery_status == "blocked_translation_integrity" else "blocked"
                    blocked += 1
                    counted_delivery_status = delivery_status
                else:
                    status = "success"
                    succeeded += 1
                    counted_success = True
                    counted_delivery_status = delivery_status
                if save_results:
                    metadata = translation_resp.get("metadata") or {}
                    persistence_required = delivery_status in {"deliverable", "qa_warning"}
                    if persistence_required and (metadata.get("translationPersisted") is not True or not metadata.get("savedTranslationId")):
                        error_code = "translation_persistence_missing"
                        error = "translation persisted metadata missing"
                        status = "translation_error"
                        if counted_success and succeeded > 0:
                            succeeded -= 1
                            if counted_delivery_status == "deliverable":
                                deliverable_count -= 1
                            elif counted_delivery_status == "qa_warning":
                                qa_warning_count -= 1
                    elif translation_resp.get("finalTranslation") is not None and not delivery_status.startswith("blocked_translation_"):
                        translation_path_written = translation_path
                        _write_text(translation_path_written, str(translation_resp.get("finalTranslation") or "") + "\n")
                elif translation_resp.get("finalTranslation") is not None:
                    translation_path_written = translation_path
                    _write_text(translation_path_written, str(translation_resp.get("finalTranslation") or "") + "\n")
            else:
                status = "translation_error"
                error_code = translation_resp.get("errorCode") or translation_resp.get("error") or "translation_error"
                error = translation_resp.get("message") or translation_resp.get("error") or "translation request failed"

            if response_ok and save_results and translation_resp.get("metadata", {}).get("translationPersisted") is not True:
                # already counted as failed above
                pass

            raw_path = _write_episode_raw(
                paths["raw"],
                source.episode_no,
                source=source,
                payload=translation_payload,
                response=translation_resp,
                status=status,
                error_code=error_code,
                error=error,
                elapsed_seconds=time.perf_counter() - started,
            )
            summary_row = _summarize_episode_result(
                source=source,
                response=translation_resp if response_ok else None,
                error_code=error_code,
                error=error,
                status=status,
                elapsed_seconds=time.perf_counter() - started,
                raw_path=raw_path,
                translation_path=translation_path_written,
                episode_id=episode_id,
                episode_reuse_status=episode_reuse_status,
                episode_warnings=episode_warnings,
            )
            if status == "translation_error":
                failed += 1
            per_episode.append(summary_row)

        try:
            pending_candidates = _count_pending_candidates(base_url, work_id, target_locale, timeout=request_timeout)
        except (TimeoutError, socket.timeout, URLError, HTTPError, OSError, ValueError, AssertionError) as exc:
            pending_candidates = 0
            if verbose:
                error_code, error = _request_error_details(exc, operation="candidate_count", timeout=request_timeout)
                print(f"candidate count failed: {error_code} - {error}")
        report = {
            "batchKey": batch_key,
            "work_id": work_id,
            "work_key": work_key,
            "workIdentitySource": work_identity_source,
            "workIdentity": work_identity_metadata,
            "workIdentityRegistryPath": str(work_identity_registry),
            "work_title": work_title,
            "target_country": target_country,
            "target_locale": target_locale,
            "input_dir": str(input_dir),
            "contentRepositoryStatus": content_status,
            "glossaryRepositoryStatus": glossary_status,
            "total_episodes": len(planned_sources),
            "succeeded": succeeded,
            "failed": failed,
            "blocked": blocked,
            "skipped_existing": skipped_existing_count,
            "episode_reused": episode_reused_count,
            "episode_updated": episode_updated_count,
            "source_mismatch_warnings": source_mismatch_warning_count,
            "qa_warning_count": qa_warning_count,
            "deliverable_count": deliverable_count,
            "total_pending_glossary_candidates": pending_candidates,
            "save_results": save_results,
            "capture_glossary_candidates": capture_glossary_candidates,
            "update_existing_episodes": update_existing_episodes,
            "dry_run": False,
            "mock_mode": _is_mock_mode(),
            "request_timeout_seconds": request_timeout,
            "episode_nos": episode_nos or [],
            "effective_limit": effective_limit,
            "seedApprovedGlossary": seed_summary,
            "per_episode": per_episode,
        }
        summary_json_path = _summary_path(report_dir)
        summary_md_path = report_dir / "latest_summary.md"
        report["summary_json_path"] = str(summary_json_path)
        report["summary_md_path"] = str(summary_md_path)
        _write_text(summary_json_path, json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n")
        _write_text(summary_md_path, _render_markdown(report))
        return report
    finally:
        if started_server and server_context is not None:
            server_context.__exit__(None, None, None)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a batch evaluation over web novel chapters.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="Directory containing UTF-8 txt files.")
    parser.add_argument("--target-country", default="JP", help="Target country for translation.")
    parser.add_argument("--work-title", default="Batch Eval Novel", help="Content work title.")
    parser.add_argument("--genre", default="fantasy", help="Work genre.")
    parser.add_argument("--pen-name", default="tester", help="Work pen name.")
    parser.add_argument("--save-results", action="store_true", help="Persist translation_results.")
    parser.add_argument(
        "--capture-glossary-candidates",
        action="store_true",
        help="Capture glossary candidates while translating.",
    )
    parser.add_argument("--skip-existing", action="store_true", help="Skip episodes that already have output files.")
    parser.add_argument(
        "--update-existing-episodes",
        action="store_true",
        help="When an existing episode_no is reused and its source/title metadata differs, update the episode before translating.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of txt files to process. Defaults to all requested --episode-nos, otherwise 20.")
    parser.add_argument(
        "--episode-nos",
        default=None,
        help="Comma-separated episode numbers to process, e.g. 17 or 8,18,19. Explicit --limit still caps the selected set.",
    )
    parser.add_argument("--work-id", type=int, default=None, help="Reuse this existing stable work_id; never creates a new work.")
    parser.add_argument("--work-key", default=None, help="Batch/test stable work key mapped to an existing or newly-created work_id.")
    parser.add_argument(
        "--work-identity-registry",
        type=Path,
        default=DEFAULT_WORK_IDENTITY_REGISTRY,
        help="Batch-eval-only JSON registry that maps --work-key plus target locale to a reusable work_id.",
    )
    parser.add_argument(
        "--seed-approved-glossary",
        action="store_true",
        help="Upsert the built-in approved/locked JP glossary seed into glossary_entries before translating.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not call the API or save DB data.")
    parser.add_argument(
        "--confirm-real-run",
        action="store_true",
        help="Acknowledge that a non-mock run may cost money.",
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Directory for batch reports.")
    parser.add_argument("--base-url", default=None, help="Existing api_server base URL.")
    parser.add_argument("--user-id", type=int, default=1, help="Numeric userId used when creating the work.")
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        help="HTTP request timeout in seconds; real model runs often need a higher value such as 600.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress details.")
    parser.add_argument(
        "--debug-capture-model-outputs",
        action="store_true",
        help="Write retry/repair model debug artifacts under the selected reports directory.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_batch_eval(
        input_dir=args.input_dir,
        target_country=args.target_country,
        work_title=args.work_title,
        genre=args.genre,
        pen_name=args.pen_name,
        save_results=args.save_results,
        capture_glossary_candidates=args.capture_glossary_candidates,
        skip_existing=args.skip_existing,
        update_existing_episodes=args.update_existing_episodes,
        limit=args.limit,
        dry_run=args.dry_run,
        confirm_real_run=args.confirm_real_run,
        report_dir=args.report_dir,
        verbose=args.verbose,
        base_url=args.base_url,
        user_id=args.user_id,
        request_timeout=args.request_timeout,
        episode_nos=_parse_episode_nos(args.episode_nos),
        debug_capture_model_outputs=args.debug_capture_model_outputs,
        work_id=args.work_id,
        work_key=args.work_key,
        work_identity_registry=args.work_identity_registry,
        seed_approved_glossary=args.seed_approved_glossary,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
