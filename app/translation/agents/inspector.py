from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from ..config import PipelineConfig
from ..text_processing.korean_output import koreanize_texts
from ..infra.mock_adapters import inspection_payload
from ..infra.openai_client import get_openai_client
from ..infra.prompt_loader import load_base_review_prompt, load_locale_constraints, load_runtime_prompt


INSPECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "locale": {"type": "string"},
        "context_analysis": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "speaker": {
                    "type": "string",
                    "description": "원문 근거로 확인한 화자. 불명확하면 '불명확'이라고 쓴다.",
                },
                "listener": {
                    "type": "string",
                    "description": "원문 근거로 확인한 청자. 불명확하면 '불명확'이라고 쓴다.",
                },
                "relationship": {
                    "type": "string",
                    "description": "화자와 청자 관계. 단정할 수 없으면 추정이라고 표시한다.",
                },
                "confidence": {
                    "type": "string",
                    "description": "high | medium | low 중 하나.",
                },
                "evidence": {
                    "type": "string",
                    "description": "화자/청자/관계를 판단한 한국어 원문 근거. 반드시 한국어로 쓴다.",
                },
            },
            "required": ["speaker", "listener", "relationship", "confidence", "evidence"],
        },
        "detected_constraints": {"type": "array", "items": {"type": "string"}},
        "severity": {"type": "string"},
        "recommended_action": {"type": "string"},
        "intervention_policy": {
            "type": "string",
            "description": "AUTO_APPLIED | USER_DECISION | INFO_ONLY 중 하나. 자동 반영 여부 정책.",
        },
        "risk_summary": {
            "type": "string",
            "description": "한국어 요약만 허용. 검수 요약은 반드시 한국어로 작성한다.",
        },
        "problematic_spans": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source_text": {"type": "string"},
                    "translated_text": {"type": "string"},
                    "issue": {
                        "type": "string",
                        "description": "한국어 설명만 허용. 문제 사유는 반드시 한국어로 작성한다.",
                    },
                    "constraint_id": {"type": "string"},
                    "severity": {"type": "string"},
                },
                "required": [
                    "source_text",
                    "translated_text",
                    "issue",
                    "constraint_id",
                    "severity",
                ],
            },
        },
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "original": {"type": "string"},
                    "suggested": {"type": "string"},
                    "reason": {
                        "type": "string",
                        "description": "한국어 설명만 허용. 수정 이유는 반드시 한국어로 작성한다.",
                    },
                },
                "required": ["original", "suggested", "reason"],
            },
        },
        "revised_translation": {"type": "string"},
        "review_note": {
            "type": "string",
            "description": "한국어 검수 메모만 허용.",
        },
    },
    "required": [
        "locale",
        "context_analysis",
        "detected_constraints",
        "severity",
        "recommended_action",
        "intervention_policy",
        "risk_summary",
        "problematic_spans",
        "suggestions",
        "revised_translation",
        "review_note",
    ],
}


@dataclass(slots=True)
class ContextAnalysis:
    speaker: str
    listener: str
    relationship: str
    confidence: str
    evidence: str


@dataclass(slots=True)
class ProblematicSpan:
    source_text: str
    translated_text: str
    issue: str
    constraint_id: str
    severity: str


@dataclass(slots=True)
class InspectionSuggestion:
    original: str
    suggested: str
    reason: str


@dataclass(slots=True)
class InspectionResult:
    locale: str
    context_analysis: ContextAnalysis
    detected_constraints: list[str]
    severity: str
    recommended_action: str
    intervention_policy: str
    risk_summary: str
    problematic_spans: list[ProblematicSpan]
    suggestions: list[InspectionSuggestion]
    revised_translation: str
    review_note: str
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InspectionAgent:
    """Independent cultural/localization inspection agent for translated output."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.resources = config.resolved_resources()
        self.base_prompt = load_base_review_prompt(config)
        self.locale_constraints = load_locale_constraints(self.resources.locale)
        self.prompt_template = load_runtime_prompt("INSPECTOR_PROMPT.md")
        self.common_korean_rule = load_runtime_prompt("COMMON_KOREAN_OUTPUT_RULE.md")

    def inspect(
        self,
        *,
        source_text: str,
        draft_translation: str,
        reviewed_translation: str | None = None,
        translation_rationale: str = "",
        used_references: list[dict[str, Any]] | None = None,
        translation_memory: list[dict[str, Any]] | None = None,
    ) -> InspectionResult:
        translation_to_review = reviewed_translation or draft_translation
        if self.config.mock:
            payload = inspection_payload(self.resources, source_text, translation_to_review)
            return self._result_from_payload(payload)

        client = get_openai_client()
        schema_name = f"{self.resources.locale}_inspection".replace("-", "_")
        prompt = self._build_prompt(
            source_text=source_text,
            draft_translation=draft_translation,
            reviewed_translation=translation_to_review,
            translation_rationale=translation_rationale,
            used_references=used_references or [],
            translation_memory=translation_memory or [],
        )
        response = client.responses.create(
            model=self.config.review_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        f"You are an independent {self.resources.target_language} "
                        "localization inspection agent. Return JSON only. "
                        "All explanatory fields must be written in Korean. "
                        f"Only revised_translation and suggested target text may be in {self.resources.target_language}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": INSPECTION_SCHEMA,
                    "strict": True,
                }
            },
        )
        payload = json.loads(response.output_text)
        self._koreanize_payload(payload)
        return self._result_from_payload(payload)

    def _build_prompt(
        self,
        *,
        source_text: str,
        draft_translation: str,
        reviewed_translation: str,
        translation_rationale: str,
        used_references: list[dict[str, Any]],
        translation_memory: list[dict[str, Any]],
    ) -> str:
        references_json = json.dumps(used_references, ensure_ascii=False, indent=2)
        memory_json = json.dumps(translation_memory, ensure_ascii=False, indent=2)
        return self.prompt_template.format(
            common_korean_rule=self.common_korean_rule,
            base_prompt=self.base_prompt,
            locale_constraints=self.locale_constraints,
            source_language=self.resources.source_language,
            target_language=self.resources.target_language,
            source_text=source_text,
            draft_translation=draft_translation,
            reviewed_translation=reviewed_translation,
            translation_rationale=translation_rationale or "- none",
            references_json=references_json,
            memory_json=memory_json,
        )

    def _koreanize_payload(self, payload: dict[str, Any]) -> None:
        context = payload.get("context_analysis", {})
        context_fields = ["speaker", "listener", "relationship", "evidence"]
        texts: list[str] = [str(context.get(field, "")) for field in context_fields]
        texts.extend([payload["risk_summary"], payload["review_note"]])
        issue_indexes: list[int] = []
        reason_indexes: list[int] = []

        for idx, row in enumerate(payload.get("problematic_spans", [])):
            issue_indexes.append(idx)
            texts.append(row.get("issue", ""))

        for idx, row in enumerate(payload.get("suggestions", [])):
            reason_indexes.append(idx)
            texts.append(row.get("reason", ""))

        translated = koreanize_texts(texts, model=self.config.review_model)
        cursor = 0
        for field in context_fields:
            if context:
                context[field] = translated[cursor]
            cursor += 1
        payload["risk_summary"] = translated[cursor]
        cursor += 1
        payload["review_note"] = translated[cursor]
        cursor += 1

        for idx in issue_indexes:
            payload["problematic_spans"][idx]["issue"] = translated[cursor]
            cursor += 1

        for idx in reason_indexes:
            payload["suggestions"][idx]["reason"] = translated[cursor]
            cursor += 1

    @staticmethod
    def _result_from_payload(payload: dict[str, Any]) -> InspectionResult:
        return InspectionResult(
            locale=payload["locale"],
            context_analysis=ContextAnalysis(
                speaker=payload["context_analysis"]["speaker"],
                listener=payload["context_analysis"]["listener"],
                relationship=payload["context_analysis"]["relationship"],
                confidence=payload["context_analysis"]["confidence"],
                evidence=payload["context_analysis"]["evidence"],
            ),
            detected_constraints=payload["detected_constraints"],
            severity=payload["severity"],
            recommended_action=payload["recommended_action"],
            intervention_policy=payload["intervention_policy"],
            risk_summary=payload["risk_summary"],
            problematic_spans=[
                ProblematicSpan(
                    source_text=row["source_text"],
                    translated_text=row["translated_text"],
                    issue=row["issue"],
                    constraint_id=row["constraint_id"],
                    severity=row["severity"],
                )
                for row in payload["problematic_spans"]
            ],
            suggestions=[
                InspectionSuggestion(
                    original=row["original"],
                    suggested=row["suggested"],
                    reason=row["reason"],
                )
                for row in payload["suggestions"]
            ],
            revised_translation=payload["revised_translation"],
            review_note=payload["review_note"],
            raw_response=payload,
        )
