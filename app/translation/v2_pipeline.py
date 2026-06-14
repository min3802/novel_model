from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .agents.translator import TranslationDraft, Translator
from .config import PipelineConfig
from .retrieval.annotation_retriever import AnnotationRetriever, AnnotationResult
from .retrieval.retriever import IdiomRetriever, RetrievalResult, embed_query
from .text_processing.terminology import extract_noun_terminology_candidates

REQUIRED_EVALUATION_PHRASES = (
    "목청이 터져라",
    "다 잡은 고기를 놓치다",
    "노는 물",
    "발목을 잡다",
    "손을 놓다",
    "벼랑 끝에 몰리다",
    "눈물 쏙 빼놓다",
    "손에 쥐다",
)

_USER_VISIBLE_IDIOM_TYPES = {"idiom"}
_USER_REVIEW_TYPES = {"term", "entity", "culture"}
_HAND_GRASP_IDIOM_ANCHORS = {"손에 쥐다", "손에 넣다"}
_HAND_GRASP_ABSTRACT_KEYWORDS = (
    "승리",
    "기회",
    "우승",
    "우승컵",
    "계약",
    "주도권",
    "권력",
    "돈",
    "티켓",
    "성과",
    "패권",
    "왕좌",
    "트로피",
)
_HAND_GRASP_PHYSICAL_OBJECT_KEYWORDS = (
    "야구공",
    "휴대폰",
    "핸드폰",
    "물건",
    "종이",
    "가방",
    "컵",
    "공",
    "펜",
    "칼",
)
_HAND_GRASP_LITERAL_PATTERN = re.compile(
    r"(?P<object>야구공|휴대폰|핸드폰|물건|종이|가방|컵|공|펜|칼)"
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _split_paragraphs(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", text or "") if part.strip()]
    return parts or ([_clean(text)] if _clean(text) else [])


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", _clean(text)).casefold()


def _first_values(value: Any, *, limit: int = 3) -> list[str]:
    if isinstance(value, list):
        return [str(row).strip() for row in value if str(row).strip()][:limit]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _unique_preserve(values: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = _clean(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
        if limit is not None and len(output) >= limit:
            break
    return output


def _parse_target_candidates(*values: Any) -> list[str]:
    direct_candidates: list[str] = []
    for value in values:
        if isinstance(value, list):
            direct_candidates.extend(_first_values(value, limit=10))
        elif isinstance(value, str):
            compact = value.strip()
            if compact and "\n" not in compact and "후보:" not in compact and "candidate" not in compact.lower():
                direct_candidates.append(compact)
        text = _clean(value)
        if not text:
            continue
        for pattern in (
            r"일본어 후보\s*:\s*([^\n]+)",
            r"日本語候補\s*:\s*([^\n]+)",
            r"Japanese candidates?\s*:\s*([^\n]+)",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            segment = match.group(1).strip()
            pieces = [
                piece.strip()
                for piece in re.split(r"\s*/\s*|,\s*|·|•|\|", segment)
                if piece.strip()
            ]
            direct_candidates.extend(pieces)
    return _unique_preserve(direct_candidates, limit=5)


def _pick_anchor(item: dict[str, Any]) -> str:
    for candidate in (
        item.get("matched_phrase"),
        item.get("anchor"),
        *(_first_values(item.get("ko_anchor_expression"), limit=3)),
        *(_first_values(item.get("ko_expression"), limit=3)),
        item.get("keyword_ko"),
        item.get("keyword"),
    ):
        cleaned = _clean(candidate)
        if not cleaned:
            continue
        return cleaned.split("\n", 1)[0].strip()
    return ""


def _pick_source_span(item: dict[str, Any], anchor: str) -> str:
    for candidate in (
        item.get("evidence_chunk"),
        item.get("matched_sentence"),
        item.get("matched_context"),
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned

    for candidate in (
        item.get("source_text"),
        item.get("context_text"),
        item.get("embedding_text"),
    ):
        cleaned = _clean(candidate)
        if not cleaned:
            continue
        sentences = re.split(r"(?<=[.!?\n])\s+|(?<=다)\.\s*|(?<=[。！？])", cleaned)
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and (anchor and anchor in sentence):
                return sentence
        if anchor and anchor in cleaned:
            return cleaned
    return anchor


def _resolve_visibility(item: "RiskItem") -> tuple[bool, str]:
    if item.type in _USER_VISIBLE_IDIOM_TYPES and item.confidence == "high":
        return True, "확인 필요"
    return False, "내부 디버그"


def _is_hand_grasp_idiom_anchor(anchor: str) -> bool:
    normalized_anchor = _normalize_text(anchor)
    return any(normalized_anchor == _normalize_text(candidate) for candidate in _HAND_GRASP_IDIOM_ANCHORS)


def _extract_literal_hand_grasp_object(source_span: str) -> str:
    cleaned = _clean(source_span)
    if not cleaned:
        return ""
    match = _HAND_GRASP_LITERAL_PATTERN.search(cleaned)
    if not match:
        return ""
    return _clean(match.group("object"))


def apply_source_risk_visibility_filters(item: "RiskItem") -> "RiskItem":
    item.user_visible, item.visibility_bucket = _resolve_visibility(item)
    item.filter_reason = ""

    if item.type != "idiom" or not _is_hand_grasp_idiom_anchor(item.anchor):
        return item

    source_span = _clean(item.source_span)
    if any(keyword in source_span for keyword in _HAND_GRASP_ABSTRACT_KEYWORDS):
        return item

    literal_object = _extract_literal_hand_grasp_object(source_span)
    if not literal_object:
        return item

    item.user_visible = False
    item.visibility_bucket = "내부 디버그"
    item.filter_reason = (
        f"literal physical grasp context: object={literal_object}; "
        "hidden because matched idiom anchor is used as physical object holding"
    )
    return item


def _build_translation_windows(translation: str) -> list[str]:
    paragraphs = _split_paragraphs(translation)
    if paragraphs:
        return paragraphs
    cleaned = _clean(translation)
    return [cleaned] if cleaned else []


def _contains_explanatory_prefix(text: str) -> bool:
    return any(prefix in text for prefix in ("일본어 후보:", "한국어 기준 표현:", "사람의 처지나", "표현.", "가리키는 표현"))


@dataclass(slots=True)
class RiskItem:
    id: str
    type: str
    source_span: str
    anchor: str
    meaning_ko: str
    target_candidates: list[str] = field(default_factory=list)
    confidence: str = "low"
    policy: str = "check_after_translation"
    source: str = "rule"
    visibility_bucket: str = "내부 디버그"
    user_visible: bool = False
    debug_reason: str = ""
    filter_reason: str = ""


@dataclass(slots=True)
class QAItem:
    risk_item_id: str
    status: str
    source_span: str
    translation_evidence: str
    reason: str
    suggested_action: str
    target_candidates: list[str] = field(default_factory=list)
    review_bucket: str = "내부 디버그"
    user_message: str = ""
    user_visible: bool = False
    debug_reason: str = ""


@dataclass(slots=True)
class PatchSuggestion:
    risk_item_id: str
    source_span: str
    current_translation: str
    suggested_translation: str
    reason: str
    apply_mode: str = "manual"


@dataclass(slots=True)
class DirectTranslationResult:
    mode: str
    final_translation: str
    draft: dict[str, Any]
    metadata: dict[str, Any]
    delivery_status: str = "deliverable"
    user_visible_error_code: str | None = None


@dataclass(slots=True)
class V2TranslationResult:
    mode: str
    final_translation: str
    risk_items: list[dict[str, Any]]
    qa_report: list[dict[str, Any]]
    user_visible_risk_items: list[dict[str, Any]]
    hidden_risk_items: list[dict[str, Any]]
    user_visible_qa_report: dict[str, list[dict[str, Any]]]
    hidden_qa_report: list[dict[str, Any]]
    patch_suggestions: list[dict[str, Any]]
    metadata: dict[str, Any]
    draft: dict[str, Any] | None = None
    delivery_status: str = "deliverable"
    user_visible_error_code: str | None = None


class DirectTranslator:
    def __init__(self, translator: Translator):
        self.translator = translator

    def translate(
        self,
        source_text: str,
        *,
        strict_locale_retry: bool = False,
        retry_attempt: int = 0,
    ) -> TranslationDraft:
        return self.translator.translate(
            source_text,
            [],
            memory_context="",
            translation_profile=None,
            source_analysis=None,
            include_rag_context=False,
            strict_locale_retry=strict_locale_retry,
            retry_attempt=retry_attempt,
        )


class SourceSideAnalyzer:
    def __init__(
        self,
        config: PipelineConfig,
        *,
        idiom_retriever: IdiomRetriever,
        annotation_retriever: AnnotationRetriever,
    ) -> None:
        self.config = config
        self.idiom_retriever = idiom_retriever
        self.annotation_retriever = annotation_retriever

    def analyze(self, source_text: str) -> list[RiskItem]:
        query_chunks, query_vectors = embed_query(
            self.idiom_retriever.backend,
            self.idiom_retriever._chunk_query,
            source_text,
        )
        idiom_results = self.idiom_retriever.search(query_chunks, query_vectors)
        annotation_results = self.annotation_retriever.search(query_chunks, query_vectors)
        terminology_candidates = extract_noun_terminology_candidates(source_text)

        risk_items: list[RiskItem] = []
        seen: set[str] = set()

        for row in idiom_results:
            item = self._risk_from_idiom(row)
            if item.id not in seen:
                risk_items.append(item)
                seen.add(item.id)

        for row in annotation_results:
            item = self._risk_from_annotation(row)
            if item.id not in seen:
                risk_items.append(item)
                seen.add(item.id)

        for index, row in enumerate(terminology_candidates, start=1):
            item = self._risk_from_term(row, index=index)
            if item.id not in seen:
                risk_items.append(item)
                seen.add(item.id)

        return risk_items

    def _risk_from_idiom(self, row: RetrievalResult) -> RiskItem:
        item = row.item
        source_id = str(item.get("source_id") or item.get("id") or "idiom")
        anchor = _pick_anchor(item)
        source_span = _pick_source_span(item, anchor)
        candidates = _parse_target_candidates(
            item.get("target_candidates"),
            item.get("expression"),
            item.get("translation_candidates"),
            item.get("context_text"),
            item.get("metadata"),
        )
        confidence = "high" if row.final_score >= 0.75 else "medium" if row.final_score >= 0.6 else "low"
        risk = RiskItem(
            id=f"idiom:{source_id}",
            type="idiom",
            source_span=source_span if source_span and not _contains_explanatory_prefix(source_span) else anchor,
            anchor=anchor or source_span,
            meaning_ko=_clean(item.get("meaning") or item.get("context_text")),
            target_candidates=candidates,
            confidence=confidence,
            policy="check_after_translation",
            source="rag",
        )
        risk = apply_source_risk_visibility_filters(risk)
        risk.debug_reason = f"idiom score={row.final_score:.3f}"
        if risk.filter_reason:
            risk.debug_reason = f"{risk.debug_reason}; {risk.filter_reason}"
        return risk

    def _risk_from_annotation(self, row: AnnotationResult) -> RiskItem:
        item = row.item
        source_id = str(item.get("source_id") or item.get("id") or item.get("keyword_ko") or "annotation")
        keyword = _pick_anchor(item) or _clean(item.get("keyword_ko") or item.get("keyword"))
        risk = RiskItem(
            id=f"culture:{source_id}",
            type="culture",
            source_span=_pick_source_span(item, keyword) or keyword,
            anchor=keyword,
            meaning_ko=_clean(item.get("context_text")),
            target_candidates=_parse_target_candidates(item.get("context_text"), item.get("metadata")),
            confidence="high" if row.final_score >= 0.75 else "medium" if row.final_score >= 0.6 else "low",
            policy="check_after_translation",
            source="rag",
        )
        risk.user_visible, risk.visibility_bucket = _resolve_visibility(risk)
        risk.debug_reason = f"annotation score={row.final_score:.3f}"
        return risk

    def _risk_from_term(self, row: dict[str, Any], *, index: int) -> RiskItem:
        source = _clean(row.get("source"))
        term_type = _clean(row.get("type")) or "term"
        allowed = _parse_target_candidates(row.get("allowedTranslations"))
        target = _clean(row.get("target"))
        if target and target not in allowed:
            allowed = [target, *allowed][:3]
        risk = RiskItem(
            id=f"term:{index}:{source}",
            type="entity" if term_type.startswith("person") else "term",
            source_span=source,
            anchor=source,
            meaning_ko=_clean(row.get("notes") or row.get("type") or source),
            target_candidates=allowed,
            confidence="medium" if row.get("policy") == "locked" else "low",
            policy="check_after_translation",
            source="terminology",
        )
        risk.user_visible, risk.visibility_bucket = _resolve_visibility(risk)
        risk.debug_reason = f"terminology policy={_clean(row.get('policy')) or 'candidate'}"
        return risk


class PostTranslationQA:
    def evaluate(self, source_text: str, translation: str, risk_items: list[RiskItem]) -> list[QAItem]:
        paragraphs = _build_translation_windows(translation)
        normalized_translation = _normalize_text(translation)
        report: list[QAItem] = []

        for item in risk_items:
            evidence = ""
            if item.target_candidates:
                for candidate in item.target_candidates:
                    normalized_candidate = _normalize_text(candidate)
                    if normalized_candidate and normalized_candidate in normalized_translation:
                        evidence = candidate
                        break
                    if normalized_candidate:
                        for paragraph in paragraphs:
                            if normalized_candidate in _normalize_text(paragraph):
                                evidence = paragraph
                                break
                    if evidence:
                        break

            if item.filter_reason:
                status = "unchecked"
                reason = item.filter_reason
                user_message = "물리적 대상 파지 문맥으로 분류되어 내부 디버그용으로만 보관합니다."
                suggested_action = "none"
                review_bucket = "내부 디버그"
                user_visible = False
            elif evidence:
                status = "pass"
                reason = "target candidate found in translation"
                user_message = "번역 후보가 번역문에서 직접 확인됩니다."
                suggested_action = "none"
                review_bucket = "내부 디버그"
                user_visible = False
            elif item.type == "idiom" and item.confidence in {"high", "medium"}:
                status = "warn"
                reason = "high-priority source-side idiom needs manual confirmation"
                user_message = "원문에 관용 표현이 있습니다. 번역문에서 의미가 자연스럽게 반영됐는지 확인이 필요합니다."
                if item.target_candidates:
                    user_message += f" 직역하면 어색해질 수 있는 표현입니다. 번역 후보: {', '.join(item.target_candidates)}"
                suggested_action = "review"
                review_bucket = "확인 필요" if item.confidence == "high" else "검토 후보"
                user_visible = item.confidence == "high"
            elif item.type in {"entity", "term"} and item.target_candidates:
                status = "warn"
                reason = "term candidate was not found directly in translation output"
                user_message = f"원문의 용어 또는 고유명사 후보입니다. 표기 일관성을 확인해 주세요. 번역 후보: {', '.join(item.target_candidates)}"
                suggested_action = "review"
                review_bucket = "검토 후보"
                user_visible = item.confidence in {"high", "medium"}
            elif item.type == "culture" and item.confidence in {"high", "medium"}:
                status = "warn"
                reason = "culture note candidate was not verified in translation output"
                user_message = "원문에 문화 표현이 있습니다. 번역문에서 설명 없이도 자연스럽게 이해되는지 확인해 주세요."
                if item.target_candidates:
                    user_message += f" 번역 후보: {', '.join(item.target_candidates)}"
                suggested_action = "review"
                review_bucket = "검토 후보"
                user_visible = item.confidence == "high"
            else:
                status = "unchecked"
                reason = "no reliable target-side heuristic for this risk item yet"
                user_message = "자동 판정 근거가 부족해 내부 검토용으로만 보관합니다."
                suggested_action = "review"
                review_bucket = "내부 디버그"
                user_visible = False

            report.append(
                QAItem(
                    risk_item_id=item.id,
                    status=status,
                    source_span=item.source_span,
                    translation_evidence=evidence,
                    reason=reason,
                    suggested_action=suggested_action,
                    target_candidates=item.target_candidates,
                    review_bucket=review_bucket,
                    user_message=user_message,
                    user_visible=user_visible,
                    debug_reason=f"{reason}; source={item.source}; confidence={item.confidence}",
                )
            )

        return report


class PatchProposer:
    def propose(
        self,
        translation: str,
        risk_items: list[RiskItem],
        qa_report: list[QAItem],
    ) -> list[PatchSuggestion]:
        risk_index = {item.id: item for item in risk_items}
        suggestions: list[PatchSuggestion] = []
        for qa_item in qa_report:
            if qa_item.status not in {"warn", "fail"}:
                continue
            risk = risk_index.get(qa_item.risk_item_id)
            if risk is None:
                continue
            suggested_translation = risk.target_candidates[0] if risk.target_candidates else ""
            if not suggested_translation:
                continue
            if not qa_item.translation_evidence:
                continue
            suggestions.append(
                PatchSuggestion(
                    risk_item_id=qa_item.risk_item_id,
                    source_span=qa_item.source_span,
                    current_translation=qa_item.translation_evidence,
                    suggested_translation=suggested_translation,
                    reason=f"{qa_item.reason}; source={risk.source}; policy={risk.policy}",
                    apply_mode="manual",
                )
            )
        return suggestions


def split_user_visible_risk_items(risk_items: list[RiskItem]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    visible = [asdict(item) for item in risk_items if item.user_visible]
    hidden = [asdict(item) for item in risk_items if not item.user_visible]
    return visible, hidden


def split_user_visible_qa_report(
    qa_report: list[QAItem],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    sections = {
        "확인 필요": [],
        "검토 후보": [],
        "내부 디버그": [],
    }
    hidden: list[dict[str, Any]] = []
    for item in qa_report:
        payload = asdict(item)
        if item.user_visible:
            sections.setdefault(item.review_bucket, []).append(payload)
        else:
            hidden.append(payload)
            sections["내부 디버그"].append(payload)
    return sections, hidden


def build_user_visible_qa_report_markdown(
    *,
    mode: str,
    translation: str,
    user_visible_risk_items: list[dict[str, Any]],
    user_visible_qa_report: dict[str, list[dict[str, Any]]],
    patch_suggestions: list[dict[str, Any]],
) -> str:
    lines = [
        f"# {mode} QA Report",
        "",
        "## 번역문",
        "",
        translation,
        "",
        f"## 사용자 노출 risk items ({len(user_visible_risk_items)})",
    ]
    if not user_visible_risk_items:
        lines.extend(["", "- 없음", ""])
    else:
        for item in user_visible_risk_items:
            lines.extend(
                [
                    "",
                    f"- [{item.get('type')}/{item.get('confidence')}] {item.get('anchor')}",
                    f"  - 원문 구간: {item.get('source_span')}",
                    f"  - 번역 후보: {', '.join(item.get('target_candidates') or []) or '(없음)'}",
                ]
            )

    for section_name in ("확인 필요", "검토 후보", "내부 디버그"):
        rows = user_visible_qa_report.get(section_name, [])
        lines.extend(["", f"## {section_name} ({len(rows)})"])
        if not rows:
            lines.extend(["", "- 없음"])
            continue
        for row in rows:
            lines.extend(
                [
                    "",
                    f"- [{row.get('status')}] {row.get('source_span')}",
                    f"  - 안내: {row.get('user_message')}",
                    f"  - 번역 증거: {row.get('translation_evidence') or '(자동 추출 없음)'}",
                ]
            )

    lines.extend(["", f"## Patch Suggestions ({len(patch_suggestions)})"])
    if not patch_suggestions:
        lines.extend(["", "- 없음"])
    else:
        for row in patch_suggestions:
            lines.extend(
                [
                    "",
                    f"- {row.get('source_span')}",
                    f"  - 현재 번역: {row.get('current_translation')}",
                    f"  - 제안 번역: {row.get('suggested_translation')}",
                    f"  - 근거: {row.get('reason')}",
                ]
            )
    return "\n".join(lines).strip() + "\n"


def build_evaluation_markdown(
    *,
    previous_risk_count: int,
    result: dict[str, Any],
    literal_false_positive: bool,
    ui_ready: bool,
) -> str:
    metadata = result.get("metadata", {})
    user_visible = result.get("user_visible_risk_items", [])
    patch_suggestions = result.get("patch_suggestions", [])
    risk_items = result.get("risk_items", [])
    qa_sections = result.get("user_visible_qa_report", {})

    def _hit(phrase: str) -> str:
        for row in risk_items:
            haystack = " ".join(
                str(row.get(key, "") or "")
                for key in ("anchor", "source_span", "meaning_ko")
            )
            if phrase in haystack:
                return "HIT"
        return "MISS"

    lines = [
        "# v2_direct_qa filtered evaluation",
        "",
        f"- previous risk_items: {previous_risk_count}",
        f"- user_visible_risk_items: {len(user_visible)}",
        f"- hidden_risk_items: {metadata.get('hidden_risk_item_count', 0)}",
        f"- patch_suggestions: {len(patch_suggestions)}",
        f"- ui_ready: {'yes' if ui_ready else 'no'}",
        f"- literal_false_positive_hand_evidence: {'yes' if literal_false_positive else 'no'}",
        "",
        "## 필수 관용어 처리 결과",
    ]
    for phrase in REQUIRED_EVALUATION_PHRASES[:-1]:
        lines.append(f"- {phrase}: {_hit(phrase)}")
    lines.extend(
        [
            "",
            "## 손에 쥐다 literal 오탐",
            f"- 손에 쥐다: {'WARN/FAIL' if literal_false_positive else 'OK'}",
            "",
            "## QA 섹션 개수",
            f"- 확인 필요: {len(qa_sections.get('확인 필요', []))}",
            f"- 검토 후보: {len(qa_sections.get('검토 후보', []))}",
            f"- 내부 디버그: {len(qa_sections.get('내부 디버그', []))}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def direct_result_to_dict(result: DirectTranslationResult) -> dict[str, Any]:
    return asdict(result)


def v2_result_to_dict(result: V2TranslationResult) -> dict[str, Any]:
    return asdict(result)
