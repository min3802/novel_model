from __future__ import annotations

from typing import Any


def _excerpt(text: str) -> str:
    return text.strip().replace("\n", " ")[:40]


def cover_extraction_payload(source_text: str, config: Any) -> dict[str, Any]:
    """표지 추출 mock. 실제 스키마와 동일 구조의 결정적 응답."""
    return {
        "characters": [
            {
                "name": "주인공",
                "gender": "불명확",
                "age_estimate": "불명확",
                "appearance": ["원문 묘사 기반 외형(mock)"],
                "personality": "불명확",
                "role": "주연",
                "arc_summary": f"이 분량에서의 행보(mock). 원문 발췌: {_excerpt(source_text)}…",
                "key_moments": ["임팩트 있는 장면(mock)"],
            }
        ],
        "raw_response": {"mock": True, "input_chars": len(source_text)},
    }


def relation_extraction_payload(source_text: str, config: Any) -> dict[str, Any]:
    """관계도 추출 mock. 실제 스키마와 동일 구조의 결정적 응답."""
    return {
        "nodes": [
            {"name": "주인공", "role": "주연"},
            {"name": "상대역", "role": "조연"},
        ],
        "relations": [
            {
                "from": "주인공",
                "to": "상대역",
                "relation_type": "불명확",
                "directed": False,
                "evidence": f"mock 결정적 응답 (원문 발췌: {_excerpt(source_text)}…)",
            }
        ],
        "raw_response": {"mock": True, "input_chars": len(source_text)},
    }
