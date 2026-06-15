from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import PipelineConfig
from .v2_pipeline import RiskItem, SourceSideAnalyzer


@dataclass(slots=True)
class MeaningDraft:
    text: str
    model: str
    purpose: str = "semantic_baseline"
    temperature_profile: str = "low"


@dataclass(slots=True)
class RagEvidence:
    id: str
    source_span: str
    anchor: str
    evidence_type: str
    literal_meaning: str
    pragmatic_function: str
    tone: str
    cultural_meaning: str
    literal_risk: str
    strategy_hints: list[str] = field(default_factory=list)
    candidate_translations: list[str] = field(default_factory=list)
    confidence: str = "low"
    source: str = "rag"
    source_id: str = ""
    user_visible: bool = False


@dataclass(slots=True)
class TranslationDecision:
    id: str
    source_span: str
    meaning_draft_span: str
    vibe_translation_span: str
    decision_type: str
    reason: str
    evidence_ids: list[str] = field(default_factory=list)
    author_note: str = ""
    confidence: str = "low"
    needs_author_review: bool = False
    risk_level: str = "low"
    target_span: str = ""
    target_start: int | None = None
    target_end: int | None = None
    alignment_status: str = "target_unresolved"
    priority: str = "P1"
    card_status: str = "pending"
    unresolved_risk: bool = False
    suggested_actions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AuthorReviewCard:
    id: str
    decision_id: str
    source_span: str
    current_translation: str
    decision_label: str
    explanation: str
    author_question: str
    options: list[dict[str, str]] = field(default_factory=list)
    recommended_option_id: str | None = None
    evidence_summary: str = ""
    patch_suggestion: dict[str, Any] | None = None
    priority: str = "P1"
    status: str = "pending"
    target_span: str = ""
    suggested_actions: list[str] = field(default_factory=list)
    created_from_evidence_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class V2DualDraftReviewResult:
    mode: str
    source_text: str
    final_translation: str
    meaning_draft: MeaningDraft
    rag_evidence: list[RagEvidence] = field(default_factory=list)
    translation_decisions: list[TranslationDecision] = field(default_factory=list)
    author_review_cards: list[AuthorReviewCard] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    delivery_status: str = "deliverable"
    user_visible_error_code: str | None = None


class MeaningDraftTranslator:
    def __init__(self, config: PipelineConfig):
        self.config = config

    @staticmethod
    def _build_mock_meaning_text(source_text: str, *, seed_translation: str | None = None) -> str:
        text = _compact_text(seed_translation)
        if text:
            return text
        source = _compact_text(source_text)
        if not source:
            return ""
        return source

    def translate(
        self,
        source_text: str,
        *,
        locale: str,
        config: PipelineConfig | None = None,
        seed_translation: str | None = None,
    ) -> MeaningDraft:
        active_config = config or self.config
        model = _compact_text(active_config.translation_model) or "mock-meaning-draft"
        text = self._build_mock_meaning_text(source_text, seed_translation=seed_translation)
        return MeaningDraft(
            text=text,
            model=model,
            purpose="semantic_baseline",
            temperature_profile="low",
        )


def _compact_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _unique_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = _compact_text(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output


def _evidence_type_for_risk(risk: RiskItem) -> str:
    risk_type = _compact_text(risk.type).lower()
    if risk_type in {"idiom", "proverb", "slang", "k_culture", "pragmatic", "term", "annotation"}:
        return risk_type
    if risk.source == "terminology":
        return "term"
    if risk.source == "rag":
        return "annotation" if risk_type in {"culture", "annotation"} else "idiom"
    return "pragmatic"


def _source_label_for_risk(risk: RiskItem, evidence_type: str) -> str:
    if risk.source == "terminology":
        return "terminology"
    if evidence_type == "annotation":
        return "annotation_rag"
    if evidence_type in {"idiom", "proverb", "slang", "pragmatic"}:
        return "idiom_rag" if risk.source == "rag" else "source_side_analyzer"
    return risk.source or "source_side_analyzer"


def _pragmatic_function_for_risk(risk: RiskItem, evidence_type: str) -> str:
    if evidence_type == "idiom":
        return "figurative meaning should be judged from context, not word-for-word"
    if evidence_type == "proverb":
        return "proverbial guidance or maxim with contextual meaning"
    if evidence_type == "slang":
        return "informal or in-group expression that may require tone adaptation"
    if evidence_type == "k_culture":
        return "culture-specific reference that may need explanation or localization"
    if evidence_type == "pragmatic":
        return "context-dependent pragmatic cue"
    if evidence_type == "term":
        return "terminology or named-entity handling"
    if evidence_type == "annotation":
        return "source-side annotation for cultural context"
    return _compact_text(risk.meaning_ko)


def _literal_risk_for_risk(risk: RiskItem, evidence_type: str) -> str:
    parts = [_compact_text(risk.filter_reason), _compact_text(risk.debug_reason), _compact_text(risk.policy)]
    parts = [part for part in parts if part]
    if parts:
        return "; ".join(_unique_preserve(parts))
    if evidence_type in {"idiom", "proverb", "slang", "pragmatic"}:
        return "literal translation may miss the intended figurative or pragmatic meaning"
    if evidence_type in {"k_culture", "annotation"}:
        return "literal translation may omit the cultural context"
    if evidence_type in {"term", "entity"}:
        return "literal translation may mis-handle a controlled term or named entity"
    return ""


def _strategy_hints_for_risk(risk: RiskItem, evidence_type: str) -> list[str]:
    hints: list[str] = []
    for candidate in (
        risk.filter_reason,
        risk.debug_reason,
        risk.policy,
        "reference only; do not force the candidate translation",
        *risk.target_candidates,
    ):
        cleaned = _compact_text(candidate)
        if cleaned:
            hints.append(cleaned)
    if evidence_type == "annotation":
        hints.append("consider an explanatory or localized note if the context warrants it")
    return _unique_preserve(hints)[:5]


def _confidence_for_risk(risk: RiskItem) -> str:
    confidence = _compact_text(risk.confidence).lower()
    if confidence in {"low", "medium", "high"}:
        return confidence
    return "low"


def _user_visible_for_risk(risk: RiskItem, evidence_type: str, confidence: str) -> bool:
    if risk.user_visible:
        return True
    if confidence != "high":
        return False
    return evidence_type in {"idiom", "proverb", "slang", "k_culture", "pragmatic", "term", "annotation"}


def risk_item_to_rag_evidence(risk: RiskItem) -> RagEvidence:
    evidence_type = _evidence_type_for_risk(risk)
    confidence = _confidence_for_risk(risk)
    return RagEvidence(
        id=_compact_text(risk.id) or f"risk:{evidence_type}",
        source_span=_compact_text(risk.source_span),
        anchor=_compact_text(risk.anchor),
        evidence_type=evidence_type,
        literal_meaning=_compact_text(risk.meaning_ko) if evidence_type in {"idiom", "proverb", "slang", "k_culture", "pragmatic", "term", "annotation"} else "",
        pragmatic_function=_pragmatic_function_for_risk(risk, evidence_type),
        tone="",
        cultural_meaning=_compact_text(risk.meaning_ko) if evidence_type in {"k_culture", "annotation"} else "",
        literal_risk=_literal_risk_for_risk(risk, evidence_type),
        strategy_hints=_strategy_hints_for_risk(risk, evidence_type),
        candidate_translations=_unique_preserve([*risk.target_candidates])[:5],
        confidence=confidence,
        source=_source_label_for_risk(risk, evidence_type),
        source_id=_compact_text(risk.id),
        user_visible=_user_visible_for_risk(risk, evidence_type, confidence),
    )


class RagEvidenceRetriever:
    def __init__(self, analyzer: SourceSideAnalyzer):
        self.analyzer = analyzer

    def retrieve(self, source_text: str, *, user_visible_only: bool = False) -> list[RagEvidence]:
        evidence = [risk_item_to_rag_evidence(risk) for risk in self.analyzer.analyze(source_text)]
        if user_visible_only:
            return [item for item in evidence if item.user_visible]
        return evidence


def _contains_text(haystack: str, needle: str) -> bool:
    haystack_text = _compact_text(haystack).casefold()
    needle_text = _compact_text(needle).casefold()
    return bool(haystack_text and needle_text and needle_text in haystack_text)


def _decision_reason_for_evidence(evidence: RagEvidence, decision_type: str) -> str:
    details = _unique_preserve(
        [
            evidence.literal_risk,
            evidence.pragmatic_function,
            evidence.cultural_meaning,
            *evidence.strategy_hints[:3],
        ]
    )
    if not details:
        if decision_type == "preserved":
            return "이 표현이 번역문에 그대로 남아 있어 보존 여부 확인이 필요합니다."
        return "이 표현은 작가 검수가 필요한 판단 지점입니다."

    summary = "; ".join(details[:3])
    if decision_type == "preserved":
        return f"{summary}. 번역문에 원문 표현이 남아 있어 보존 여부 확인이 필요합니다."
    return f"{summary}. 작가 검수가 필요합니다."


def _author_note_for_evidence(evidence: RagEvidence, decision_type: str) -> str:
    if evidence.evidence_type in {"k_culture", "annotation"}:
        if decision_type == "preserved":
            return "이 문화어를 원어로 유지한 의도가 맞는지 확인할까요?"
        return "이 문화어를 원어로 유지할지, 설명을 붙일지 확인이 필요합니다."
    if evidence.evidence_type in {"idiom", "proverb", "slang", "pragmatic"}:
        if decision_type == "preserved":
            return "이 표현을 그대로 둔 의도가 맞는지 확인할까요?"
        return "이 표현은 실제 의미보다 관계성/톤이 중요한 표현인가요?"
    if evidence.evidence_type == "term":
        if decision_type == "preserved":
            return "이 용어를 원어로 유지한 선택이 맞는지 확인할까요?"
        return "이 용어는 고정 번역어를 쓸지, 원어 유지할지 확인이 필요합니다."
    if decision_type == "preserved":
        return "이 표현을 그대로 둔 의도가 맞는지 확인할까요?"
    return "이 표현의 처리 방식이 맞는지 확인이 필요합니다."


def _decision_type_for_evidence(evidence: RagEvidence, final_translation: str) -> str:
    if _contains_text(final_translation, evidence.source_span) or _contains_text(final_translation, evidence.anchor):
        return "preserved"
    return "risk_unresolved"


def _risk_level_for_decision(evidence: RagEvidence, decision_type: str) -> str:
    confidence = _compact_text(evidence.confidence).lower()
    if decision_type == "preserved":
        if confidence == "high":
            return "low"
        if confidence == "medium":
            return "medium"
        return "high"
    if confidence == "high":
        return "high"
    if confidence == "medium":
        return "medium"
    return "low"


def _priority_for_decision(evidence: RagEvidence, decision_type: str) -> str:
    confidence = _compact_text(evidence.confidence).lower()
    if confidence == "high":
        return "P1"
    if confidence == "medium":
        if decision_type == "risk_unresolved":
            return "P1"
        return "P2"
    if decision_type == "risk_unresolved":
        return "P2"
    return "P3"


def _suggested_actions_for_decision(decision_type: str) -> list[str]:
    if decision_type == "risk_unresolved":
        return ["작가 검토"]
    if decision_type == "preserved":
        return ["현재 번역 유지 검토"]
    return []


class TranslationDecisionAnalyzer:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()

    def analyze(
        self,
        rag_evidence: list[RagEvidence],
        meaning_draft: MeaningDraft,
        final_translation: str,
        *,
        source_text: str = "",
        locale: str = "",
    ) -> list[TranslationDecision]:
        _ = (source_text, locale)
        decisions: list[TranslationDecision] = []
        draft_text = _compact_text(meaning_draft.text)
        final_text = _compact_text(final_translation)

        for evidence in rag_evidence:
            if not evidence.user_visible:
                continue
            if _compact_text(evidence.confidence).lower() == "low":
                continue

            decision_type = _decision_type_for_evidence(evidence, final_text)
            decision_id = _compact_text(evidence.id) or _compact_text(evidence.source_id) or "decision"
            evidence_ids = _unique_preserve([evidence.source_id or evidence.id, evidence.id])
            source_span = _compact_text(evidence.source_span) or _compact_text(evidence.anchor)
            alignment_status = "source_only" if source_span else "unresolved"
            decisions.append(
                TranslationDecision(
                    id=f"decision:{decision_id}",
                    source_span=source_span,
                    meaning_draft_span=draft_text,
                    vibe_translation_span=final_text,
                    target_span="",
                    target_start=None,
                    target_end=None,
                    alignment_status=alignment_status,
                    decision_type=decision_type,
                    reason=_decision_reason_for_evidence(evidence, decision_type),
                    evidence_ids=evidence_ids,
                    author_note=_author_note_for_evidence(evidence, decision_type),
                    confidence=_compact_text(evidence.confidence) or "low",
                    priority=_priority_for_decision(evidence, decision_type),
                    card_status="pending",
                    unresolved_risk=decision_type == "risk_unresolved",
                    suggested_actions=_suggested_actions_for_decision(decision_type),
                    needs_author_review=True,
                    risk_level=_risk_level_for_decision(evidence, decision_type),
                )
            )
        return decisions


def _decision_label_for_type(decision_type: str) -> str:
    mapping = {
        "literal": "직역 유지",
        "adaptive": "문맥 의역",
        "localized": "현지화",
        "preserved": "원어 유지",
        "expanded": "설명 보강",
        "compressed": "압축 번역",
        "risk_unresolved": "작가 확인 필요",
    }
    return mapping.get(_compact_text(decision_type), "작가 확인 필요")


def _card_explanation_for_decision(decision: TranslationDecision) -> str:
    text = _compact_text(decision.reason)
    if text:
        return text
    if decision.decision_type == "preserved":
        return "이 표현은 원문 표현이 남아 있어 보존 여부 확인이 필요합니다."
    return "이 표현은 작가 확인이 필요한 판단 지점입니다."


def _card_question_for_decision(decision: TranslationDecision, evidence_types: list[str]) -> str:
    note = _compact_text(decision.author_note)
    if note:
        return note
    evidence_type = evidence_types[0] if evidence_types else ""
    if evidence_type in {"k_culture", "annotation"}:
        return "이 문화어를 원어로 유지할지, 설명을 붙일지 확인해 주세요."
    if evidence_type in {"idiom", "proverb", "slang", "pragmatic"}:
        return "이 표현의 핵심이 실제 의미인가요, 관계성이나 톤인가요?"
    if evidence_type == "term":
        return "이 용어를 원어로 유지할지, 고정 번역어로 바꿀지 확인해 주세요."
    if decision.decision_type == "preserved":
        return "이 표현을 그대로 둔 의도가 맞는지 확인해 주세요."
    return "이 표현의 처리 방식이 맞는지 확인해 주세요."


def _card_options_for_decision(decision: TranslationDecision) -> list[dict[str, str]]:
    options = [
        {
            "id": "keep",
            "label": "현재 번역 유지",
            "description": "현재 번역을 유지합니다.",
        },
        {
            "id": "review",
            "label": "직접 검토",
            "description": "작가가 문맥에 맞게 직접 확인합니다.",
        },
    ]
    if decision.decision_type == "preserved":
        options.insert(
            1,
            {
                "id": "add_explanation",
                "label": "설명 보강 검토",
                "description": "원어를 유지하되 설명을 덧붙일지 검토합니다.",
            },
        )
    elif decision.decision_type == "risk_unresolved":
        options.insert(
            1,
            {
                "id": "make_more_literal",
                "label": "더 직접적인 번역",
                "description": "의미가 더 직접 드러나도록 조정할지 검토합니다.",
            },
        )
        options.insert(
            2,
            {
                "id": "make_more_natural",
                "label": "더 자연스러운 번역",
                "description": "문맥에 맞게 더 자연스럽게 풀어낼지 검토합니다.",
            },
        )
    return options


def _evidence_lookup(rag_evidence: list[RagEvidence]) -> dict[str, RagEvidence]:
    lookup: dict[str, RagEvidence] = {}
    for evidence in rag_evidence:
        lookup[_compact_text(evidence.id)] = evidence
        lookup[_compact_text(evidence.source_id)] = evidence
    return lookup


def _evidence_summary_for_decision(
    decision: TranslationDecision,
    evidence_lookup: dict[str, RagEvidence],
) -> str:
    summaries: list[str] = []
    for evidence_id in decision.evidence_ids:
        evidence = evidence_lookup.get(_compact_text(evidence_id))
        if evidence is None:
            continue
        bits = _unique_preserve(
            [
                evidence.literal_risk,
                evidence.pragmatic_function,
                evidence.cultural_meaning,
            ]
        )
        if bits:
            summaries.append(" / ".join(bits[:2]))
    return " | ".join(_unique_preserve(summaries)[:2])


class AuthorReviewCardGenerator:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()

    def generate(
        self,
        translation_decisions: list[TranslationDecision],
        *,
        rag_evidence: list[RagEvidence] | None = None,
    ) -> list[AuthorReviewCard]:
        if not translation_decisions:
            return []

        evidence_lookup = _evidence_lookup(rag_evidence or [])
        cards: list[AuthorReviewCard] = []
        for decision in translation_decisions:
            if not decision.needs_author_review:
                continue

            evidence_types = [evidence_lookup.get(_compact_text(evidence_id)).evidence_type for evidence_id in decision.evidence_ids if evidence_lookup.get(_compact_text(evidence_id))]
            evidence_types = _unique_preserve(evidence_types)
            current_translation = _compact_text(decision.vibe_translation_span)
            card = AuthorReviewCard(
                id=f"review:{_compact_text(decision.id) or 'decision'}",
                decision_id=_compact_text(decision.id),
                source_span=_compact_text(decision.source_span),
                current_translation=current_translation,
                priority=_compact_text(decision.priority) or "P1",
                status=_compact_text(decision.card_status) or "pending",
                target_span=_compact_text(decision.target_span),
                suggested_actions=list(decision.suggested_actions),
                created_from_evidence_ids=list(decision.evidence_ids),
                decision_label=_decision_label_for_type(decision.decision_type),
                explanation=_card_explanation_for_decision(decision),
                author_question=_card_question_for_decision(decision, evidence_types),
                options=_card_options_for_decision(decision),
                recommended_option_id="review" if decision.decision_type == "risk_unresolved" else "keep",
                evidence_summary=_evidence_summary_for_decision(decision, evidence_lookup),
                patch_suggestion=None,
            )
            cards.append(card)
        return cards
