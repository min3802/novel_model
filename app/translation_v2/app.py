from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import streamlit as st

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from translation.agents.chatbot import ChatMessage, ChatbotAgent
from translation.agents.translator import Translator
from translation.config import PipelineConfig
from translation.infra.country_locale import resolve_country_for_locale, resolve_locale_for_country
from translation.text_processing.translation_consistency import (
    TranslationConsistencyManager,
    default_media_root,
    read_json,
)


LOCALE_OPTIONS = {
    "영어(미국)": "ko_en_us",
    "일본어": "ko_ja",
    "중국어(간체)": "ko_zh_cn",
    "태국어": "ko_th_th",
}

MODEL_OPTIONS = ["gpt-4.1-mini", "gpt-5-mini"]


def safe_episode_id(episode_no: int | str) -> str:
    try:
        return f"EP_{int(episode_no):03d}"
    except Exception:
        return f"EP_{episode_no}"


def episode_file(work_id: str, episode_no: int) -> Path:
    return default_media_root() / work_id / "uploads" / f"episode_{episode_no:03d}.txt"


def translated_file(work_id: str, episode_no: int, locale: str) -> Path:
    return default_media_root() / work_id / "translated" / f"episode_{episode_no:03d}_{locale}.txt"


def list_episodes(work_id: str) -> list[int]:
    upload_dir = default_media_root() / work_id / "uploads"
    if not upload_dir.exists():
        return []
    episode_nos: list[int] = []
    for path in upload_dir.glob("episode_*.txt"):
        match = re.search(r"episode_(\d+)", path.stem)
        if match:
            episode_nos.append(int(match.group(1)))
    return sorted(set(episode_nos))


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8")


def make_config(locale: str, translation_model: str, review_model: str) -> PipelineConfig:
    return PipelineConfig(
        locale=locale,
        translation_model=translation_model,
        review_model=review_model,
        mock=False,
    )


def guess_override_from_message(message: str) -> tuple[str, str]:
    """Very small helper for UI convenience, not a source of truth."""
    text = message.strip()
    patterns = [
        r"['\"]?([^'\"\s]{1,30})['\"]?\s*(?:을|를|은|는)?\s*['\"]([A-Za-z][A-Za-z0-9 .,'\-]{1,80})['\"]\s*(?:로|으로|라고|로\s*바꿔)",
        r"([^\s]{1,30})\s*=>\s*([A-Za-z][A-Za-z0-9 .,'\-]{1,80})",
        r"([^\s]{1,30})\s*->\s*([A-Za-z][A-Za-z0-9 .,'\-]{1,80})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip("'\" ,."), m.group(2).strip("'\" ,.")
    return "", ""


def load_json_file(path: Path | None, default: dict[str, Any]) -> dict[str, Any]:
    if path is None:
        return default
    return read_json(path, default)


def translate_current_episode(
    *,
    work_id: str,
    episode_no: int,
    locale: str,
    translation_model: str,
    review_model: str,
    source_text: str,
) -> dict[str, Any]:
    config = make_config(locale, translation_model, review_model)
    resources = config.resolved_resources()
    manager = TranslationConsistencyManager(
        work_id=work_id,
        target_locale=locale,
        target_language=resources.target_language,
    )
    runtime = manager.build_runtime_context(source_text)
    memory_context = manager.render_prompt_context(source_text)

    translator = Translator(config)
    draft = translator.translate(
        source_text,
        [],
        memory_context=memory_context,
        translation_profile=None,
        source_analysis=None,
    )
    draft_dict = asdict(draft)
    translated = draft.translation
    episode_id = safe_episode_id(episode_no)
    report = manager.update_after_translation(
        source_text=source_text,
        translated_text=translated,
        episode_id=episode_id,
        draft=draft_dict,
        active_terminology=runtime.get("terms", []),
    )
    out_path = translated_file(work_id, episode_no, locale)
    write_text(out_path, translated)
    return {
        "draft": draft_dict,
        "translation": translated,
        "report": report,
        "runtime": runtime,
        "memory_context": memory_context,
        "output_path": str(out_path),
    }


def run_chatbot(
    *,
    work_id: str,
    episode_no: int,
    locale: str,
    translation_model: str,
    review_model: str,
    source_text: str,
    current_translation: str,
    user_message: str,
    draft: dict[str, Any] | None,
    chat_history: list[dict[str, str]],
) -> dict[str, Any]:
    config = make_config(locale, translation_model, review_model)
    resources = config.resolved_resources()
    manager = TranslationConsistencyManager(work_id=work_id, target_locale=locale, target_language=resources.target_language)
    glossary = manager.load_glossary()
    overrides = manager.load_overrides()
    bot = ChatbotAgent(config)
    reply = bot.reply(
        user_message=user_message,
        source_text=source_text,
        draft_translation=(draft or {}).get("translation", current_translation),
        reviewed_translation=current_translation,
        translation_rationale=(draft or {}).get("rationale", ""),
        used_references=[],
        inspection_report={},
        translation_memory=[*glossary.get("items", []), *overrides.get("items", [])],
        chat_history=[ChatMessage(**row) for row in chat_history if row.get("role") in {"user", "assistant"}],
    )
    return reply.to_dict()


def init_session() -> None:
    st.session_state.setdefault("translation_result", None)
    st.session_state.setdefault("current_translation", "")
    st.session_state.setdefault("draft", None)
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("last_chat_reply", None)
    st.session_state.setdefault("last_user_message", "")
    st.session_state.setdefault("selected_signature", "")
    st.session_state.setdefault("flash_message", "")


def main() -> None:
    st.set_page_config(page_title="w.LiGHTER 번역 일관성 테스트", layout="wide")
    init_session()

    st.title("w.LiGHTER 번역 일관성 테스트")
    st.caption("기존 번역 코어는 유지하고, 번역 전후 일관성 데이터 저장/적용과 챗봇 수정 저장을 확인하는 테스트용 앱입니다.")
    if st.session_state.get("flash_message"):
        st.success(st.session_state.pop("flash_message"))

    with st.sidebar:
        st.subheader("실행 설정")
        work_id = st.text_input("work_id", value="WORK_001")
        locale_label = st.selectbox("대상 언어", list(LOCALE_OPTIONS.keys()), index=0)
        locale = LOCALE_OPTIONS[locale_label]
        default_translation_model = os.getenv("OPENAI_TRANSLATION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
        default_review_model = os.getenv("OPENAI_REVIEW_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
        translation_model = st.selectbox(
            "번역 모델",
            MODEL_OPTIONS,
            index=MODEL_OPTIONS.index(default_translation_model) if default_translation_model in MODEL_OPTIONS else 0,
        )
        review_model = st.selectbox(
            "챗봇/검수 모델",
            MODEL_OPTIONS,
            index=MODEL_OPTIONS.index(default_review_model) if default_review_model in MODEL_OPTIONS else 0,
        )
        st.caption("기본 추천: gpt-4.1-mini. 일관성 기능 검증은 속도/비용이 중요하고, 확정 표현은 glossary/user_overrides로 강제하기 때문입니다. 품질 비교가 필요할 때만 gpt-5-mini로 바꿔보면 됩니다.")

        episodes = list_episodes(work_id)
        if episodes:
            episode_no = st.selectbox("회차", episodes, index=0)
        else:
            episode_no = st.number_input("회차", min_value=1, value=1, step=1)
        st.divider()
        st.write("media root")
        st.code(str(default_media_root()))
        if not os.getenv("OPENAI_API_KEY"):
            st.warning("OPENAI_API_KEY가 현재 환경에서 보이지 않습니다. .env 또는 환경변수에 넣어주세요.")

    source_path = episode_file(work_id, int(episode_no))
    source_text = read_text(source_path)
    saved_translation_path = translated_file(work_id, int(episode_no), locale)
    saved_translation = read_text(saved_translation_path)

    selected_signature = f"{work_id}:{int(episode_no)}:{locale}"
    if st.session_state.selected_signature != selected_signature:
        st.session_state.selected_signature = selected_signature
        st.session_state.translation_result = None
        st.session_state.current_translation = saved_translation
        st.session_state.draft = None
        st.session_state.chat_history = []
        st.session_state.last_chat_reply = None
        st.session_state.last_user_message = ""

    manager = TranslationConsistencyManager(work_id=work_id, target_locale=locale, target_language=make_config(locale, translation_model, review_model).resolved_resources().target_language)

    top_cols = st.columns([1, 1, 1, 1])
    top_cols[0].metric("업로드 회차", len(episodes))
    top_cols[1].metric("원문 글자 수", len(source_text))
    top_cols[2].metric("glossary", len(manager.load_glossary().get("items", [])))
    top_cols[3].metric("user overrides", len(manager.load_overrides().get("items", [])))

    if not source_text:
        st.error(f"원문 파일을 찾지 못했습니다: {source_path}")
        st.stop()

    tab_source, tab_translate, tab_chat, tab_data, tab_check = st.tabs([
        "원문/번역",
        "번역 실행",
        "챗봇 수정",
        "일관성 데이터",
        "확인 포인트",
    ])

    with tab_source:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("원문")
            st.caption(str(source_path))
            st.text_area("source", value=source_text, height=520, label_visibility="collapsed")
        with col2:
            st.subheader("현재 번역")
            st.caption(str(saved_translation_path))
            display_translation = st.session_state.current_translation or saved_translation
            st.text_area("translation", value=display_translation, height=520, label_visibility="collapsed")
            if saved_translation_path.exists():
                st.caption("저장된 번역 파일을 불러왔습니다." if display_translation else "번역 파일은 있지만 내용이 비어 있습니다.")

    with tab_translate:
        st.subheader("번역 실행")
        runtime_context = manager.render_prompt_context(source_text)
        with st.expander("이번 회차에 주입될 일관성 context", expanded=False):
            st.code(runtime_context or "이번 원문에 매칭되는 확정 용어가 아직 없습니다.")
        if st.button("번역 실행", type="primary"):
            with st.spinner("번역 중입니다. 5-mini는 시간이 더 걸릴 수 있습니다."):
                try:
                    result = translate_current_episode(
                        work_id=work_id,
                        episode_no=int(episode_no),
                        locale=locale,
                        translation_model=translation_model,
                        review_model=review_model,
                        source_text=source_text,
                    )
                except Exception as exc:
                    st.exception(exc)
                else:
                    st.session_state.translation_result = result
                    st.session_state.current_translation = result["translation"]
                    st.session_state.draft = result["draft"]
                    st.session_state.flash_message = "번역 및 일관성 데이터 저장 완료"
                    st.rerun()
        if st.session_state.translation_result:
            st.write("저장 경로")
            st.code(st.session_state.translation_result.get("output_path", ""))
            st.write("최근 리포트")
            st.json(st.session_state.translation_result.get("report", {}))

    with tab_chat:
        st.subheader("챗봇 수정 테스트")
        if not st.session_state.current_translation:
            st.info("먼저 번역을 실행하거나 저장된 번역 파일을 불러와야 합니다.")
        user_message = st.text_area("수정/질문", placeholder="예: 한연주는 Han Yeon-joo로 통일해줘", height=100)
        if st.button("챗봇에게 요청"):
            if not user_message.strip():
                st.warning("요청 내용을 입력해 주세요.")
            else:
                with st.spinner("챗봇 응답 생성 중..."):
                    try:
                        reply = run_chatbot(
                            work_id=work_id,
                            episode_no=int(episode_no),
                            locale=locale,
                            translation_model=translation_model,
                            review_model=review_model,
                            source_text=source_text,
                            current_translation=st.session_state.current_translation,
                            user_message=user_message,
                            draft=st.session_state.draft,
                            chat_history=st.session_state.chat_history,
                        )
                    except Exception as exc:
                        st.exception(exc)
                    else:
                        st.session_state.last_chat_reply = reply
                        st.session_state.last_user_message = user_message
                        st.session_state.chat_history.append({"role": "user", "content": user_message})
                        st.session_state.chat_history.append({"role": "assistant", "content": reply.get("answer", "")})
        reply = st.session_state.last_chat_reply
        if reply:
            st.write("챗봇 답변")
            st.info(reply.get("answer", ""))
            st.write("변경 요약")
            st.code(reply.get("change_summary", ""))
            proposed = reply.get("proposed_translation", "")
            if proposed:
                st.write("제안 번역")
                st.text_area("proposed", value=proposed, height=280, label_visibility="collapsed")
                if st.button("제안 번역 반영"):
                    st.session_state.current_translation = proposed
                    write_text(translated_file(work_id, int(episode_no), locale), proposed)
                    manager.save_chat_edit(
                        episode_id=safe_episode_id(int(episode_no)),
                        user_message=st.session_state.last_user_message,
                        answer=reply.get("answer", ""),
                        change_summary=reply.get("change_summary", ""),
                        proposed_translation=proposed,
                        applied=True,
                    )
                    st.session_state.flash_message = "챗봇 제안 번역을 번역 파일에 반영했습니다. 필요한 표현은 user_overrides에 저장하세요."
                    st.rerun()
            guessed_source, guessed_target = guess_override_from_message(st.session_state.last_user_message)
            st.divider()
            st.write("수정 표현을 일관성 데이터에 저장")
            o_col1, o_col2, o_col3 = st.columns([1, 1, 1])
            source_override = o_col1.text_input("원문 표현", value=guessed_source, key="override_source")
            target_override = o_col2.text_input("확정 번역", value=guessed_target, key="override_target")
            category_override = o_col3.selectbox("분류", ["character_name", "organization_name", "place_name", "term", "honorific", "proper_noun"], index=0)
            reason_override = st.text_input("저장 사유", value="챗봇 수정/사용자 승인 표현")
            if st.button("user_overrides.json에 저장", type="primary"):
                result = manager.apply_user_override(
                    source_text_ko=source_override,
                    target_text=target_override,
                    category=category_override,
                    reason_ko=reason_override,
                )
                st.json(result)

    with tab_data:
        st.subheader("일관성 데이터")
        data_tabs = st.tabs(["glossary", "user_overrides", "translation_memory", "chat_edits", "latest_report"])
        with data_tabs[0]:
            st.json(manager.load_glossary())
        with data_tabs[1]:
            st.json(manager.load_overrides())
        with data_tabs[2]:
            st.json(manager.load_memory())
        with data_tabs[3]:
            st.json(manager.load_chat_edits())
        with data_tabs[4]:
            report_path = manager.report_path(safe_episode_id(int(episode_no)))
            st.caption(str(report_path))
            st.json(load_json_file(report_path, {}))

    with tab_check:
        st.subheader("이번 테스트에서 확인할 것")
        st.markdown(
            """
            1. 1화 번역 후 `glossary.json`에 이름/조직/장소/핵심 용어가 과하지 않게 저장되는지 확인한다.
            2. 2화 번역 전 `이번 회차에 주입될 일관성 context`에 1화에서 저장된 항목 중 실제 등장 항목만 들어가는지 확인한다.
            3. 동일한 원문 표현이 이전 번역과 다른 target으로 나오면 `glossary.conflicts` 또는 리포트에 남는지 확인한다.
            4. 챗봇으로 수정한 뒤 `제안 번역 반영`을 누르면 번역 파일이 바뀌는지 확인한다.
            5. 수정 표현을 `user_overrides.json`에 저장한 뒤 다음 회차 번역 context에서 `USER_OVERRIDE`로 우선 적용되는지 확인한다.
            6. 문체 일관성은 현재 범위에서 제외한다. 지금은 고유명사/용어/사용자 수정 일관성만 본다.
            """
        )


if __name__ == "__main__":
    main()
