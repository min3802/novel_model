from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from .retrieval.annotation_retriever import AnnotationRetriever, AnnotationResult
from .config import PipelineConfig
from .agents.chatbot import ChatbotAgent
from .agents.inspector import InspectionAgent
from .retrieval.retriever import IdiomRetriever, RetrievalResult, embed_query
from .text_processing.korean_output import is_korean_source
from .agents.translator import Translator


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


class TranslationPipeline:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.retriever = IdiomRetriever(self.config)
        self.annotation_retriever = AnnotationRetriever(self.config)
        self.translator = Translator(self.config)
        self.inspector = InspectionAgent(self.config)
        self.chatbot = ChatbotAgent(self.config)

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
        # 입력 언어 검증: 한국어 원문만 번역 가능. 한글 비중 0.5 미만이면 차단.
        # (모델 처리 불가 여부만 판단해 신호 반환. 사용자 응답 포장은 호출측/backend 담당.)
        if not is_korean_source(source_text):
            return AgentWorkflowResult(
                source_text=source_text,
                retrievals=[],
                annotation_matches=[],
                draft={},
                inspection={},
                reviewed_translation="",
                context_extraction=context_extraction,
                memory_context=memory_context,
                blocked=True,
                block_reason="non_korean_source",
            )
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

        # annotation_matches(한국 문화 주석 후보)는 번역 대체어가 아니라 "독자용 문화 설명"이므로
        # Translator 입력에 넣지 않는다. 사용자 채택용 주석 후보군으로만 결과에 실어 보낸다.
        # 번역은 원문 + idiom RAG(retrievals) + 용어집(memory_context)만으로 수행한다.
        draft = self.translator.translate(
            source_text,
            retrievals,
            memory_context=memory_context,
        )
        retrieval_dicts = [self._retrieval_to_dict(row) for row in retrievals]
        # Inspector는 전체 재번역을 하지 않는다. draft 번역을 검사해 span 단위 issue만 반환한다.
        # (RAG references 는 검수 입력에서 제외 — 번역 단계 산물이라 검수에는 과한 맥락.)
        inspection = self.inspector.inspect(
            source_text=source_text,
            draft_translation=draft.translation,
            translation_rationale=draft.rationale,
            translation_memory=translation_memory or [],
        )
        return AgentWorkflowResult(
            source_text=source_text,
            retrievals=retrieval_dicts,
            annotation_matches=[self._annotation_to_dict(row) for row in annotation_matches],
            draft=asdict(draft),
            # Reviewer 제거: 전체 번역문을 생성하는 LLM 호출은 Translator 1회로 일원화.
            inspection=inspection.to_dict(),
            # 전체 번역문은 draft 하나뿐. Inspector는 span 제안만 하므로 draft를 그대로 최종본으로 쓴다.
            reviewed_translation=draft.translation,
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



