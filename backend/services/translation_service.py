"""Translation and inspector chat services."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.translation import ChatMessage, TranslationPipeline, PipelineConfig
from app.translation.text_processing.consistency_checker import check_translation_consistency
from app.translation.infra.runtime import is_mock_mode
from app.translation.text_processing.terminology import (
    extract_noun_terminology_candidates,
    merge_terminology,
    render_terminology_context,
)
from backend.store.memory_store import _get_episode, save_translation_version, work_get

COUNTRY_TO_LOCALE = {
    "일본": "ko_ja",
    "미국": "ko_en_us",
    "중국": "ko_zh_cn",
    "태국": "ko_th_th",
}


def _pipeline(locale: str) -> TranslationPipeline:
    return TranslationPipeline(PipelineConfig(locale=locale, mock=is_mock_mode()))


def _config(locale: str) -> PipelineConfig:
    return PipelineConfig(locale=locale, mock=is_mock_mode())


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
    "summary": "입력이 번역 모델 처리 대상에서 제외되었습니다.",
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


# Inspector severity(LOW~CRITICAL) 기준 사용자용 라벨.
SEVERITY_LABELS = {
    "LOW": ("참고", "큰 수정은 필요 없지만, 표시된 구간을 한 번 확인해보세요."),
    "MEDIUM": ("주의", "현지화·표현 리스크가 있어 사람이 한 번 더 확인하는 것이 좋습니다."),
    "HIGH": ("현지화 조정 권장", "문화권 적합성 문제가 있어 표시된 구간을 다듬는 것이 좋습니다."),
    "CRITICAL": ("재작성 권장", "법적/플랫폼/문화권 리스크가 커서 해당 구간을 반드시 손보는 것이 좋습니다."),
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
    # Inspector 새 구조({summary, issues[]}) + Translator draft(rationale) 기준으로 요약을 구성한다.
    inspection = workflow.get("inspection", {}) or {}
    draft = workflow.get("draft", {}) or {}
    summary = _clean_summary_text(inspection.get("summary"))
    issues = [i for i in (inspection.get("issues") or []) if isinstance(i, dict)]
    rationale = _clean_summary_text(draft.get("rationale"))

    top_severity = _top_severity(issues)
    sev_title, sev_desc = SEVERITY_LABELS.get(
        top_severity,
        ("참고", "구체적인 문제는 확인되지 않았습니다. 필요 시 표현을 한 번 더 살펴보세요."),
    )

    # 검출된 issue 들을 사람이 읽기 좋은 한국어 항목으로 변환.
    issue_lines: list[str] = []
    for idx, issue in enumerate(issues, start=1):
        sev = _clean_summary_text(issue.get("severity")).upper()
        problem = _clean_summary_text(issue.get("problem"))
        translated_span = _clean_summary_text(issue.get("translated_span"))
        suggested = _clean_summary_text(issue.get("suggested"))
        parts = [f"{idx}) [{sev or '확인'}] {problem or '확인이 필요한 표현입니다.'}"]
        if translated_span:
            parts.append(f"   - 대상 구간: {translated_span}")
        if suggested:
            parts.append(f"   - 제안: {suggested}")
        issue_lines.append("\n".join(parts))

    sections: list[str] = [
        "\n".join([
            "1. 핵심 검수 요약",
            summary or "구체적인 문화권 리스크나 현지화 문제는 확인되지 않았습니다.",
            f"권장 조치: {sev_title}",
            sev_desc,
        ]),
        "\n".join([
            "2. 문제 구간 및 제안",
            "\n\n".join(issue_lines) if issue_lines else "구간 단위로 보고된 문제는 없습니다.",
        ]),
        "\n".join([
            "3. 문체/현지화 전략",
            rationale or "문체와 현지화 전략은 대상 국가 독자 기준으로 자연스러운지 살펴보세요.",
            "이 항목은 문장 호흡, 어휘 선택, 문화적 완곡함을 함께 보는 용도입니다.",
        ]),
    ]

    if top_severity:
        sections[0] += f"\n심각도: {top_severity}"

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
    locale = COUNTRY_TO_LOCALE.get(country)
    if not locale:
        raise ValueError(f"unsupported targetCountry: {country}")
    config = _config(locale)
    terminology = payload.get("terminology") or payload.get("terms") or payload.get("glossary") or []
    terminology_candidates = extract_noun_terminology_candidates(source_text)
    active_terminology = merge_terminology(terminology, terminology_candidates)
    terminology_context = render_terminology_context(active_terminology, locale, source_text=source_text)
    retrieval_queries: list[str] = []
    if work_id is not None:
        work_id_int = int(work_id)
        work = work_get(work_id_int)
        if not work:
            raise ValueError(f"work {work_id_int} not found")
        if episode_id is not None and not _get_episode(work_id_int, int(episode_id)):
            raise ValueError(f"episode {episode_id} not found for work {work_id_int}")
    workflow = TranslationPipeline(config).run_with_inspection(
        source_text,
        translation_memory=[],
        memory_context=terminology_context,
        retrieval_queries=retrieval_queries,
        context_extraction={"terminologyCandidates": terminology_candidates} if terminology_candidates else None,
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
        terminology=terminology,
    )
    data["consistency"] = consistency
    data["terminology_context"] = terminology_context
    review_summary = format_review_summary(data)
    saved_version: dict[str, Any] | None = None
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
            memory={"terms": active_terminology} if active_terminology else None,
        )
    return {
        "country": country,
        "locale": locale,
        "finalTranslation": final_translation,
        "reviewSummary": review_summary,
        "retrievalCount": len(data.get("retrievals", [])),
        "workflow": data,
        "terminologyCandidates": terminology_candidates,
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
