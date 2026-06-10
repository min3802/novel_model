from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .agents.chatbot import ChatbotAgent
from .agents.inspector import InspectionAgent
from .agents.translator import Translator
from .config import PipelineConfig
from .retrieval.annotation_retriever import AnnotationRetriever
from .retrieval.retriever import IdiomRetriever
from .translation_graph import TranslationGraph


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


class TranslationPipeline:
    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.retriever = IdiomRetriever(self.config)
        self.annotation_retriever = AnnotationRetriever(self.config)
        self.translator = Translator(self.config)
        self.inspector = InspectionAgent(self.config)
        self.chatbot = ChatbotAgent(self.config)
        self.graph = TranslationGraph(
            self.config,
            retriever=self.retriever,
            annotation_retriever=self.annotation_retriever,
            translator=self.translator,
            inspector=self.inspector,
        )

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
        """Run the deterministic translation graph and return the workflow artifact."""
        return self.graph.run_with_inspection(
            source_text,
            request_payload=request_payload,
            translation_memory=translation_memory,
            memory_context=memory_context,
            retrieval_queries=retrieval_queries,
            context_extraction=context_extraction,
        )

