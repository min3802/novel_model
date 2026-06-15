from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
TMP_SOURCE_PATH = ROOT / "tmp" / "streamlit_source.txt"
TRANSLATION_OUTPUT_PATH = ROOT / "outputs" / "streamlit_translation_result.json"
ENTITY_OUTPUT_PATH = ROOT / "outputs" / "streamlit_entity_probe.json"
DEFAULT_MODEL = "gpt-5.4-mini"
TARGET_LOCALES = ["ko_ja", "ko_en_us", "ko_zh_cn", "ko_th_th"]


@dataclass
class RunLog:
    command: list[str] = field(default_factory=list)
    output_path: str = ""
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    parse_error: str = ""


def _session_default() -> None:
    st.session_state.setdefault("source_text", "")
    st.session_state.setdefault("translation_json", None)
    st.session_state.setdefault("entity_json", None)
    st.session_state.setdefault("translation_log", RunLog())
    st.session_state.setdefault("entity_log", RunLog())


def _read_openai_key_from_dotenv(path: Path = ROOT / ".env") -> str:
    if not path.exists():
        return ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "OPENAI_API_KEY":
            return value.strip().strip('"').strip("'")
    return ""


def _subprocess_env() -> tuple[dict[str, str], str]:
    env = os.environ.copy()
    key = env.get("OPENAI_API_KEY") or _read_openai_key_from_dotenv()
    if key:
        env["OPENAI_API_KEY"] = key
    return env, "set" if key else "missing"


def _display_command(command: list[str]) -> str:
    return " ".join(command)


def _run_command(command: list[str], output_path: Path) -> tuple[RunLog, dict[str, Any] | None]:
    env, _ = _subprocess_env()
    start = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed = time.perf_counter() - start
    log = RunLog(
        command=command,
        output_path=str(output_path.relative_to(ROOT)),
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        elapsed_seconds=elapsed,
    )
    parsed: dict[str, Any] | None = None
    if output_path.exists():
        try:
            parsed = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - displayed in UI
            log.parse_error = f"Failed to parse output JSON: {exc}"
    elif proc.returncode == 0:
        log.parse_error = "Output JSON was not created."
    return log, parsed


def _write_source_file(source_text: str) -> Path:
    TMP_SOURCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TMP_SOURCE_PATH.write_text(source_text, encoding="utf-8")
    return TMP_SOURCE_PATH


def _translation_command(input_path: Path, target_locale: str, *, mock: bool) -> list[str]:
    command = [
        sys.executable,
        "scripts/run_long_translation_smoke.py",
        "--input",
        str(input_path.relative_to(ROOT)),
        "--target-locale",
        target_locale,
        "--work-id",
        "streamlit_work",
        "--episode-id",
        "streamlit_episode",
        "--output",
        str(TRANSLATION_OUTPUT_PATH.relative_to(ROOT)),
    ]
    if mock:
        command.append("--mock")
    return command


def _entity_command(input_path: Path, target_locale: str, model: str) -> list[str]:
    return [
        sys.executable,
        "scripts/run_entity_extraction_probe.py",
        "--input",
        str(input_path.relative_to(ROOT)),
        "--target-locale",
        target_locale,
        "--model",
        model,
        "--output",
        str(ENTITY_OUTPUT_PATH.relative_to(ROOT)),
    ]


def _get(data: dict[str, Any] | None, *keys: str, default: Any = "") -> Any:
    if not data:
        return default
    for key in keys:
        if key in data:
            return data.get(key)
    return default


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _metric_row(translation: dict[str, Any] | None, entity: dict[str, Any] | None) -> None:
    cards = _as_list(_get(translation, "authorReviewCards", "author_review_cards", default=[]))
    decisions = _as_list(_get(translation, "translationDecisions", "translation_decisions", default=[]))
    evidence = _as_list(_get(translation, "ragEvidence", "rag_evidence", default=[]))
    final_translation = _get(translation, "finalTranslation", "final_translation", default="")
    characters = _as_list(_get(entity, "characters", default=[]))
    ambiguous_terms = _as_list(_get(entity, "ambiguousTerms", default=[]))
    cols = st.columns(6)
    cols[0].metric("finalTranslationLen", len(final_translation or ""))
    cols[1].metric("cards", len(cards))
    cols[2].metric("decisions", len(decisions))
    cols[3].metric("ragEvidence", len(evidence))
    cols[4].metric("entity chars", len(characters))
    cols[5].metric("ambiguous", len(ambiguous_terms))


def _render_key_value(label: str, value: Any) -> None:
    st.markdown(f"**{label}:** {value if value not in (None, '') else 'N/A'}")


def _render_translation_preview(data: dict[str, Any] | None, source_text: str) -> None:
    st.subheader("Translation Preview")
    if not data:
        st.info("Run translation smoke to see preview.")
        return
    delivery_status = _get(data, "deliveryStatus", "delivery_status", default="")
    user_error = _get(data, "userVisibleErrorCode", "user_visible_error_code", default="")
    message = _get(data, "message", default="")
    final_translation = _get(data, "finalTranslation", "final_translation", default="")
    status_fn = st.error if delivery_status == "blocked_translation_safety" else st.warning if delivery_status == "qa_warning" else st.success
    status_fn(f"deliveryStatus: {delivery_status or 'N/A'}")
    if user_error:
        st.error(f"userVisibleErrorCode: {user_error}")
    if message:
        st.warning(f"message: {message}")
    st.caption(f"finalTranslationLen={len(final_translation or '')}")
    if delivery_status == "blocked_translation_safety" and final_translation:
        st.warning("blocked_translation_safety인데 finalTranslation이 비어 있지 않습니다.")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Source")
        st.text_area("sourceText", source_text, height=480, disabled=True)
    with right:
        st.markdown("#### Final Translation")
        st.text_area("finalTranslation", final_translation or "", height=480, disabled=True)


def _render_author_cards(data: dict[str, Any] | None) -> None:
    cards = _as_list(_get(data, "authorReviewCards", "author_review_cards", default=[]))
    st.subheader(f"authorReviewCards count: {len(cards)}")
    if not cards:
        st.info("No author review cards.")
        return
    for index, card in enumerate(cards, start=1):
        with st.container(border=True):
            st.markdown(f"### Card {index}")
            cols = st.columns(3)
            cols[0].write(f"priority: {_get(card, 'priority', default='N/A')}")
            cols[1].write(f"status: {_get(card, 'status', default='N/A')}")
            cols[2].write(f"decisionType: {_get(card, 'decisionType', 'decision_type', default='N/A')}")
            _render_key_value("sourceSpan", _get(card, "sourceSpan", "source_span", default=""))
            _render_key_value("targetSpan", _get(card, "targetSpan", "target_span", default=""))
            _render_key_value("currentTranslation", _get(card, "currentTranslation", "current_translation", default=""))
            _render_key_value("explanation", _get(card, "explanation", default=""))
            _render_key_value("suggestedActions", _get(card, "suggestedActions", "suggested_actions", default=[]))
            _render_key_value(
                "createdFromEvidenceIds",
                _get(card, "createdFromEvidenceIds", "created_from_evidence_ids", default=[]),
            )
            with st.expander("Raw card JSON"):
                st.json(card)


def _render_decisions(data: dict[str, Any] | None) -> None:
    decisions = _as_list(_get(data, "translationDecisions", "translation_decisions", default=[]))
    st.subheader(f"translationDecisions count: {len(decisions)}")
    if not decisions:
        st.info("No translation decisions.")
        return
    for index, decision in enumerate(decisions, start=1):
        with st.container(border=True):
            st.markdown(f"### Decision Card {index}")
            cols = st.columns(3)
            cols[0].write(f"decisionType: {_get(decision, 'decisionType', 'decision_type', default='N/A')}")
            cols[1].write(f"priority: {_get(decision, 'priority', default='N/A')}")
            cols[2].write(f"confidence: {_get(decision, 'confidence', default='N/A')}")
            _render_key_value("sourceSpan", _get(decision, "sourceSpan", "source_span", default=""))
            _render_key_value("targetSpan", _get(decision, "targetSpan", "target_span", default=""))
            _render_key_value(
                "currentTranslation",
                _get(
                    decision,
                    "currentTranslation",
                    "current_translation",
                    "targetSpan",
                    "target_span",
                    default="",
                ),
            )
            explanation = _get(decision, "explanation", "rationale", "reason", default="")
            _render_key_value("reason/explanation", explanation or "No explanation field in response")
            _render_key_value("risk", _get(decision, "risk", "riskLevel", "risk_level", default=""))
            _render_key_value("suggestedActions", _get(decision, "suggestedActions", "suggested_actions", default=[]))
            _render_key_value(
                "createdFromEvidenceIds",
                _get(decision, "createdFromEvidenceIds", "created_from_evidence_ids", "evidenceIds", "evidence_ids", default=[]),
            )
            _render_key_value("alignmentStatus", _get(decision, "alignmentStatus", "alignment_status", default=""))
            _render_key_value("unresolvedRisk", _get(decision, "unresolvedRisk", "unresolved_risk", default=""))
            with st.expander("Raw decision JSON"):
                st.json(decision)


def _table_rows(items: list[dict[str, Any]], *, name_key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                name_key: item.get(name_key, ""),
                "aliases": ", ".join(item.get("aliases") or []),
                "confidence": item.get("confidence", ""),
                "evidenceCount": _count(item.get("evidence")),
                "reason": item.get("reason", ""),
            }
        )
    return rows


def _render_entity_probe(data: dict[str, Any] | None) -> None:
    st.subheader("Entity Probe")
    if not data:
        st.info("Run entity probe to see results.")
        return
    characters = _as_list(data.get("characters"))
    places = _as_list(data.get("places"))
    organizations = _as_list(data.get("organizations"))
    ambiguous_terms = _as_list(data.get("ambiguousTerms"))

    st.markdown("### Characters")
    if characters:
        st.dataframe(_table_rows(characters, name_key="canonicalName"), use_container_width=True)
    for item in characters:
        title = f"{item.get('canonicalName', 'character')} aliases={item.get('aliases') or []}"
        with st.expander(title):
            _render_key_value("canonicalName", item.get("canonicalName", ""))
            _render_key_value("aliases", item.get("aliases", []))
            _render_key_value("confidence", item.get("confidence", ""))
            _render_key_value("evidence", item.get("evidence", []))
            _render_key_value("reason", item.get("reason", ""))
            _render_key_value("targetLocaleHint", item.get("targetLocaleHint", {}))
            st.json(item)

    st.markdown("### Places")
    if places:
        st.dataframe(_table_rows(places, name_key="name"), use_container_width=True)
    for item in places:
        with st.expander(f"place: {item.get('name', '')}"):
            st.json(item)

    st.markdown("### Organizations")
    if organizations:
        st.dataframe(_table_rows(organizations, name_key="name"), use_container_width=True)
    for item in organizations:
        with st.expander(f"organization: {item.get('name', '')}"):
            st.json(item)

    st.markdown("### Ambiguous Terms")
    for term in ambiguous_terms:
        with st.container(border=True):
            _render_key_value("text", term.get("text", ""))
            _render_key_value("possibleEntity", term.get("possibleEntity", ""))
            _render_key_value("possibleCommonMeaning", term.get("possibleCommonMeaning", ""))
            _render_key_value("confidence", term.get("confidence", ""))
            _render_key_value("evidence", term.get("evidence", []))
            _render_key_value("note", term.get("note", ""))
            with st.expander("Raw ambiguous term JSON"):
                st.json(term)


def _render_log(label: str, log: RunLog, *, show_logs: bool) -> None:
    st.markdown(f"### {label}")
    _render_key_value("command", _display_command(log.command) if log.command else "N/A")
    _render_key_value("output path", log.output_path)
    _render_key_value("returncode", log.returncode)
    _render_key_value("elapsed seconds", f"{log.elapsed_seconds:.2f}" if log.elapsed_seconds else "N/A")
    if log.parse_error:
        st.error(log.parse_error)
    if show_logs:
        st.markdown("#### stdout")
        st.code(log.stdout or "", language="text")
        st.markdown("#### stderr")
        st.code(log.stderr or "", language="text")


def _render_backend_debug(
    translation: dict[str, Any] | None,
    entity: dict[str, Any] | None,
    translation_log: RunLog,
    entity_log: RunLog,
    *,
    api_key_status: str,
    show_logs: bool,
) -> None:
    st.subheader("Evidence & Backend Debug")
    _render_key_value("OPENAI_API_KEY status", api_key_status)
    _metric_row(translation, entity)
    _render_log("translation command", translation_log, show_logs=show_logs)
    _render_log("entity probe command", entity_log, show_logs=show_logs)

    metadata = _get(translation, "metadata", default={})
    if metadata:
        with st.expander("metadata"):
            st.json(metadata)
    evidence = _as_list(_get(translation, "ragEvidence", "rag_evidence", default=[]))
    st.markdown(f"### ragEvidence count: {len(evidence)}")
    for item in evidence:
        with st.expander(f"evidence: {item.get('id') or item.get('sourceId') or item.get('source_id') or 'N/A'}"):
            _render_key_value("id", item.get("id", ""))
            _render_key_value("source", item.get("source", ""))
            _render_key_value("span", item.get("sourceSpan") or item.get("source_span") or item.get("anchor") or "")
            _render_key_value("confidence", item.get("confidence", ""))
            st.json(item)


def _json_download(label: str, data: dict[str, Any] | None, file_name: str) -> None:
    if not data:
        st.info(f"No {label} JSON.")
        return
    content = json.dumps(data, ensure_ascii=False, indent=2)
    st.download_button(label=f"Download {label} JSON", data=content, file_name=file_name, mime="application/json")
    st.json(data)


def main() -> None:
    st.set_page_config(page_title="Novel Translation Lab", layout="wide")
    _session_default()
    env, api_key_status = _subprocess_env()
    _ = env  # keep key handling centralized without displaying values

    st.title("Novel Translation Lab")
    st.caption("개발자용 번역 실험실입니다. 번역 결과, 검수 카드, 판단 근거, entity probe, backend JSON을 함께 확인합니다.")

    with st.sidebar:
        target_locale = st.selectbox("targetLocale", TARGET_LOCALES, index=0)
        model = st.text_input("model", value=DEFAULT_MODEL)
        run_mode = st.radio("run mode", ["real", "mock"], index=0)
        run_translation = st.checkbox("Run translation smoke", value=True)
        run_entity = st.checkbox("Run entity probe", value=True)
        show_raw_json = st.checkbox("Show raw JSON", value=True)
        show_subprocess_logs = st.checkbox("Show subprocess logs", value=True)
        run_button = st.button("Run selected checks", type="primary")
        clear_button = st.button("Clear current result")
        st.divider()
        st.write(f"OPENAI_API_KEY: {api_key_status}")

    uploaded = st.file_uploader("Upload source text file", type=["txt", "md"])
    uploaded_text = ""
    if uploaded is not None:
        uploaded_text = uploaded.read().decode("utf-8")
        st.info(f"Using uploaded file: {uploaded.name}")
        st.session_state["source_text"] = uploaded_text

    source_text = st.text_area(
        "sourceText",
        value=st.session_state.get("source_text", ""),
        height=220,
        placeholder="긴 한국어 웹소설 원문을 입력하거나 파일을 업로드하세요.",
    )
    st.session_state["source_text"] = source_text

    if clear_button:
        st.session_state["translation_json"] = None
        st.session_state["entity_json"] = None
        st.session_state["translation_log"] = RunLog()
        st.session_state["entity_log"] = RunLog()
        st.rerun()

    if run_button:
        if not source_text.strip():
            st.error("sourceText is empty.")
        else:
            input_path = _write_source_file(source_text)
            if run_translation:
                command = _translation_command(input_path, target_locale, mock=run_mode == "mock")
                log, parsed = _run_command(command, TRANSLATION_OUTPUT_PATH)
                st.session_state["translation_log"] = log
                st.session_state["translation_json"] = parsed
            if run_entity:
                command = _entity_command(input_path, target_locale, model)
                log, parsed = _run_command(command, ENTITY_OUTPUT_PATH)
                st.session_state["entity_log"] = log
                st.session_state["entity_json"] = parsed

    translation_json = st.session_state.get("translation_json")
    entity_json = st.session_state.get("entity_json")
    translation_log = st.session_state.get("translation_log") or RunLog()
    entity_log = st.session_state.get("entity_log") or RunLog()

    _metric_row(translation_json, entity_json)

    tabs = st.tabs(
        [
            "Translation Preview",
            "Author Review Cards",
            "Why / Decisions",
            "Entity Probe",
            "Evidence & Backend Debug",
            "Raw JSON",
        ]
    )
    with tabs[0]:
        _render_translation_preview(translation_json, source_text)
    with tabs[1]:
        _render_author_cards(translation_json)
    with tabs[2]:
        _render_decisions(translation_json)
    with tabs[3]:
        _render_entity_probe(entity_json)
    with tabs[4]:
        _render_backend_debug(
            translation_json,
            entity_json,
            translation_log,
            entity_log,
            api_key_status=api_key_status,
            show_logs=show_subprocess_logs,
        )
    with tabs[5]:
        if show_raw_json:
            st.markdown("### Translation full JSON")
            _json_download("translation", translation_json, "streamlit_translation_result.json")
            st.markdown("### Entity probe full JSON")
            _json_download("entity probe", entity_json, "streamlit_entity_probe.json")
        else:
            st.info("Enable 'Show raw JSON' in the sidebar.")


if __name__ == "__main__":
    main()
