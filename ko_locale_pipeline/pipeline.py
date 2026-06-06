from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .annotation_retriever import AnnotationRetriever, AnnotationResult
from .config import PipelineConfig
from .chatbot import ChatbotAgent
from .cultural_lexicon import CulturalLexicon
from .inspector import InspectionAgent
from .retriever import DenseRetriever, RetrievalResult
from .reviewer import Reviewer
from .translator import Translator


@dataclass(slots=True)
class PipelineResult:
    source_text: str
    retrievals: list[dict[str, Any]]
    draft: dict[str, Any]
    review: dict[str, Any]
    final_translation: str


@dataclass(slots=True)
class AgentWorkflowResult:
    source_text: str
    retrievals: list[dict[str, Any]]
    cultural_matches: list[dict[str, Any]]
    annotation_matches: list[dict[str, Any]]
    draft: dict[str, Any]
    translation_review: dict[str, Any]
    inspection: dict[str, Any]
    reviewed_translation: str
    context_extraction: dict[str, Any] | None = None
    memory_context: str = ""


class KoJaPipeline:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.retriever = DenseRetriever(self.config)
        self.annotation_retriever = AnnotationRetriever(self.config)
        self.cultural_lexicon = CulturalLexicon(self.config)
        self.translator = Translator(self.config)
        self.reviewer = Reviewer(self.config)
        self.inspector = InspectionAgent(self.config)
        self.chatbot = ChatbotAgent(self.config)

    def run(self, source_text: str) -> PipelineResult:
        retrievals = self.retriever.retrieve(source_text, top_k=self.config.top_k)
        draft = self.translator.translate(source_text, retrievals)
        review = self.reviewer.review(source_text, draft, retrievals)
        return PipelineResult(
            source_text=source_text,
            retrievals=[self._retrieval_to_dict(row) for row in retrievals],
            draft=asdict(draft),
            review=asdict(review),
            final_translation=review.revised_translation or draft.translation,
        )

    def run_with_inspection(
        self,
        source_text: str,
        *,
        translation_memory: list[dict[str, Any]] | None = None,
        memory_context: str = "",
        retrieval_queries: list[str] | None = None,
        context_extraction: dict[str, Any] | None = None,
    ) -> AgentWorkflowResult:
        """Run translation plus independent inspection without auto-finalizing changes."""
        retrieval_query = "\n".join([source_text, *(retrieval_queries or [])]).strip()
        cultural_matches = self.cultural_lexicon.lookup(source_text)
        annotation_matches = self.annotation_retriever.retrieve(
            retrieval_query or source_text,
            top_k=self.config.annotation_top_k,
        )
        cultural_context = self._build_cultural_context(cultural_matches, annotation_matches)
        retrievals = self.retriever.retrieve(retrieval_query or source_text, top_k=self.config.top_k)
        draft = self.translator.translate(
            source_text,
            retrievals,
            memory_context=memory_context,
            cultural_context=cultural_context,
        )
        review = self.reviewer.review(source_text, draft, retrievals)
        retrieval_dicts = [self._retrieval_to_dict(row) for row in retrievals]
        used_references = [
            {
                "id": row["item"].get("id"),
                "ko_anchor_expression": row["item"].get("ko_anchor_expression", []),
                "target_expression": row["item"].get("expression", ""),
                "score": row["score"],
            }
            for row in retrieval_dicts
        ]
        inspection = self.inspector.inspect(
            source_text=source_text,
            draft_translation=draft.translation,
            reviewed_translation=review.revised_translation,
            translation_rationale=draft.rationale,
            used_references=used_references,
            translation_memory=translation_memory or [],
        )
        return AgentWorkflowResult(
            source_text=source_text,
            retrievals=retrieval_dicts,
            cultural_matches=[match.to_dict() for match in cultural_matches],
            annotation_matches=[self._annotation_to_dict(row) for row in annotation_matches],
            draft=asdict(draft),
            translation_review=asdict(review),
            inspection=inspection.to_dict(),
            reviewed_translation=self._select_reviewed_translation(
                draft_translation=draft.translation,
                translation_review=review.revised_translation,
                inspection=inspection.to_dict(),
            ),
            context_extraction=context_extraction,
            memory_context=memory_context,
        )

    @staticmethod
    def _retrieval_to_dict(row: RetrievalResult) -> dict[str, Any]:
        return {
            "score": row.score,
            "similarity_score": row.similarity_score,
            "anchor_boost": row.anchor_boost,
            "final_score": row.final_score,
            "item": row.item,
        }

    @staticmethod
    def _annotation_to_dict(row: AnnotationResult) -> dict[str, Any]:
        return {
            "score": row.score,
            "similarity_score": row.similarity_score,
            "trigger_boost": row.trigger_boost,
            "final_score": row.final_score,
            "item": row.item,
        }

    @staticmethod
    def _build_cultural_context(
        cultural_matches: list[Any],
        annotation_matches: list[AnnotationResult],
    ) -> str:
        return "\n\n".join(
            [
                CulturalLexicon.build_context(cultural_matches),
                AnnotationRetriever.build_context(annotation_matches),
            ]
        )

    @staticmethod
    def _select_reviewed_translation(
        *,
        draft_translation: str,
        translation_review: str,
        inspection: dict[str, Any],
    ) -> str:
        """Only auto-apply inspection revisions when the inspector explicitly says so."""
        baseline = translation_review or draft_translation
        if inspection.get("intervention_policy") == "AUTO_APPLIED":
            return inspection.get("revised_translation") or baseline
        return baseline


class KoLocalePipeline(KoJaPipeline):
    """Locale-driven alias for the legacy KoJaPipeline name."""
