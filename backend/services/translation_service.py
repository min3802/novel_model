"""Translation, memory extraction, and inspector chat services."""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from ko_locale_pipeline import ChatMessage, KoLocalePipeline, PipelineConfig
from ko_locale_pipeline.consistency_checker import check_translation_consistency
from ko_locale_pipeline.context_extractor import ContextExtractor
from ko_locale_pipeline.ontology import (
    compact_memory_context,
    extract_named_entity_glossary_candidates,
    load_memory,
    merge_extraction,
    render_glossary_context,
    save_memory,
    upsert_glossary_candidates,
)
from backend.store.memory_store import _get_episode, save_translation_version, work_get

COUNTRY_TO_LOCALE = {
    "일본": "ko_ja",
    "미국": "ko_en_us",
    "중국": "ko_zh_cn",
    "태국": "ko_th_th",
}


def _pipeline(locale: str) -> KoLocalePipeline:
    mock = os.getenv("WLIGHTER_MOCK_MODE", "true").lower() in {"1", "true", "yes", "y"}
    return KoLocalePipeline(PipelineConfig(locale=locale, mock=mock, top_k=3))


def _config(locale: str) -> PipelineConfig:
    mock = os.getenv("WLIGHTER_MOCK_MODE", "true").lower() in {"1", "true", "yes", "y"}
    return PipelineConfig(locale=locale, mock=mock, top_k=3)


def _is_mock_mode() -> bool:
    return os.getenv("WLIGHTER_MOCK_MODE", "true").lower() in {"1", "true", "yes", "y"}


def _contains_hangul(text: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in text)


def work_memory_get(work_id: int) -> dict[str, Any]:
    work = work_get(work_id)
    if not work:
        raise ValueError(f"work {work_id} not found")
    return load_memory(work_id, title=work.get("title", ""))


def work_memory_update(work_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    work = work_get(work_id)
    if not work:
        raise ValueError(f"work {work_id} not found")
    memory = payload.get("memory") if isinstance(payload.get("memory"), dict) else payload
    memory = dict(memory or {})
    memory["workId"] = work_id
    memory.setdefault("title", work.get("title", ""))
    return save_memory(memory)


def work_memory_extract(work_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    work = work_get(work_id)
    if not work:
        raise ValueError(f"work {work_id} not found")
    country = payload.get("targetCountry") or "일본"
    locale = COUNTRY_TO_LOCALE.get(country)
    if not locale:
        raise ValueError(f"unsupported targetCountry: {country}")
    source_text = (payload.get("sourceText") or payload.get("body") or "").strip()
    if not source_text:
        raise ValueError("sourceText is required")

    config = _config(locale)
    memory = load_memory(work_id, title=work.get("title", ""))
    memory_context = compact_memory_context(memory)
    extraction = ContextExtractor(config).extract(source_text, existing_memory_context=memory_context)
    merged = merge_extraction(memory, extraction.to_dict())
    glossary_candidates = extract_named_entity_glossary_candidates(source_text)
    merged = upsert_glossary_candidates(merged, glossary_candidates)
    saved = save_memory(merged)
    memory_context = compact_memory_context(saved)
    glossary_context = render_glossary_context(saved, locale, source_text=source_text)
    return {
        "workId": work_id,
        "country": country,
        "locale": locale,
        "extraction": extraction.to_dict(),
        "glossaryCandidates": glossary_candidates,
        "memory": saved,
        "memoryContext": "\n\n".join(part for part in [memory_context, glossary_context] if part),
    }


ACTION_LABELS = {
    "ALLOW": ("통과", "현재 번역을 그대로 사용해도 큰 문제가 없습니다."),
    "NOTE": ("참고", "큰 수정은 필요 없지만, 검수 메모를 참고해 표현을 확인하세요."),
    "FLAG": ("주의", "문화권/표현 리스크가 있어 사람이 한 번 더 확인하는 것이 좋습니다."),
    "ADAPT": ("현지화 조정 권장", "의미는 유지하되 대상 국가 독자에게 더 자연스럽도록 표현을 다듬는 것이 좋습니다."),
    "REWRITE": ("재작성 권장", "문장 의미나 문화권 적합성 문제가 커서 번역을 다시 구성하는 것이 좋습니다."),
}


def _clean_summary_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def format_review_summary(workflow: dict[str, Any]) -> str:
    translation_review = workflow.get("translation_review", {}) or {}
    inspection = workflow.get("inspection", {}) or {}
    draft = workflow.get("draft", {}) or {}
    translation_risk = _clean_summary_text(translation_review.get("risk_summary"))
    inspection_risk = _clean_summary_text(inspection.get("risk_summary"))
    translation_note = _clean_summary_text(translation_review.get("review_note"))
    inspection_note = _clean_summary_text(inspection.get("review_note"))
    rationale = _clean_summary_text(draft.get("rationale"))
    action_code = _clean_summary_text(
        inspection.get("recommended_action") or translation_review.get("recommended_action")
    ).upper()
    action_title, action_desc = ACTION_LABELS.get(
        action_code,
        (action_code or "검토 필요", "검수 결과를 기준으로 표현을 한 번 더 확인하세요."),
    )

    sections: list[str] = [
        "\n".join([
            "1. 핵심 번역 판단",
            translation_risk or "번역 결과는 검토 가능하지만, 핵심 판단을 다시 한 번 확인해보세요.",
            f"권장 조치: {action_title}",
            action_desc,
        ]),
        "\n".join([
            "2. 문화권 유의사항",
            inspection_risk or "문화권 특이사항이 많지 않지만, 문맥에 따라 표현을 다시 확인해볼 수 있습니다.",
            inspection_note or "검수 코멘트는 별도로 남지 않았습니다.",
        ]),
        "\n".join([
            "3. 고유명사/표현",
            translation_note or "고유명사·관용구·표현 일관성을 한 번 더 점검해보세요.",
            _clean_summary_text(inspection.get("review_note")) if inspection_note else "표현 관련 추가 메모가 없습니다.",
        ]),
        "\n".join([
            "4. 문체/현지화 전략",
            rationale or "문체와 현지화 전략은 대상 국가 독자 기준으로 자연스러운지 살펴보세요.",
            "이 항목은 문장 호흡, 어휘 선택, 문화적 완곡함을 함께 보는 용도입니다.",
        ]),
    ]

    if action_code:
        sections[0] += f"\n코드: {action_code}"

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
    if not _contains_hangul(source_text):
        message = "현재 한국어 원문만 지원하고 있어요. 한국어로 작성된 원문을 입력해 주세요."
        return {
            "country": country,
            "locale": locale,
            "finalTranslation": message,
            "reviewSummary": "입력 언어 확인이 필요합니다.",
            "retrievalCount": 0,
            "workflow": {
                "source_text": source_text,
                "retrievals": [],
                "cultural_matches": [],
                "annotation_matches": [],
                "draft": {"translation": message, "strategy": "unsupported-source-language"},
                "translation_review": {},
                "inspection": {
                    "recommended_action": "BLOCK",
                    "risk_summary": "한국어 원문이 아닌 입력은 번역 모델 테스트 대상에서 제외됩니다.",
                },
                "reviewed_translation": message,
            },
            "memory": None,
        }
    config = _config(locale)
    memory_context = ""
    extraction_payload: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    retrieval_queries: list[str] = []
    if work_id is not None:
        work_id_int = int(work_id)
        work = work_get(work_id_int)
        if not work:
            raise ValueError(f"work {work_id_int} not found")
        if episode_id is not None and not _get_episode(work_id_int, int(episode_id)):
            raise ValueError(f"episode {episode_id} not found for work {work_id_int}")
        memory = load_memory(work_id_int, title=work.get("title", ""))
        memory_context = compact_memory_context(memory)
        extraction = ContextExtractor(config).extract(source_text, existing_memory_context=memory_context)
        extraction_payload = extraction.to_dict()
        retrieval_queries = extraction.ragQueries
        merged_memory = merge_extraction(memory, extraction_payload)
        glossary_candidates = extract_named_entity_glossary_candidates(source_text)
        merged_memory = upsert_glossary_candidates(merged_memory, glossary_candidates)
        memory = save_memory(merged_memory)
        base_memory_context = compact_memory_context(memory)
        glossary_context = render_glossary_context(memory, locale, source_text=source_text)
        memory_context = "\n\n".join(part for part in [base_memory_context, glossary_context] if part)
        if extraction_payload is not None:
            extraction_payload = dict(extraction_payload)
            extraction_payload["glossaryCandidates"] = glossary_candidates
    workflow = KoLocalePipeline(config).run_with_inspection(
        source_text,
        translation_memory=[],
        memory_context=memory_context,
        retrieval_queries=retrieval_queries,
        context_extraction=extraction_payload,
    )
    data = asdict(workflow)
    final_translation = data.get("reviewed_translation", "")
    consistency = check_translation_consistency(
        source_text=source_text,
        translated_text=final_translation,
        locale=locale,
        memory=memory,
    )
    data["consistency"] = consistency
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
            memory=memory,
        )
    return {
        "country": country,
        "locale": locale,
        "finalTranslation": final_translation,
        "reviewSummary": review_summary,
        "retrievalCount": len(data.get("retrievals", [])),
        "workflow": data,
        "memory": memory,
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
    translation_review = workflow.get("translation_review") or {}
    inspection = workflow.get("inspection") or {}
    retrievals = workflow.get("retrievals") or []
    reviewed_translation = (
        current_translation
        or workflow.get("reviewed_translation")
        or translation_review.get("revised_translation")
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
