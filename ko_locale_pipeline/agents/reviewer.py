from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import PipelineConfig
from ..text_processing.korean_output import koreanize_texts
from ..core.mock_adapters import review_payload
from ..core.openai_client import get_openai_client
from ..core.prompt_loader import load_runtime_prompt
from ..retrieval.retriever import RetrievalResult
from .translator import TranslationDraft


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "detected_constraints": {"type": "array", "items": {"type": "string"}},
        "risk_summary": {
            "type": "string",
            "description": "한국어 요약만 허용. 위험 설명은 반드시 한국어로 작성한다.",
        },
        "recommended_action": {"type": "string"},
        "revised_translation": {"type": "string"},
        "review_note": {
            "type": "string",
            "description": "한국어 검수 메모만 허용. 대상 번역문이 아닌 설명은 반드시 한국어로 작성한다.",
        },
    },
    "required": [
        "detected_constraints",
        "risk_summary",
        "recommended_action",
        "revised_translation",
        "review_note",
    ],
}


def extract_prompt_text(raw_text: str) -> str:
    triple_quote_match = re.search(r'BASE_REVIEW_PROMPT\s*=\s*"""(.*?)"""', raw_text, re.DOTALL)
    if triple_quote_match:
        return triple_quote_match.group(1).strip()

    fenced_match = re.search(r"```(?:python)?\s*(.*?)```", raw_text, re.DOTALL)
    if fenced_match:
        return extract_prompt_text(fenced_match.group(1))

    return raw_text.strip()


@dataclass(slots=True)
class ReviewResult:
    detected_constraints: list[str]
    risk_summary: str
    recommended_action: str
    revised_translation: str
    review_note: str
    raw_response: dict[str, Any]


class Reviewer:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.resources = config.resolved_resources()
        self.prompt_template = load_runtime_prompt("REVIEWER_PROMPT.md")
        self.common_korean_rule = load_runtime_prompt("COMMON_KOREAN_OUTPUT_RULE.md")

    @staticmethod
    def _load_review_prompt(path: Path) -> str:
        prompt_path = Path(path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"Review prompt not found: {prompt_path}")
        return extract_prompt_text(prompt_path.read_text(encoding="utf-8"))

    def review(
        self,
        source_text: str,
        draft: TranslationDraft,
        retrievals: list[RetrievalResult],
    ) -> ReviewResult:
        if self.config.mock:
            payload = review_payload(draft.translation)
            return ReviewResult(
                detected_constraints=payload["detected_constraints"],
                risk_summary=payload["risk_summary"],
                recommended_action=payload["recommended_action"],
                revised_translation=payload["revised_translation"],
                review_note=payload["review_note"],
                raw_response=payload["raw_response"],
            )

        client = get_openai_client()
        target_language = self.resources.target_language
        schema_name = f"{self.resources.locale}_review".replace("-", "_")
        reference_block = "\n".join(
            f"- {row.item.get('id', '')}: KO={', '.join(row.item.get('ko_anchor_expression', []) or row.item.get('ko_expression', []) or [])} | TARGET={row.item.get('expression', '')}"
            for row in retrievals
        ) or "- none"

        prompt = self.prompt_template.format(
            common_korean_rule=self.common_korean_rule,
            source_language=self.resources.source_language,
            target_language=target_language,
            source_text=source_text,
            draft_translation=draft.translation,
            reference_block=reference_block,
        )

        response = client.responses.create(
            model=self.config.review_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        self.resources.reviewer_system_prompt
                        + " All explanatory output fields must be written in Korean. "
                        + f"Only revised_translation may be in {target_language}."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": REVIEW_SCHEMA,
                    "strict": True,
                }
            },
        )
        payload = json.loads(response.output_text)
        payload["risk_summary"], payload["review_note"] = koreanize_texts(
            [payload["risk_summary"], payload["review_note"]],
            model=self.config.review_model,
        )
        return ReviewResult(
            detected_constraints=payload["detected_constraints"],
            risk_summary=payload["risk_summary"],
            recommended_action=payload["recommended_action"],
            revised_translation=payload["revised_translation"],
            review_note=payload["review_note"],
            raw_response=payload,
        )
