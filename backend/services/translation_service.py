"""Translation and inspector chat services."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from typing import Any

from app.translation import (
    ChatMessage,
    DEFAULT_QUALITY_MODE,
    PipelineConfig,
    TranslationMode,
    TranslationPipeline,
)
from app.translation.locale_utils import (
    LocaleNormalizationError,
    TARGET_COUNTRY_TO_LOCALE,
    TARGET_LOCALE_TO_COUNTRY,
    normalize_target_fields,
)
from app.translation.infra.runtime import is_mock_mode
from app.translation.text_processing.consistency_checker import check_translation_consistency
from app.translation.text_processing.korean_output import is_korean_source
from backend.services.glossary_service import capture_candidates_from_v3_result, hydrate_work_memory
from backend.services.content_service import get_content_repository
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


def _delivery_block_message(delivery_status: str) -> str:
    if delivery_status == "blocked_translation_safety":
        return "Translation safety validation failed. Please try again."
    if delivery_status == "blocked_translation_integrity":
        return "Translation target-language integrity validation failed. Please try again."
    return ""


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
        normalized_delivery_status = "blocked_translation_integrity"
        normalized_error_code = "translation_integrity_failed"

    if normalized_delivery_status == "blocked_translation_safety":
        normalized_translation = ""
        normalized_error_code = "translation_safety_failed"
    elif normalized_delivery_status == "blocked_translation_integrity":
        normalized_translation = ""
        normalized_error_code = "translation_integrity_failed"

    if normalized_delivery_status != "deliverable":
        normalized_metadata["delivery_status"] = normalized_delivery_status
        normalized_metadata["user_visible_error_code"] = normalized_error_code

    return normalized_translation, normalized_delivery_status, normalized_error_code, normalized_metadata


def _blocked_response(
    *,
    country: str,
    locale: str,
    source_text: str,
    block_reason: str,
    mode: str = TranslationMode.V3_LITERARY_PACKAGE.value,
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


def _locale_error(exc: LocaleNormalizationError) -> dict[str, Any]:
    return {
        "ok": False,
        "status": 400,
        "errorCode": exc.error_code,
        "message": exc.message,
    }


def _wants_translation_persistence(payload: dict[str, Any]) -> bool:
    return bool(payload.get("saveTranslationResult") or payload.get("save_translation_result"))


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None


def _attach_translation_persistence(
    response: dict[str, Any],
    *,
    payload: dict[str, Any],
    source_text: str,
    country: str,
    locale: str,
    mode: TranslationMode,
) -> dict[str, Any]:
    if not _wants_translation_persistence(payload):
        return response
    metadata = dict(response.get("metadata") or {})
    internal = dict(response.get("internal") or {})
    delivery_status = str(response.get("deliveryStatus") or metadata.get("delivery_status") or "deliverable")
    if delivery_status.startswith("blocked_translation_"):
        internal["translationPersistence"] = {
            "enabled": True,
            "saved": False,
            "skipped": True,
            "reason": delivery_status,
        }
        response["internal"] = internal
        response["metadata"] = metadata
        return response
    work_id = _safe_int(_payload_value(payload, "workId", "work_id"))
    episode_id = _safe_int(_payload_value(payload, "episodeId", "episode_id"))
    if work_id is None or episode_id is None:
        internal["translationPersistence"] = {
            "enabled": True,
            "saved": False,
            "error": "missing_numeric_work_or_episode_id",
        }
        response["internal"] = internal
        response["metadata"] = metadata
        return response
    try:
        saved = get_content_repository().save_translation_result(
            {
                "work_id": work_id,
                "episode_id": episode_id,
                "target_country": country,
                "target_locale": locale,
                "pipeline": response.get("pipeline") or mode.value,
                "delivery_status": delivery_status,
                "translated_text": response.get("finalTranslation") or "",
                "translation_rationale": response.get("translationRationale"),
                "qa_issues": response.get("qaIssues") or response.get("qaReport"),
                "author_review_cards": response.get("authorReviewCards"),
                "metadata": metadata,
                "internal": internal,
                "model_name": metadata.get("model_name") or metadata.get("translation_model"),
                "source_text_hash": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
            }
        )
        saved_id = saved.get("translation_id")
        metadata["translationPersisted"] = True
        metadata["savedTranslationId"] = saved_id
        internal["translationPersistence"] = {"enabled": True, "saved": True, "savedTranslationId": saved_id}
        response["savedTranslationId"] = saved_id
    except Exception as exc:
        internal["translationPersistence"] = {
            "enabled": True,
            "saved": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    response["metadata"] = metadata
    response["internal"] = internal
    return response


COUNTRY_TO_LOCALE = dict(TARGET_COUNTRY_TO_LOCALE)
LOCALE_TO_COUNTRY = dict(TARGET_LOCALE_TO_COUNTRY)


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


def _payload_value(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _json_context(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(value)


def _chat_reference_from_legacy_retrieval(row: dict[str, Any]) -> dict[str, Any]:
    item = row.get("item") or {}
    return {
        "id": item.get("id"),
        "ko_anchor_expression": item.get("ko_anchor_expression", []),
        "target_expression": item.get("expression", ""),
        "score": row.get("score"),
    }


def _chat_reference_from_v3_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id") or row.get("noteId") or row.get("source") or row.get("sourceSpan"),
        "source": row.get("source") or row.get("sourceSpan") or row.get("term_ko") or row.get("text") or "",
        "target": row.get("target") or row.get("targetSpan") or row.get("expression") or "",
        "note": row.get("note") or row.get("explanation") or row.get("meaning") or "",
        "category": row.get("category") or row.get("type") or "",
    }


def _chat_used_references(workflow: dict[str, Any], internal: dict[str, Any]) -> list[dict[str, Any]]:
    rows = internal.get("idiomNotes") or internal.get("ragPackets") or workflow.get("retrievals") or []
    used_references: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if isinstance(row.get("item"), dict):
            used_references.append(_chat_reference_from_legacy_retrieval(row))
        else:
            used_references.append(_chat_reference_from_v3_row(row))
    return used_references


def _chat_inspection_report(workflow: dict[str, Any], internal: dict[str, Any]) -> dict[str, Any]:
    if internal:
        return {
            "reviewFindings": internal.get("reviewFindings") or [],
            "aggregateReview": internal.get("aggregateReview") or {},
            "qaIssues": workflow.get("qaIssues") or [],
        }
    return workflow.get("inspection") or {}


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
    source_text = str(_payload_value(payload, "sourceText", "source_text", default="") or "").strip()
    requested_work_id = _payload_value(payload, "workId", "work_id")
    canonical_work_key = _payload_value(payload, "canonicalWorkKey", "canonical_work_key")
    episode_id = _payload_value(payload, "episodeId", "episode_id")
    mode = TranslationMode(
        _payload_value(payload, "mode", "pipeline", default=TranslationMode.V3_LITERARY_PACKAGE.value)
    )
    work_id = requested_work_id if requested_work_id is not None else (canonical_work_key if mode is TranslationMode.V3_LITERARY_PACKAGE else None)
    try:
        normalized_target = normalize_target_fields(payload)
    except LocaleNormalizationError as exc:
        return _locale_error(exc)
    country = normalized_target["targetCountry"]
    locale = normalized_target["targetLocale"]
    if not source_text:
        raise ValueError("sourceText is required")
    quality_mode = payload.get("qualityMode") or DEFAULT_QUALITY_MODE
    model_override = payload.get("translationModel") or payload.get("model")
    if work_id is not None and mode is not TranslationMode.V3_LITERARY_PACKAGE:
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
        response = {
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
        return response

    pipeline = _pipeline_for_mode(locale, mode, quality_mode=quality_mode, model_override=model_override)
    if mode is TranslationMode.DIRECT_ONLY:
        direct = asdict(pipeline.run_direct_only(source_text))
        final_translation = direct.get("final_translation", "")
        delivery_status = direct.get("delivery_status", "deliverable")
        user_visible_error_code = direct.get("user_visible_error_code")
        message = ""
        if delivery_status == "blocked_translation_safety":
            final_translation = ""
        message = _delivery_block_message(delivery_status)
        final_translation, delivery_status, user_visible_error_code, metadata = _normalize_translation_delivery_contract(
            final_translation=final_translation,
            delivery_status=delivery_status,
            user_visible_error_code=user_visible_error_code,
            metadata=direct.get("metadata", {}),
        )
        message = _delivery_block_message(delivery_status)
        direct["metadata"] = metadata
        direct["delivery_status"] = delivery_status
        direct["user_visible_error_code"] = user_visible_error_code
        direct["final_translation"] = final_translation
        response = {
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
        return _attach_translation_persistence(
            response,
            payload=payload,
            source_text=source_text,
            country=country,
            locale=locale,
            mode=mode,
        )

    if mode is TranslationMode.V2_DUAL_DRAFT_REVIEW:
        result = asdict(pipeline.run_v2_dual_draft_review(source_text))
        final_translation = result.get("final_translation", "")
        delivery_status = result.get("delivery_status", "deliverable")
        user_visible_error_code = result.get("user_visible_error_code")
        message = ""
        final_translation, delivery_status, user_visible_error_code, metadata = _normalize_translation_delivery_contract(
            final_translation=final_translation,
            delivery_status=delivery_status,
            user_visible_error_code=user_visible_error_code,
            metadata=result.get("metadata", {}),
        )
        message = _delivery_block_message(delivery_status)
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
            "meaningDraft": result.get("meaning_draft", {}),
            "ragEvidence": result.get("rag_evidence", []),
            "translationDecisions": result.get("translation_decisions", []),
            "authorReviewCards": result.get("author_review_cards", []),
            "riskItems": [],
            "userVisibleRiskItems": [],
            "hiddenRiskItems": [],
            "qaReport": [],
            "userVisibleQaReport": {},
            "hiddenQaReport": [],
            "patchSuggestions": [],
            "metadata": metadata,
            "deliveryStatus": delivery_status,
            "userVisibleErrorCode": user_visible_error_code,
            "message": message,
            "memory": None,
            "translationVersion": None,
        }

    if mode is TranslationMode.V3_LITERARY_PACKAGE:
        genre = payload.get("genre") or payload.get("workGenre") or "Modern Korean web novel"
        max_iterations = int(payload.get("maxIterations") or 2)
        request_work_memory = payload.get("workMemory") or payload.get("work_memory")
        work_memory = request_work_memory if isinstance(request_work_memory, dict) else None
        work_memory_source = "request_payload" if work_memory is not None else "none"
        work_memory_fallback_reason = ""
        if work_memory is None and work_id is not None and locale:
            try:
                hydrated = hydrate_work_memory(str(work_id), locale)
                if hydrated is not None and hydrated.approvedGlossary:
                    work_memory = hydrated
                    work_memory_source = "rdb_hydrated"
                else:
                    work_memory_source = "none"
                    work_memory_fallback_reason = "no_approved_glossary"
            except Exception as exc:  # keep translation deliverable if glossary storage is unavailable
                work_memory = None
                work_memory_source = "none"
                work_memory_fallback_reason = f"glossary_hydration_failed:{type(exc).__name__}"
        result = asdict(
            pipeline.run_v3_literary_package(
                source_text,
                genre=genre,
                work_memory=work_memory,
                max_iterations=max_iterations,
                debug_capture_model_outputs=bool(
                    payload.get("debugCaptureModelOutputs")
                    or payload.get("debug_capture_model_outputs")
                    or os.environ.get("TRANSLATION_DEBUG_CAPTURE_MODEL_OUTPUTS") == "1"
                ),
                debug_artifact_dir=payload.get("debugArtifactDir") or payload.get("debug_artifact_dir"),
            )
        )
        capture_enabled = bool(payload.get("captureGlossaryCandidates") or payload.get("capture_glossary_candidates"))
        capture_summary: dict[str, Any]
        capture_target_locale = locale
        if not capture_enabled:
            capture_summary = {"enabled": False, "reason": "disabled"}
        elif work_id is None:
            capture_summary = {"enabled": False, "reason": "missing_work_id"}
        elif not capture_target_locale:
            capture_summary = {"enabled": False, "reason": "missing_target_locale"}
        else:
            try:
                capture_summary = capture_candidates_from_v3_result(
                    result,
                    work_id=str(work_id),
                    episode_id=str(episode_id) if episode_id is not None else None,
                    target_locale=capture_target_locale,
                )
            except Exception as exc:
                capture_summary = {
                    "enabled": True,
                    "error": f"candidate_capture_failed:{type(exc).__name__}",
                    "collectedCount": 0,
                    "savedCount": 0,
                    "skippedCount": 0,
                    "skippedReasons": {},
                }
        final_translation = result.get("finalTranslation", "")
        delivery_status = result.get("deliveryStatus", "deliverable")
        user_visible_error_code = (result.get("internal") or {}).get("userVisibleErrorCode")
        final_translation, delivery_status, user_visible_error_code, metadata = _normalize_translation_delivery_contract(
            final_translation=final_translation,
            delivery_status=delivery_status,
            user_visible_error_code=user_visible_error_code,
            metadata={
                "mode": TranslationMode.V3_LITERARY_PACKAGE.value,
                "pipeline": result.get("pipeline"),
                "delivery_status": delivery_status,
                "idiom_note_count": len(((result.get("internal") or {}).get("idiomNotes") or [])),
                "qa_issue_count": len(result.get("qaIssues") or []),
                "translation_rationale_item_count": len((result.get("translationRationale") or {}).get("items") or []),
                "work_memory_glossary_count": len(((result.get("internal") or {}).get("workMemory") or {}).get("approvedGlossary") or []),
                "work_memory_source": work_memory_source,
                "work_memory_fallback_reason": work_memory_fallback_reason,
            },
        )
        result["finalTranslation"] = final_translation
        result["deliveryStatus"] = delivery_status
        internal = dict(result.get("internal") or {})
        internal["userVisibleErrorCode"] = user_visible_error_code
        internal["workMemorySource"] = work_memory_source
        internal["workMemoryFallbackReason"] = work_memory_fallback_reason
        internal["workMemoryGlossaryCount"] = len((internal.get("workMemory") or {}).get("approvedGlossary") or [])
        internal["glossaryCandidateCapture"] = capture_summary
        result["internal"] = internal
        response = {
            "country": country,
            "locale": locale,
            "mode": mode.value,
            "pipeline": result.get("pipeline"),
            "finalTranslation": final_translation,
            "reviewSummary": "",
            "translationRationale": result.get("translationRationale", {}),
            "readerEndnotes": result.get("readerEndnotes", []),
            "retrievalCount": 0,
            "workflow": result,
            "meaningDraft": {},
            "ragEvidence": [],
            "translationDecisions": [],
            "authorReviewCards": result.get("authorReviewCards", []),
            "riskItems": [],
            "userVisibleRiskItems": [],
            "hiddenRiskItems": [],
            "qaReport": result.get("qaIssues", []),
            "qaIssues": result.get("qaIssues", []),
            "userVisibleQaReport": {},
            "hiddenQaReport": [],
            "patchSuggestions": [],
            "metadata": metadata,
            "deliveryStatus": delivery_status,
            "userVisibleErrorCode": user_visible_error_code,
            "message": "",
            "internal": result.get("internal", {}),
            "memory": None,
            "translationVersion": None,
        }
        return _attach_translation_persistence(
            response,
            payload=payload,
            source_text=source_text,
            country=country,
            locale=locale,
            mode=mode,
        )

    if mode is TranslationMode.V2_DIRECT_QA:
        result = asdict(pipeline.run_v2_direct_qa(source_text))
        final_translation = result.get("final_translation", "")
        delivery_status = result.get("delivery_status", "deliverable")
        user_visible_error_code = result.get("user_visible_error_code")
        message = ""
        if delivery_status == "blocked_translation_safety":
            final_translation = ""
        message = _delivery_block_message(delivery_status)
        final_translation, delivery_status, user_visible_error_code, metadata = _normalize_translation_delivery_contract(
            final_translation=final_translation,
            delivery_status=delivery_status,
            user_visible_error_code=user_visible_error_code,
            metadata=result.get("metadata", {}),
        )
        message = _delivery_block_message(delivery_status)
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
    message = _delivery_block_message(delivery_status)
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
    question = str(_payload_value(payload, "question", "question_text", default="") or "").strip()
    source_text = str(_payload_value(payload, "sourceText", "source_text", default="") or "").strip()
    current_translation = str(_payload_value(payload, "currentTranslation", "current_translation", default="") or "").strip()
    workflow = payload.get("workflow") or {}
    chat_history_payload = payload.get("chatHistory") or []

    try:
        normalized_target = normalize_target_fields(payload)
    except LocaleNormalizationError as exc:
        return _locale_error(exc)
    country = normalized_target["targetCountry"]
    if not question:
        raise ValueError("question is required")
    locale = normalized_target["targetLocale"]

    draft = workflow.get("draft") or {}
    internal = workflow.get("internal") or {}
    reviewed_translation = (
        current_translation
        or workflow.get("finalTranslation")
        or workflow.get("reviewed_translation")
        or draft.get("translation")
        or ""
    )
    source_text = source_text or workflow.get("source_text") or ""
    translation_rationale = _json_context(workflow.get("translationRationale") or draft.get("rationale") or "")
    inspection_report = _chat_inspection_report(workflow, internal)
    used_references = _chat_used_references(workflow, internal)
    reader_endnotes = workflow.get("readerEndnotes") or []
    work_title = str(workflow.get("title") or _payload_value(payload, "title", "work_title", default="") or "")
    episode_id = str(_payload_value(payload, "episodeId", "episode_id", default=workflow.get("episodeId") or workflow.get("episode_id") or "") or "")

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
        translation_rationale=translation_rationale,
        used_references=used_references,
        inspection_report=inspection_report,
        reader_endnotes=reader_endnotes,
        work_title=work_title,
        episode_id=episode_id,
        translation_memory=[],
        chat_history=chat_history,
    )

    return {
        "answer": reply.answer,
        "proposedTranslation": reply.proposed_translation,
        "changeSummary": reply.change_summary,
        "needsUserConfirmation": reply.needs_user_confirmation,
    }
