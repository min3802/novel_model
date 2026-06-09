from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..config import PipelineConfig
from ..text_processing.korean_output import koreanize_text
from ..infra.mock_adapters import translation_payload
from ..infra.openai_client import get_openai_client
from ..infra.prompt_loader import load_runtime_prompt
from ..retrieval.retriever import IdiomRetriever, RetrievalResult


TRANSLATOR_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translation": {"type": "string"},
        "strategy": {"type": "string"},
        "rationale": {
            "type": "string",
            "description": "한국어 설명만 허용. 대상 언어가 무엇이든 번역 이유와 전략 설명은 반드시 한국어로 작성한다.",
        },
        "reference_ids": {"type": "array", "items": {"type": "string"}},
        "translation_decisions": {
            "type": "array",
            "description": "원문 표현, RAG 근거, 번역 표현, 변경 이유를 연결한 의사결정 목록.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source_span": {"type": "string"},
                    "reference_id": {"type": "string"},
                    "reference_expression": {"type": "string"},
                    "translated_span": {"type": "string"},
                    "decision_type": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "description": "한국어 설명만 허용. 왜 이렇게 바꿨는지 한국어로 작성한다.",
                    },
                },
                "required": [
                    "source_span",
                    "reference_id",
                    "reference_expression",
                    "translated_span",
                    "decision_type",
                    "reason",
                ],
            },
        },
    },
    "required": [
        "translation",
        "strategy",
        "rationale",
        "reference_ids",
        "translation_decisions",
    ],
}


@dataclass(slots=True)
class TranslationDraft:
    translation: str
    strategy: str
    rationale: str
    reference_ids: list[str]
    translation_decisions: list[dict[str, str]]
    raw_response: dict[str, Any]


class Translator:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.resources = config.resolved_resources()
        self.prompt_template = load_runtime_prompt("TRANSLATOR_PROMPT.md")
        self.common_korean_rule = load_runtime_prompt("COMMON_KOREAN_OUTPUT_RULE.md")

    def translate(
        self,
        source_text: str,
        retrievals: list[RetrievalResult],
        *,
        memory_context: str = "",
    ) -> TranslationDraft:
        reference_ids = [str(row.item.get("source_id") or row.item.get("id") or "") for row in retrievals if (row.item.get("source_id") or row.item.get("id"))]
        if self.config.mock:
            payload = translation_payload(self.config, self.resources, source_text, retrievals)
            return TranslationDraft(
                translation=payload["translation"],
                strategy=payload["strategy"],
                rationale=payload["rationale"],
                reference_ids=payload["reference_ids"],
                translation_decisions=payload["translation_decisions"],
                raw_response=payload["raw_response"],
            )

        client = get_openai_client()
        context = IdiomRetriever.build_context(retrievals)
        if memory_context.strip():
            context = "\n\n[작품 메모리 / 온톨로지 참고]\n" + memory_context.strip() + "\n\n[RAG 참고]\n" + context
        target_language = self.resources.target_language
        schema_name = f"{self.resources.locale}_translation".replace("-", "_")
        prompt = self.prompt_template.format(
            common_korean_rule=self.common_korean_rule,
            source_language=self.resources.source_language,
            target_language=target_language,
            source_text=source_text,
            rag_context=context,
        )

        response = client.responses.create(
            model=self.config.translation_model,
            input=[
                {"role": "system", "content": self.resources.translator_system_prompt},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": TRANSLATOR_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        payload = json.loads(response.output_text)
        payload["rationale"] = koreanize_text(payload["rationale"], model=self.config.review_model)
        for decision in payload.get("translation_decisions", []):
            decision["reason"] = koreanize_text(decision.get("reason", ""), model=self.config.review_model)
        return TranslationDraft(
            translation=payload["translation"],
            strategy=payload["strategy"],
            rationale=payload["rationale"],
            reference_ids=payload["reference_ids"],
            translation_decisions=payload["translation_decisions"],
            raw_response=payload,
        )
