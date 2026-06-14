from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from .agents.chatbot import ChatbotAgent
from .agents.inspector import InspectionAgent
from .agents.translator import Translator
from .config import PipelineConfig, TranslationMode
from .retrieval.annotation_retriever import AnnotationRetriever
from .retrieval.retriever import IdiomRetriever
from .translation_graph import TranslationGraph
from .v2_pipeline import (
    DirectTranslationResult,
    DirectTranslator,
    PatchProposer,
    PostTranslationQA,
    SourceSideAnalyzer,
    V2TranslationResult,
    split_user_visible_qa_report,
    split_user_visible_risk_items,
)
from .v2_dual_draft_review import (
    TranslationDecisionAnalyzer,
    MeaningDraftTranslator,
    MeaningDraft,
    RagEvidenceRetriever,
    V2DualDraftReviewResult,
)


@dataclass(slots=True)
class AgentWorkflowResult:
    source_text: str
    retrievals: list[dict[str, Any]]
    annotation_matches: list[dict[str, Any]]
    draft: dict[str, Any]
    inspection: dict[str, Any]
    reviewed_translation: str
    context_extraction: dict[str, Any] | None = None
    memory_context: str = ""
    blocked: bool = False
    block_reason: str = ""
    translation_profile: dict[str, Any] | None = None
    source_analysis: dict[str, Any] | None = None
    annotation_candidates: list[dict[str, Any]] = field(default_factory=list)
    terminology_candidates: list[dict[str, Any]] = field(default_factory=list)
    active_terminology: list[dict[str, Any]] = field(default_factory=list)
    terminology_context: str = ""
    draft_translation: str = ""
    inspection_issues: list[dict[str, Any]] = field(default_factory=list)
    support_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class TranslationPipeline:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.retriever = IdiomRetriever(self.config)
        self.annotation_retriever = AnnotationRetriever(self.config)
        self.translator = Translator(self.config)
        self.direct_translator = DirectTranslator(self.translator)
        self.inspector = InspectionAgent(self.config)
        self.chatbot = ChatbotAgent(self.config)
        self.source_side_analyzer = SourceSideAnalyzer(
            self.config,
            idiom_retriever=self.retriever,
            annotation_retriever=self.annotation_retriever,
        )
        self.rag_evidence_retriever = RagEvidenceRetriever(self.source_side_analyzer)
        self.meaning_draft_translator = MeaningDraftTranslator(self.config)
        self.translation_decision_analyzer = TranslationDecisionAnalyzer(self.config)
        self.post_translation_qa = PostTranslationQA()
        self.patch_proposer = PatchProposer()
        self.graph = TranslationGraph(
            self.config,
            retriever=self.retriever,
            annotation_retriever=self.annotation_retriever,
            translator=self.translator,
            inspector=self.inspector,
        )

    def _metadata(
        self,
        *,
        source_side_rag_enabled: bool,
        rag_enabled: bool,
        terminology_enabled: bool,
        glossary_enabled: bool,
        review_enabled: bool,
        inspection_enabled: bool,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.config.build_metadata(
            source_side_rag_enabled=source_side_rag_enabled,
            rag_enabled=rag_enabled,
            terminology_enabled=terminology_enabled,
            glossary_enabled=glossary_enabled,
            review_enabled=review_enabled,
            inspection_enabled=inspection_enabled,
            extra=extra,
        )

    @staticmethod
    def _target_script_ratio(*, locale: str, latin_chars: int, han_chars: int, japanese_chars: int, thai_chars: int, total: int) -> float:
        if locale == "ko_en_us":
            return latin_chars / total
        if locale == "ko_zh_cn":
            return han_chars / total
        if locale == "ko_th_th":
            return thai_chars / total
        return japanese_chars / total

    @classmethod
    def _pass_threshold_for_locale(cls, locale: str) -> float:
        if locale in {"ko_en_us", "ko_zh_cn"}:
            return 0.3
        return 0.2

    @staticmethod
    def _hangul_spans(text: str) -> list[dict[str, Any]]:
        return [
            {"text": match.group(0), "start": match.start(), "end": match.end(), "length": len(match.group(0))}
            for match in re.finditer(r"[\uac00-\ud7a3]+", text)
        ]

    @staticmethod
    def _residual_hangul_ratio(text: str) -> float:
        total = max(len(text), 1)
        return round(len(re.findall(r"[\uac00-\ud7a3]", text)) / total, 4)

    @classmethod
    def _is_source_copy_like(
        cls,
        *,
        source_text: str,
        final_translation: str,
        locale: str,
        target_script_ratio: float,
        korean_chars: int,
        total: int,
        residual_hangul_spans: list[dict[str, Any]],
    ) -> bool:
        prefix_len = min(200, len(source_text), len(final_translation))
        source_prefix_match = prefix_len > 0 and source_text[:prefix_len] == final_translation[:prefix_len]
        if source_prefix_match or source_text.strip() == final_translation.strip():
            return True
        if korean_chars / total >= 0.35 and target_script_ratio <= 0.2:
            return True
        if len(residual_hangul_spans) >= 2 and korean_chars / total >= 0.2 and target_script_ratio <= cls._pass_threshold_for_locale(locale):
            return True
        return False

    @classmethod
    def _translation_safety_checks(
        cls,
        *,
        source_text: str,
        final_translation: str,
        locale: str = "ko_ja",
        target_language_name: str = "Japanese",
    ) -> dict[str, Any]:
        total = max(len(final_translation), 1)
        korean_chars = len(re.findall(r"[\uac00-\ud7a3]", final_translation))
        latin_chars = len(re.findall(r"[A-Za-z]", final_translation))
        han_chars = len(re.findall(r"[\u4e00-\u9fff]", final_translation))
        japanese_chars = len(re.findall(r"[\u3040-\u30ff\u31f0-\u31ff\u4e00-\u9fff]", final_translation))
        thai_chars = len(re.findall(r"[\u0e00-\u0e7f]", final_translation))
        target_script_ratio = cls._target_script_ratio(
            locale=locale,
            latin_chars=latin_chars,
            han_chars=han_chars,
            japanese_chars=japanese_chars,
            thai_chars=thai_chars,
            total=total,
        )
        prefix_len = min(200, len(source_text), len(final_translation))
        source_prefix_match = prefix_len > 0 and source_text[:prefix_len] == final_translation[:prefix_len]
        residual_hangul_spans = cls._hangul_spans(final_translation)
        residual_hangul_ratio = cls._residual_hangul_ratio(final_translation)
        pass_threshold = cls._pass_threshold_for_locale(locale)
        source_copy_like = cls._is_source_copy_like(
            source_text=source_text,
            final_translation=final_translation,
            locale=locale,
            target_script_ratio=target_script_ratio,
            korean_chars=korean_chars,
            total=total,
            residual_hangul_spans=residual_hangul_spans,
        )
        weak_source_copy_signal = (
            not source_copy_like
            and (
                source_prefix_match
                or (korean_chars / total >= 0.2 and target_script_ratio <= pass_threshold)
                or (len(residual_hangul_spans) >= 2 and residual_hangul_ratio >= 0.08)
            )
        )
        source_copy_status = "fail" if source_copy_like else "warn" if weak_source_copy_signal else "pass"
        source_copy_suspected = source_copy_status == "fail"

        locale_adherence_status = "fail" if source_copy_status == "fail" or target_script_ratio < 0.1 else "pass"
        if locale_adherence_status == "pass" and target_script_ratio < pass_threshold:
            locale_adherence_status = "warn"

        if not residual_hangul_spans:
            residual_hangul_status = "pass"
        else:
            sentence_like_hangul = len(residual_hangul_spans) >= 2 and any(
                span["length"] <= 4 for span in residual_hangul_spans
            )
            if source_copy_status == "fail" or sentence_like_hangul:
                residual_hangul_status = "fail"
            else:
                residual_hangul_status = "warn"

        proper_noun_issues: list[dict[str, Any]] = []
        if residual_hangul_spans and source_copy_status != "fail":
            for span in residual_hangul_spans:
                proper_noun_issues.append(
                    {
                        "issue_type": "possible_transliteration_issue",
                        "span": span["text"],
                        "start": span["start"],
                        "end": span["end"],
                        "length": span["length"],
                    }
                )
        proper_noun_status = "pass"
        if proper_noun_issues:
            proper_noun_status = "warn" if residual_hangul_status != "fail" else "unchecked"

        overall_status = "pass"
        if source_copy_status == "fail" or locale_adherence_status == "fail" or residual_hangul_status == "fail":
            overall_status = "fail"
        elif (
            locale_adherence_status == "warn"
            or residual_hangul_status == "warn"
            or proper_noun_status in {"warn", "unchecked"}
            or source_copy_status == "warn"
        ):
            overall_status = "warn"

        locale_adherence = {
            "status": locale_adherence_status,
            "locale": locale,
            "target_language_name": target_language_name,
            "target_script_ratio": round(target_script_ratio, 4),
            "target_script_threshold": round(pass_threshold, 4),
            "korean_char_ratio": round(korean_chars / total, 4),
            "latin_char_ratio": round(latin_chars / total, 4),
            "han_char_ratio": round(han_chars / total, 4),
            "japanese_char_ratio": round(japanese_chars / total, 4),
            "thai_char_ratio": round(thai_chars / total, 4),
        }
        source_copy = {
            "status": source_copy_status,
            "suspected": source_copy_suspected,
            "source_prefix_match_200": source_prefix_match,
            "source_exact_match": source_text.strip() == final_translation.strip(),
            "source_copy_like": source_copy_like,
            "weak_source_copy_signal": weak_source_copy_signal,
            "reason": (
                "literal source copy or severe source-language leakage"
                if source_copy_status == "fail"
                else "weak source-copy signal"
                if source_copy_status == "warn"
                else "no strong source-copy signal"
            ),
        }
        residual_hangul = {
            "status": residual_hangul_status,
            "ratio": residual_hangul_ratio,
            "spans": residual_hangul_spans,
            "examples": [span["text"] for span in residual_hangul_spans[:5]],
            "reason": (
                "residual Hangul span(s) remain"
                if residual_hangul_spans
                else "no residual Hangul detected"
            ),
        }
        proper_noun_transliteration = {
            "status": proper_noun_status if not proper_noun_issues else proper_noun_status,
            "issues": proper_noun_issues,
        }

        return {
            "locale": locale,
            "target_language_name": target_language_name,
            "raw_model_response_length": len(final_translation),
            "final_translation_length": len(final_translation),
            "source_prefix_match_200": source_prefix_match,
            "korean_char_ratio": round(korean_chars / total, 4),
            "latin_char_ratio": round(latin_chars / total, 4),
            "han_char_ratio": round(han_chars / total, 4),
            "japanese_char_ratio": round(japanese_chars / total, 4),
            "thai_char_ratio": round(thai_chars / total, 4),
            "target_script_ratio": round(target_script_ratio, 4),
            "source_copy_suspected": source_copy_suspected,
            "source_copy_status": source_copy_status,
            "residual_hangul_ratio": residual_hangul_ratio,
            "residual_hangul_status": residual_hangul_status,
            "residual_hangul_spans": residual_hangul_spans,
            "residual_hangul_examples": residual_hangul["examples"],
            "proper_noun_transliteration_status": proper_noun_status,
            "proper_noun_transliteration_issues": proper_noun_issues,
            "locale_adherence_status": locale_adherence_status,
            "overall_translation_safety_status": overall_status,
            "translation_safety": {
                "overall_status": overall_status,
                "locale_adherence": locale_adherence,
                "source_copy": source_copy,
                "residual_hangul": residual_hangul,
                "proper_noun_transliteration": proper_noun_transliteration,
            },
        }

    @classmethod
    def _locale_adherence_metadata(
        cls,
        *,
        source_text: str,
        final_translation: str,
        locale: str = "ko_ja",
        target_language_name: str = "Japanese",
    ) -> dict[str, Any]:
        checks = cls._translation_safety_checks(
            source_text=source_text,
            final_translation=final_translation,
            locale=locale,
            target_language_name=target_language_name,
        )
        return {
            **checks,
            "locale_adherence_status": checks["translation_safety"]["locale_adherence"]["status"],
            "source_copy_suspected": checks["translation_safety"]["source_copy"]["suspected"],
            "source_copy_status": checks["translation_safety"]["source_copy"]["status"],
            "residual_hangul_status": checks["translation_safety"]["residual_hangul"]["status"],
            "residual_hangul_ratio": checks["translation_safety"]["residual_hangul"]["ratio"],
            "residual_hangul_spans": checks["translation_safety"]["residual_hangul"]["spans"],
            "residual_hangul_examples": checks["translation_safety"]["residual_hangul"]["examples"],
            "proper_noun_transliteration_status": checks["translation_safety"]["proper_noun_transliteration"]["status"],
            "proper_noun_transliteration_issues": checks["translation_safety"]["proper_noun_transliteration"]["issues"],
            "overall_translation_safety_status": checks["translation_safety"]["overall_status"],
        }

    @staticmethod
    def _should_retry_translation_safety(metadata: dict[str, Any]) -> bool:
        return (
            metadata.get("source_copy_status") == "fail"
            or metadata.get("locale_adherence_status") == "fail"
            or bool(metadata.get("source_copy_suspected"))
        )

    @staticmethod
    def _translation_safety_is_hard_fail(metadata: dict[str, Any]) -> bool:
        return metadata.get("source_copy_status") == "fail" or metadata.get("locale_adherence_status") == "fail"

    def run_with_inspection(
        self,
        source_text: str,
        *,
        request_payload: dict[str, Any] | None = None,
        translation_memory: list[dict[str, Any]] | None = None,
        memory_context: str = "",
        retrieval_queries: list[str] | None = None,
        context_extraction: dict[str, Any] | None = None,
    ) -> AgentWorkflowResult:
        return self.graph.run_with_inspection(
            source_text,
            request_payload=request_payload,
            translation_memory=translation_memory,
            memory_context=memory_context,
            retrieval_queries=retrieval_queries,
            context_extraction=context_extraction,
        )

    def _run_direct_translation_once(
        self,
        source_text: str,
        *,
        strict_locale_retry: bool = False,
        retry_attempt: int = 0,
    ) -> DirectTranslationResult:
        draft = self.direct_translator.translate(
            source_text,
            strict_locale_retry=strict_locale_retry,
            retry_attempt=retry_attempt,
        )
        resources = self.config.resolved_resources()
        locale_meta = self._locale_adherence_metadata(
            source_text=source_text,
            final_translation=draft.translation,
            locale=resources.locale,
            target_language_name=resources.target_language,
        )
        return DirectTranslationResult(
            mode="direct_only",
            final_translation=draft.translation,
            draft=asdict(draft),
            metadata=self._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=locale_meta,
            ),
        )

    def _finalize_direct_translation(
        self,
        source_text: str,
        initial_result: DirectTranslationResult,
    ) -> DirectTranslationResult:
        initial_metadata = initial_result.metadata
        retry_attempted = self._should_retry_translation_safety(initial_metadata)
        retry_result: DirectTranslationResult | None = None
        final_result = initial_result
        if retry_attempted:
            retry_result = self._run_direct_translation_once(
                source_text,
                strict_locale_retry=True,
                retry_attempt=1,
            )
            final_result = retry_result

        final_metadata = final_result.metadata
        if not retry_attempted:
            retry_success: bool | None = None
        else:
            retry_success = not self._translation_safety_is_hard_fail(final_metadata)

        delivery_status = "deliverable"
        if retry_attempted and retry_success is False:
            delivery_status = "blocked_translation_safety"
        user_visible_error_code = None if delivery_status == "deliverable" else "translation_safety_failed"

        final_result.metadata = {
            **final_metadata,
            "translation_safety_retry_attempted": retry_attempted,
            "translation_safety_retry_count": 1 if retry_attempted else 0,
            "initial_translation_safety": initial_metadata["translation_safety"],
            "final_translation_safety": final_metadata["translation_safety"],
            "initial_locale_adherence_status": initial_metadata["locale_adherence_status"],
            "final_locale_adherence_status": final_metadata["locale_adherence_status"],
            "initial_source_copy_status": initial_metadata["source_copy_status"],
            "final_source_copy_status": final_metadata["source_copy_status"],
            "initial_source_copy_suspected": initial_metadata["source_copy_suspected"],
            "final_source_copy_suspected": final_metadata["source_copy_suspected"],
            "retry_translation_model": retry_result.metadata["translation_model"] if retry_result else None,
            "retry_prompt_hash": retry_result.draft["prompt_debug"].get("prompt_hash") if retry_result else None,
            "retry_success": retry_success,
            "delivery_status": delivery_status,
            "user_visible_error_code": user_visible_error_code,
        }
        final_result.delivery_status = delivery_status
        final_result.user_visible_error_code = user_visible_error_code
        return final_result

    def run_direct_only(
        self,
        source_text: str,
        *,
        strict_locale_retry: bool = False,
        retry_attempt: int = 0,
    ) -> DirectTranslationResult:
        initial_result = self._run_direct_translation_once(
            source_text,
            strict_locale_retry=strict_locale_retry,
            retry_attempt=retry_attempt,
        )
        return self._finalize_direct_translation(source_text, initial_result)

    def run_v2_direct_qa(self, source_text: str) -> V2TranslationResult:
        final_result = self.run_direct_only(source_text)
        final_metadata = final_result.metadata
        risk_items = self.source_side_analyzer.analyze(source_text)
        qa_report = self.post_translation_qa.evaluate(
            source_text,
            final_result.final_translation,
            risk_items,
        )
        user_visible_risk_items, hidden_risk_items = split_user_visible_risk_items(risk_items)
        user_visible_qa_report, hidden_qa_report = split_user_visible_qa_report(qa_report)
        patch_suggestions = self.patch_proposer.propose(
            final_result.final_translation,
            risk_items,
            qa_report,
        )
        metadata = self._metadata(
            source_side_rag_enabled=True,
            rag_enabled=False,
            terminology_enabled=False,
            glossary_enabled=False,
            review_enabled=False,
            inspection_enabled=False,
            extra={
                "risk_item_count": len(risk_items),
                "internal_risk_item_count": len(risk_items),
                "user_visible_risk_item_count": len(user_visible_risk_items),
                "hidden_risk_item_count": len(hidden_risk_items),
                "qa_item_count": len(qa_report),
                "user_visible_qa_count": sum(
                    len(rows) for key, rows in user_visible_qa_report.items() if key != "내부 디버그"
                ),
                "hidden_qa_count": len(hidden_qa_report),
                "patch_suggestion_count": len(patch_suggestions),
                **final_metadata,
            },
        )
        return V2TranslationResult(
            mode="v2_direct_qa",
            final_translation=final_result.final_translation,
            risk_items=[asdict(item) for item in risk_items],
            qa_report=[asdict(item) for item in qa_report],
            user_visible_risk_items=user_visible_risk_items,
            hidden_risk_items=hidden_risk_items,
            user_visible_qa_report=user_visible_qa_report,
            hidden_qa_report=hidden_qa_report,
            patch_suggestions=[asdict(item) for item in patch_suggestions],
            metadata=metadata,
            draft=final_result.draft,
            delivery_status=final_result.delivery_status,
            user_visible_error_code=final_result.user_visible_error_code,
        )

    def run_v2_dual_draft_review(self, source_text: str) -> V2DualDraftReviewResult:
        direct_result = self.run_direct_only(source_text)
        blocked = direct_result.delivery_status == "blocked_translation_safety"
        rag_evidence = [] if blocked else self.rag_evidence_retriever.retrieve(source_text)
        meaning_draft = (
            MeaningDraft(text="", model=self.config.translation_model or "", purpose="semantic_baseline", temperature_profile="low")
            if blocked
            else self.meaning_draft_translator.translate(
                source_text,
                locale=self.config.resolved_resources().locale,
                config=self.config,
                seed_translation=direct_result.final_translation,
            )
        )
        translation_decisions = (
            []
            if blocked
            else self.translation_decision_analyzer.analyze(
                rag_evidence,
                meaning_draft,
                direct_result.final_translation,
                source_text=source_text,
                locale=self.config.resolved_resources().locale,
            )
        )
        metadata = self._metadata(
            source_side_rag_enabled=not blocked,
            rag_enabled=False,
            terminology_enabled=False,
            glossary_enabled=False,
            review_enabled=False,
            inspection_enabled=False,
            extra={
                "mode": TranslationMode.V2_DUAL_DRAFT_REVIEW.value,
                "meaning_draft_enabled": True,
                "rag_evidence_count": len(rag_evidence),
                "translation_decision_count": len(translation_decisions),
                "author_review_card_count": 0,
            },
        )
        return V2DualDraftReviewResult(
            mode=TranslationMode.V2_DUAL_DRAFT_REVIEW.value,
            source_text=source_text,
            final_translation=direct_result.final_translation,
            meaning_draft=meaning_draft,
            rag_evidence=rag_evidence,
            translation_decisions=translation_decisions,
            author_review_cards=[],
            metadata=metadata,
            delivery_status=direct_result.delivery_status,
            user_visible_error_code=direct_result.user_visible_error_code,
        )

    def run_qa_only(self, source_text: str, translation_text: str) -> V2TranslationResult:
        risk_items = self.source_side_analyzer.analyze(source_text)
        qa_report = self.post_translation_qa.evaluate(source_text, translation_text, risk_items)
        user_visible_risk_items, hidden_risk_items = split_user_visible_risk_items(risk_items)
        user_visible_qa_report, hidden_qa_report = split_user_visible_qa_report(qa_report)
        patch_suggestions = self.patch_proposer.propose(translation_text, risk_items, qa_report)
        return V2TranslationResult(
            mode="qa_only",
            final_translation=translation_text,
            risk_items=[asdict(item) for item in risk_items],
            qa_report=[asdict(item) for item in qa_report],
            user_visible_risk_items=user_visible_risk_items,
            hidden_risk_items=hidden_risk_items,
            user_visible_qa_report=user_visible_qa_report,
            hidden_qa_report=hidden_qa_report,
            patch_suggestions=[asdict(item) for item in patch_suggestions],
            metadata=self._metadata(
                source_side_rag_enabled=True,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra={
                    "risk_item_count": len(risk_items),
                    "internal_risk_item_count": len(risk_items),
                    "user_visible_risk_item_count": len(user_visible_risk_items),
                    "hidden_risk_item_count": len(hidden_risk_items),
                    "qa_item_count": len(qa_report),
                    "user_visible_qa_count": sum(
                        len(rows) for key, rows in user_visible_qa_report.items() if key != "내부 디버그"
                    ),
                    "hidden_qa_count": len(hidden_qa_report),
                    "patch_suggestion_count": len(patch_suggestions),
                    **self._locale_adherence_metadata(
                        source_text=source_text,
                        final_translation=translation_text,
                        locale=self.config.resolved_resources().locale,
                        target_language_name=self.config.resolved_resources().target_language,
                    ),
                },
            ),
            draft=None,
        )
