"""Translation and inspector chat services."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.translation import ChatMessage, PipelineConfig, TranslationPipeline
from app.translation.infra.country_locale import COUNTRY_TO_LOCALE, resolve_locale_for_country
from app.translation.infra.runtime import is_mock_mode
from app.translation.text_processing.consistency_checker import check_translation_consistency
from backend.store.memory_store import _get_episode, save_translation_version, work_get


def _pipeline(locale: str) -> TranslationPipeline:
    return TranslationPipeline(PipelineConfig(locale=locale, mock=is_mock_mode()))


BLOCK_MESSAGES = {
    "non_korean_source": {
        "finalTranslation": "현재 한국어 원문만 지원하고 있어요. 한국어로 작성된 원문을 입력해 주세요.",
        "reviewSummary": "입력 언어 확인이 필요합니다.",
        "summary": "한국어 원문이 아닌 입력은 번역 모델 테스트 대상에서 제외됩니다.",
    },
}

_DEFAULT_BLOCK = {
    "finalTranslation": "입력을 처리할 수 없어요. 입력 내용을 확인해 주세요.",
    "reviewSummary": "입력 확인이 필요합니다.",
    "summary": "입력이 번역 모델 처리 대상으로 보이지 않았습니다.",
}


def _blocked_response(
    *, country: str, locale: str, source_text: str, block_reason: str
) -> dict[str, Any]:
    messages = BLOCK_MESSAGES.get(block_reason, _DEFAULT_BLOCK)
    message = messages["finalTranslation"]
    return {
        "country": country,
        "locale": locale,
        "finalTranslation": message,
        "reviewSummary": messages["reviewSummary"],
        "retrievalCount": 0,
        "workflow": {
            "source_text": source_text,
            "retrievals": [],
            "annotation_matches": [],
            "draft": {"translation": message, "strategy": "unsupported-source-language"},
            "inspection": {
                "summary": messages["summary"],
                "issues": [],
            },
            "reviewed_translation": message,
        },
        "memory": None,
    }


SEVERITY_LABELS = {
    "LOW": ("李멸퀬", "???섏젙? ?꾩슂 ?놁?留? ?쒖떆??援ш컙????踰??뺤씤?대낫?몄슂."),
    "MEDIUM": ("二쇱쓽", "?꾩??붋룻몴??由ъ뒪?ш? ?덉뼱 ?щ엺????踰????뺤씤?섎뒗 寃껋씠 醫뗭뒿?덈떎."),
    "HIGH": ("?꾩???議곗젙 沅뚯옣", "臾명솕沅??곹빀??臾몄젣媛 ?덉뼱 ?쒖떆??援ш컙???ㅻ벉??寃껋씠 醫뗭뒿?덈떎."),
    "CRITICAL": ("?ъ옉??沅뚯옣", "踰뺤쟻/?뚮옯??臾명솕沅?由ъ뒪?ш? 而ㅼ꽌 ?대떦 援ш컙??諛섎뱶???먮낫??寃껋씠 醫뗭뒿?덈떎."),
}
_SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def _clean_summary_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _top_severity(issues: list[dict[str, Any]]) -> str:
    top = ""
    top_rank = -1
    for issue in issues:
        sev = _clean_summary_text(issue.get("severity")).upper()
        if sev in _SEVERITY_ORDER:
            rank = _SEVERITY_ORDER.index(sev)
            if rank > top_rank:
                top_rank, top = rank, sev
    return top


def format_review_summary(workflow: dict[str, Any]) -> str:
    inspection = workflow.get("inspection", {}) or {}
    draft = workflow.get("draft", {}) or {}
    summary = _clean_summary_text(inspection.get("summary"))
    issues = [i for i in (inspection.get("issues") or []) if isinstance(i, dict)]
    rationale = _clean_summary_text(draft.get("rationale"))

    top_severity = _top_severity(issues)
    sev_title, sev_desc = SEVERITY_LABELS.get(
        top_severity,
        ("李멸퀬", "援ъ껜?곸씤 臾몄젣???뺤씤?섏? ?딆븯?듬땲?? ?꾩슂 ???쒗쁽????踰????댄렣蹂댁꽭??"),
    )

    issue_lines: list[str] = []
    for idx, issue in enumerate(issues, start=1):
        sev = _clean_summary_text(issue.get("severity")).upper()
        problem = _clean_summary_text(issue.get("problem"))
        translated_span = _clean_summary_text(issue.get("translated_span"))
        suggested = _clean_summary_text(issue.get("suggested"))
        parts = [f"{idx}) [{sev or '?뺤씤'}] {problem or '?뺤씤???꾩슂???쒗쁽?낅땲??'}"]
        if translated_span:
            parts.append(f"   - ???援ш컙: {translated_span}")
        if suggested:
            parts.append(f"   - ?쒖븞: {suggested}")
        issue_lines.append("\n".join(parts))

    sections: list[str] = [
        "\n".join([
            "1. ?듭떖 寃???붿빟",
            summary or "援ъ껜?곸씤 臾명솕沅?由ъ뒪?щ굹 ?꾩???臾몄젣???뺤씤?섏? ?딆븯?듬땲??",
            f"沅뚯옣 議곗튂: {sev_title}",
            sev_desc,
        ]),
        "\n".join([
            "2. 臾몄젣 援ш컙 諛??쒖븞",
            "\n\n".join(issue_lines) if issue_lines else "援ш컙 ?⑥쐞濡?蹂닿퀬??臾몄젣???놁뒿?덈떎.",
        ]),
        "\n".join([
            "3. 臾몄껜/?꾩????꾨왂",
            rationale or "臾몄껜? ?꾩????꾨왂? ???援?? ?낆옄 湲곗??쇰줈 ?먯뿰?ㅻ윭?댁? ?댄렣蹂댁꽭??",
            "????ぉ? 臾몄옣 ?명씉, ?댄쐶 ?좏깮, 臾명솕???꾧끝?⑥쓣 ?④퍡 蹂대뒗 ?⑸룄?낅땲??",
        ]),
    ]

    if top_severity:
        sections[0] += f"\n?ш컖?? {top_severity}"

    return "\n\n".join(sections)


def translate(payload: dict[str, Any]) -> dict[str, Any]:
    country = payload.get("targetCountry")
    source_text = (payload.get("sourceText") or "").strip()
    work_id = payload.get("workId")
    episode_id = payload.get("episodeId")
    if not country:
        raise ValueError("targetCountry is required")
    if not source_text:
        raise ValueError("sourceText is required")
    locale = resolve_locale_for_country(country)
    if not locale:
        raise ValueError(f"unsupported targetCountry: {country}")
    if work_id is not None:
        work_id_int = int(work_id)
        work = work_get(work_id_int)
        if not work:
            raise ValueError(f"work {work_id_int} not found")
        if episode_id is not None and not _get_episode(work_id_int, int(episode_id)):
            raise ValueError(f"episode {episode_id} not found for work {work_id_int}")

    workflow = _pipeline(locale).run_with_inspection(
        source_text,
        request_payload=payload,
        translation_memory=[],
    )
    data = asdict(workflow)
    if data.get("blocked"):
        return _blocked_response(
            country=country,
            locale=locale,
            source_text=source_text,
            block_reason=data.get("block_reason", ""),
        )
    final_translation = data.get("reviewed_translation", "")
    consistency = check_translation_consistency(
        source_text=source_text,
        translated_text=final_translation,
        locale=locale,
        terminology=payload.get("terminology") or payload.get("terms") or payload.get("glossary") or [],
    )
    data["consistency"] = consistency
    review_summary = format_review_summary(data)
    saved_version: dict[str, Any] | None = None
    terminology_memory = data.get("active_terminology") or data.get("terminology_candidates")
    if work_id is not None and episode_id is not None:
        saved_version = save_translation_version(
            work_id=int(work_id),
            episode_id=int(episode_id),
            country=country,
            locale=locale,
            source_text=source_text,
            final_translation=final_translation,
            review_summary=review_summary,
            workflow=data,
            memory={"terms": terminology_memory} if terminology_memory else None,
        )
    return {
        "country": country,
        "locale": locale,
        "finalTranslation": final_translation,
        "reviewSummary": review_summary,
        "retrievalCount": len(data.get("retrievals", [])),
        "workflow": data,
        "terminologyCandidates": data.get("terminology_candidates", []),
        "memory": None,
        "translationVersion": saved_version,
    }


def inspect_chat(payload: dict[str, Any]) -> dict[str, Any]:
    country = payload.get("targetCountry")
    question = (payload.get("question") or "").strip()
    source_text = (payload.get("sourceText") or "").strip()
    current_translation = (payload.get("currentTranslation") or "").strip()
    workflow = payload.get("workflow") or {}
    chat_history_payload = payload.get("chatHistory") or []

    if not country:
        raise ValueError("targetCountry is required")
    if not question:
        raise ValueError("question is required")
    locale = COUNTRY_TO_LOCALE.get(country)
    if not locale:
        raise ValueError(f"unsupported targetCountry: {country}")

    draft = workflow.get("draft") or {}
    inspection = workflow.get("inspection") or {}
    retrievals = workflow.get("retrievals") or []
    reviewed_translation = (
        current_translation
        or workflow.get("reviewed_translation")
        or draft.get("translation")
        or ""
    )
    source_text = source_text or workflow.get("source_text") or ""

    used_references = [
        {
            "id": (row.get("item") or {}).get("id"),
            "ko_anchor_expression": (row.get("item") or {}).get("ko_anchor_expression", []),
            "target_expression": (row.get("item") or {}).get("expression", ""),
            "score": row.get("score"),
        }
        for row in retrievals
        if isinstance(row, dict)
    ]

    chat_history: list[ChatMessage] = []
    for row in chat_history_payload[-8:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "").strip()
        content = str(row.get("content") or "").strip()
        if role in {"user", "assistant", "ai"} and content:
            chat_history.append(ChatMessage(role="assistant" if role == "ai" else role, content=content))

    reply = _pipeline(locale).chatbot.reply(
        user_message=question,
        source_text=source_text,
        draft_translation=draft.get("translation", ""),
        reviewed_translation=reviewed_translation,
        translation_rationale=draft.get("rationale", ""),
        used_references=used_references,
        inspection_report=inspection,
        translation_memory=[],
        chat_history=chat_history,
    )

    return {
        "answer": reply.answer,
        "proposedTranslation": reply.proposed_translation,
        "changeSummary": reply.change_summary,
        "needsUserConfirmation": reply.needs_user_confirmation,
    }
