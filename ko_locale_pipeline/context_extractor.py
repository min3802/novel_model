from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import PipelineConfig
from .openai_client import get_openai_client


CONTEXT_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "role": {"type": "string"},
                    "traits": {"type": "array", "items": {"type": "string"}},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "role", "traits", "aliases", "confidence", "status", "evidence"],
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "relation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["from", "to", "relation", "confidence", "status", "evidence"],
            },
        },
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "type": {"type": "string"},
                    "meaning": {"type": "string"},
                    "policy": {"type": "string"},
                    "recommendedTranslation": {"type": "string"},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "source",
                    "type",
                    "meaning",
                    "policy",
                    "recommendedTranslation",
                    "confidence",
                    "status",
                    "evidence",
                ],
            },
        },
        "speechStyles": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "character": {"type": "string"},
                    "summary": {"type": "string"},
                    "rules": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["character", "summary", "rules", "confidence", "status", "evidence"],
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "participants": {"type": "array", "items": {"type": "string"}},
                    "stateChange": {"type": "string"},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "summary", "participants", "stateChange", "confidence", "status", "evidence"],
            },
        },
        "translationPolicies": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "policy": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                    "status": {"type": "string"},
                },
                "required": ["source", "target", "policy", "reason", "confidence", "status"],
            },
        },
        "ragQueries": {
            "type": "array",
            "description": "RAG 검색에 사용할 짧은 질의. 관용어, 문화어, 시대/관계 맥락을 포함한다.",
            "items": {"type": "string"},
        },
    },
    "required": [
        "characters",
        "relations",
        "terms",
        "speechStyles",
        "events",
        "translationPolicies",
        "ragQueries",
    ],
}


@dataclass(slots=True)
class ContextExtraction:
    characters: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    terms: list[dict[str, Any]]
    speechStyles: list[dict[str, Any]]
    events: list[dict[str, Any]]
    translationPolicies: list[dict[str, Any]]
    ragQueries: list[str]
    raw_response: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "characters": self.characters,
            "relations": self.relations,
            "terms": self.terms,
            "speechStyles": self.speechStyles,
            "events": self.events,
            "translationPolicies": self.translationPolicies,
            "ragQueries": self.ragQueries,
            "raw_response": self.raw_response,
        }


class ContextExtractor:
    """Extract candidate work-memory facts and retrieval queries from the current source chunk."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.resources = config.resolved_resources()

    def extract(self, source_text: str, *, existing_memory_context: str = "") -> ContextExtraction:
        if self.config.mock:
            return self._mock_extract(source_text)

        client = get_openai_client()
        prompt = f"""
다음 원문 일부를 번역하기 전에 작품 메모리 후보와 RAG 검색 질의를 추출하세요.
사용자에게 확정된 사실처럼 말하지 말고, 모든 신규 항목의 status는 suggested로 둡니다.
확신이 낮은 항목은 confidence를 낮게 표시하고, 근거 문장을 evidence에 짧게 넣습니다.

[기존 작품 메모리]
{existing_memory_context or "없음"}

[원문]
{source_text}
""".strip()
        response = client.responses.create(
            model=self.config.review_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are a localization context extraction agent. "
                        "Return JSON only. Korean explanations are allowed in values."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "work_memory_context_extraction",
                    "schema": CONTEXT_EXTRACTION_SCHEMA,
                    "strict": True,
                }
            },
        )
        payload = json.loads(response.output_text)
        return self._from_payload(payload)

    def _mock_extract(self, source_text: str) -> ContextExtraction:
        names = self._candidate_korean_names(source_text)
        characters = [
            {
                "name": name,
                "role": "작품 내 주요 인물 후보",
                "traits": [],
                "aliases": [],
                "confidence": 0.55,
                "status": "suggested",
                "evidence": [self._first_evidence(source_text, name)],
            }
            for name in names[:5]
        ]
        terms = []
        for term, term_type, meaning, policy in self._candidate_terms(source_text):
            terms.append(
                {
                    "source": term,
                    "type": term_type,
                    "meaning": meaning,
                    "policy": policy,
                    "recommendedTranslation": "",
                    "confidence": 0.6,
                    "status": "suggested",
                    "evidence": [self._first_evidence(source_text, term)],
                }
            )
        rag_queries = [term["source"] for term in terms]
        rag_queries.extend(names[:3])
        if source_text.strip():
            rag_queries.append(source_text.strip()[:160])
        return self._from_payload(
            {
                "characters": characters,
                "relations": [],
                "terms": terms,
                "speechStyles": [],
                "events": [],
                "translationPolicies": [],
                "ragQueries": [q for q in rag_queries if q],
            }
        )

    @staticmethod
    def _from_payload(payload: dict[str, Any]) -> ContextExtraction:
        return ContextExtraction(
            characters=list(payload.get("characters") or []),
            relations=list(payload.get("relations") or []),
            terms=list(payload.get("terms") or []),
            speechStyles=list(payload.get("speechStyles") or []),
            events=list(payload.get("events") or []),
            translationPolicies=list(payload.get("translationPolicies") or []),
            ragQueries=list(payload.get("ragQueries") or []),
            raw_response=payload,
        )

    @staticmethod
    def _candidate_korean_names(text: str) -> list[str]:
        candidates: list[str] = []
        particles = r"(?:은|는|이|가|을|를|에게|와|과|의|도|만|께서)"
        for match in re.finditer(rf"([가-힣]{{2,4}}){particles}", text):
            value = match.group(1)
            if value in {"그것", "오늘", "어제", "내일", "사람", "문장", "원문", "아내"}:
                continue
            if value not in candidates:
                candidates.append(value)
        if "아내" in text and "아내" not in candidates:
            candidates.append("아내")
        return candidates

    @staticmethod
    def _candidate_terms(text: str) -> list[tuple[str, str, str, str]]:
        seed_terms = {
            "설렁탕": ("cultural_term", "한국 음식이자 작품 내 상징일 수 있음", "음차 유지 여부와 설명 필요성을 검토"),
            "인력거": ("cultural_term", "시대/계층 배경을 드러내는 이동 수단", "직역보다 시대 맥락을 살려 번역"),
            "정": ("cultural_concept", "한국적 정서 개념", "문맥에 맞춰 설명 또는 의역"),
            "체면": ("cultural_concept", "사회적 얼굴/명예 개념", "대상 문화권에 맞춘 의역"),
        }
        rows: list[tuple[str, str, str, str]] = []
        for term, values in seed_terms.items():
            if term in text:
                rows.append((term, *values))
        return rows

    @staticmethod
    def _first_evidence(text: str, needle: str) -> str:
        if not needle:
            return text.strip()[:120]
        idx = text.find(needle)
        if idx < 0:
            return text.strip()[:120]
        start = max(0, idx - 40)
        end = min(len(text), idx + len(needle) + 40)
        return text[start:end].strip()
