"""Translation and inspector chat services."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.translation import (
    ChatMessage,
    DEFAULT_QUALITY_MODE,
    PipelineConfig,
    TranslationMode,
    TranslationPipeline,
)
from app.translation.infra.country_locale import COUNTRY_TO_LOCALE, resolve_locale_for_country
from app.translation.infra.runtime import is_mock_mode
from app.translation.text_processing.consistency_checker import check_translation_consistency
from app.translation.text_processing.korean_output import is_korean_source
from backend.store.memory_store import _get_episode, save_translation_version, work_get


def _pipeline(locale: str) -> TranslationPipeline:
    return TranslationPipeline(PipelineConfig(locale=locale, mock=is_mock_mode()))


def _pipeline_for_mode(
    locale: str,
    mode: TranslationMode,
    *,
    quality_mode: str = DEFAULT_QUALITY_MODE,
    model_override: str | None = None,
) -> TranslationPipeline:
    return TranslationPipeline(
        PipelineConfig(
            locale=locale,
            mode=mode,
            mock=is_mock_mode(),
            quality_mode=quality_mode,
            model_override=model_override,
        )
    )


BLOCK_MESSAGES = {
    "non_korean_source": {
        "finalTranslation": "현재 한국어 원문만 지원하고 있어요. 한국어로 작성된 원문을 입력해 주세요.",
        "reviewSummary": "입력 언어 확인이 필요합니다.",
        "summary": "한국어 원문이 아닌 입력은 번역 모델 테스트 대상에서 제외됩니다.",
    },
}

_DEFAULT_BLOCK = {
    "finalTranslation": "입력을 처리할 수 없어요. 입력 내용을 다시 확인해 주세요.",
    "reviewSummary": "입력 확인이 필요합니다.",
    "summary": "입력이 번역 모델 처리 대상으로 보이지 않습니다.",
}


def _normalize_translation_delivery_contract(
    *,
    final_translation: str,
    delivery_status: str,
    user_visible_error_code: str | None,
    metadata: dict[str, Any],
) -> tuple[str, str, str | None, dict[str, Any]]:
    normalized_metadata = dict(metadata or {})
    normalized_translation = final_translation
    normalized_delivery_status = delivery_status
    normalized_error_code = user_visible_error_code

    if normalized_delivery_status == "deliverable" and not normalized_translation.strip():
        normalized_translation = ""
        normalized_delivery_status = "blocked_translation_safety"
        normalized_error_code = "translation_safety_failed"

    if normalized_delivery_status == "blocked_translation_safety":
        normalized_translation = ""
        normalized_error_code = "translation_safety_failed"

    if normalized_delivery_status != "deliverable":
        normalized_metadata["delivery_status"] = normalized_delivery_status
        normalized_metadata["user_visible_error_code"] = normalized_error_code

    return normalized_translation, normalized_delivery_status, normalized_error_code, normalized_metadata


def _blocked_response(
    *, country: str, locale: str, source_text: str, block_reason: str, mode: str = TranslationMode.LEGACY_FULL.value
) -> dict[str, Any]:
    messages = BLOCK_MESSAGES.get(block_reason, _DEFAULT_BLOCK)
    message = messages["finalTranslation"]
    return {
        "country": country,
        "locale": locale,
        "mode": mode,
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
    "LOW": ("낮음", "의미 전달에는 큰 문제가 없지만, 표현을 조금 더 다듬으면 더 자연스러워질 수 있습니다."),
    "MEDIUM": ("보통", "일부 표현이나 뉘앙스에 보완이 필요하며, 수정 여부를 검토할 가치가 있습니다."),
    "HIGH": ("높음", "의미·뉘앙스·문체 중 하나 이상에서 중요한 어긋남이 있어 우선적으로 확인이 필요합니다."),
    "CRITICAL": ("치명적", "핵심 의미가 손상되었거나 독자 이해를 방해할 정도의 문제가 있어 즉시 수정이 필요합니다."),
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
        ("미분류", "심각도 분류가 비어 있어도 핵심 쟁점과 수정 필요성은 검토할 수 있습니다."),
    )

    issue_lines: list[str] = []
    for idx, issue in enumerate(issues, start=1):
        sev = _clean_summary_text(issue.get("severity")).upper()
        problem = _clean_summary_text(issue.get("problem"))
        translated_span = _clean_summary_text(issue.get("translated_span"))
        suggested = _clean_summary_text(issue.get("suggested"))
        parts = [f"{idx}) [{sev or '미분류'}] {problem or '문제 설명이 제공되지 않았습니다.'}"]
        if translated_span:
            parts.append(f"   - 번역 구간: {translated_span}")
        if suggested:
            parts.append(f"   - 제안 표현: {suggested}")
        issue_lines.append("\n".join(parts))

    sections: list[str] = [
        "\n".join([
            "1. 전체 검토 요약",
            summary or "검토 요약이 비어 있지만, 세부 항목을 통해 필요한 수정 포인트를 확인할 수 있습니다.",
            f"최고 심각도: {sev_title}",
            sev_desc,
        ]),
        "\n".join([
            "2. 문제 번역 구간 및 제안",
            "\n\n".join(issue_lines) if issue_lines else "검토 대상 번역에서 별도 수정이 필요한 문제 구간은 발견되지 않았습니다.",
        ]),
        "\n".join([
            "3. 문체/현지화 전략",
            rationale or "번역 근거 설명이 제공되지 않아도, 문체와 현지화 방향은 결과 문장과 이슈 항목을 함께 보며 판단할 수 있습니다.",
            "고유명사 표기, 문화 맥락 처리, 인물 말투 유지 여부를 함께 점검해 주세요.",
        ]),
    ]

    if top_severity:
        sections[0] += f"\n원본 심각도 코드: {top_severity}"

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
    mode = TranslationMode(payload.get("mode") or TranslationMode.LEGACY_FULL.value)
    quality_mode = payload.get("qualityMode") or DEFAULT_QUALITY_MODE
    model_override = payload.get("translationModel") or payload.get("model")
    if work_id is not None:
        work_id_int = int(work_id)
        work = work_get(work_id_int)
        if not work:
            raise ValueError(f"work {work_id_int} not found")
        if episode_id is not None and not _get_episode(work_id_int, int(episode_id)):
            raise ValueError(f"episode {episode_id} not found for work {work_id_int}")
    if not is_korean_source(source_text):
        return _blocked_response(
            country=country,
            locale=locale,
            source_text=source_text,
            block_reason="non_korean_source",
            mode=mode.value,
        )

    if mode is TranslationMode.LEGACY_FULL:
        pipeline = _pipeline_for_mode(locale, mode, quality_mode=quality_mode, model_override=model_override)
        workflow = pipeline.run_with_inspection(
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
                mode=mode.value,
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
            "mode": mode.value,
            "finalTranslation": final_translation,
            "reviewSummary": review_summary,
            "retrievalCount": len(data.get("retrievals", [])),
            "workflow": data,
            "metadata": data.get("metadata", {}),
            "terminologyCandidates": data.get("terminology_candidates", []),
            "memory": None,
            "translationVersion": saved_version,
        }

    pipeline = _pipeline_for_mode(locale, mode, quality_mode=quality_mode, model_override=model_override)
    if mode is TranslationMode.DIRECT_ONLY:
        direct = asdict(pipeline.run_direct_only(source_text))
        final_translation = direct.get("final_translation", "")
        delivery_status = direct.get("delivery_status", "deliverable")
        user_visible_error_code = direct.get("user_visible_error_code")
        message = ""
        if delivery_status == "blocked_translation_safety":
            final_translation = ""
            message = "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요."
        final_translation, delivery_status, user_visible_error_code, metadata = _normalize_translation_delivery_contract(
            final_translation=final_translation,
            delivery_status=delivery_status,
            user_visible_error_code=user_visible_error_code,
            metadata=direct.get("metadata", {}),
        )
        if delivery_status == "blocked_translation_safety":
            message = "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요."
        direct["metadata"] = metadata
        direct["delivery_status"] = delivery_status
        direct["user_visible_error_code"] = user_visible_error_code
        direct["final_translation"] = final_translation
        return {
            "country": country,
            "locale": locale,
            "mode": mode.value,
            "finalTranslation": final_translation,
            "reviewSummary": "",
            "retrievalCount": 0,
            "workflow": direct,
            "terminologyCandidates": [],
            "riskItems": [],
            "qaReport": [],
            "patchSuggestions": [],
            "metadata": direct.get("metadata", {}),
            "deliveryStatus": delivery_status,
            "userVisibleErrorCode": user_visible_error_code,
            "message": message,
            "memory": None,
            "translationVersion": None,
        }

    if mode is TranslationMode.V2_DIRECT_QA:
        result = asdict(pipeline.run_v2_direct_qa(source_text))
        final_translation = result.get("final_translation", "")
        delivery_status = result.get("delivery_status", "deliverable")
        user_visible_error_code = result.get("user_visible_error_code")
        message = ""
        if delivery_status == "blocked_translation_safety":
            final_translation = ""
            message = "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요."
        final_translation, delivery_status, user_visible_error_code, metadata = _normalize_translation_delivery_contract(
            final_translation=final_translation,
            delivery_status=delivery_status,
            user_visible_error_code=user_visible_error_code,
            metadata=result.get("metadata", {}),
        )
        if delivery_status == "blocked_translation_safety":
            message = "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요."
        result["metadata"] = metadata
        result["delivery_status"] = delivery_status
        result["user_visible_error_code"] = user_visible_error_code
        result["final_translation"] = final_translation
        return {
            "country": country,
            "locale": locale,
            "mode": mode.value,
            "finalTranslation": final_translation,
            "reviewSummary": "",
            "retrievalCount": 0,
            "workflow": result,
            "riskItems": result.get("risk_items", []),
            "userVisibleRiskItems": result.get("user_visible_risk_items", []),
            "hiddenRiskItems": result.get("hidden_risk_items", []),
            "qaReport": result.get("qa_report", []),
            "userVisibleQaReport": result.get("user_visible_qa_report", {}),
            "hiddenQaReport": result.get("hidden_qa_report", []),
            "patchSuggestions": result.get("patch_suggestions", []),
            "metadata": result.get("metadata", {}),
            "deliveryStatus": delivery_status,
            "userVisibleErrorCode": user_visible_error_code,
            "message": message,
            "memory": None,
            "translationVersion": None,
        }

    translation_text = (
        (payload.get("currentTranslation") or "")
        or (payload.get("finalTranslation") or "")
        or (payload.get("translatedText") or "")
    ).strip()
    result = asdict(pipeline.run_qa_only(source_text, translation_text))
    final_translation, delivery_status, user_visible_error_code, metadata = _normalize_translation_delivery_contract(
        final_translation=result.get("final_translation", ""),
        delivery_status=result.get("delivery_status", "deliverable"),
        user_visible_error_code=result.get("user_visible_error_code"),
        metadata=result.get("metadata", {}),
    )
    if delivery_status == "blocked_translation_safety":
        message = "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요."
    else:
        message = ""
    result["metadata"] = metadata
    result["delivery_status"] = delivery_status
    result["user_visible_error_code"] = user_visible_error_code
    result["final_translation"] = final_translation
    return {
        "country": country,
        "locale": locale,
        "mode": mode.value,
        "finalTranslation": final_translation,
        "reviewSummary": "",
        "retrievalCount": 0,
        "workflow": result,
        "riskItems": result.get("risk_items", []),
        "userVisibleRiskItems": result.get("user_visible_risk_items", []),
        "hiddenRiskItems": result.get("hidden_risk_items", []),
        "qaReport": result.get("qa_report", []),
        "userVisibleQaReport": result.get("user_visible_qa_report", {}),
        "hiddenQaReport": result.get("hidden_qa_report", []),
        "patchSuggestions": result.get("patch_suggestions", []),
        "metadata": metadata,
        "deliveryStatus": delivery_status,
        "userVisibleErrorCode": user_visible_error_code,
        "message": message,
        "memory": None,
        "translationVersion": None,
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
