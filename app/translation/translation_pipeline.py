from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from .retrieval.annotation_retriever import AnnotationRetriever, AnnotationResult
from .config import PipelineConfig
from .agents.chatbot import ChatbotAgent
from .agents.inspector import InspectionAgent
from .retrieval.retriever import IdiomRetriever, RetrievalResult, embed_query
from .agents.reviewer import Reviewer
from .agents.translator import Translator


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
    annotation_matches: list[dict[str, Any]]
    draft: dict[str, Any]
    translation_review: dict[str, Any]
    inspection: dict[str, Any]
    reviewed_translation: str
    context_extraction: dict[str, Any] | None = None
    memory_context: str = ""


class TranslationPipeline:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.retriever = IdiomRetriever(self.config)
        self.annotation_retriever = AnnotationRetriever(self.config)
        self.translator = Translator(self.config)
        self.reviewer = Reviewer(self.config)
        self.inspector = InspectionAgent(self.config)
        self.chatbot = ChatbotAgent(self.config)

    def run(self, source_text: str) -> PipelineResult:
        retrievals = self.retriever.retrieve(source_text)
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
        query = retrieval_query or source_text

        # 쿼리 임베딩은 무거운 작업(KURE 추론)이므로 1회만 수행하고,
        # idiom/annotation 두 검색이 같은 (chunks, vectors)를 공유한다.
        # (이전엔 두 retriever가 같은 문장을 각자 임베딩 → 중복. 이를 제거.)
        chunks, chunk_vectors = embed_query(
            self.retriever.backend, self.retriever._chunk_query, query
        )

        # 임베딩 이후 남는 두 검색(idiom/annotation)을 공유 벡터로 병렬 실행한다.
        # (qdrant 동시 읽기 안전성 검증됨.)
        # NOTE: cultural_lexicon(사전 매칭)은 현재 파이프라인에서 제외됨.
        #   - 데이터가 5개·draft 상태의 초기/구버전 산물로 판단되어 비활성화.
        #   - annotation_retriever(kculture 임베딩 검색)가 문화 맥락을 담당한다.
        with ThreadPoolExecutor(max_workers=2) as executor:
            annotation_future = executor.submit(
                self.annotation_retriever.search, chunks, chunk_vectors,
            )
            idiom_future = executor.submit(
                self.retriever.search, chunks, chunk_vectors
            )
            annotation_matches = annotation_future.result()
            retrievals = idiom_future.result()

        cultural_context = self._build_cultural_context(annotation_matches)
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
                # qdrant idiom payload는 평면 구조. source_id/embedding_text 사용.
                "id": row["item"].get("source_id", row["item"].get("id")),
                "reference_text": row["item"].get("embedding_text", ""),
                "original_meaning": row["item"].get("original_meaning", ""),
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
    def _build_cultural_context(annotation_matches: list[AnnotationResult]) -> str:
        # cultural_lexicon 제외 후 annotation_retriever(kculture)만 문화 맥락을 담당.
        return AnnotationRetriever.build_context(annotation_matches)

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


