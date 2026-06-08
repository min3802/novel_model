from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.translation.infra.runtime import is_mock_mode

from ..config import ImageConfig
from ..infra._extract_base import call_structured, join_episodes
from ..infra.mock_adapters import relation_extraction_payload


@dataclass(slots=True)
class RelationNode:
    """관계도 노드(인물). 관계도엔 외형보다 식별·역할이 중요해 가볍게 둔다."""
    name: str
    role: str          # "주연" | "조연" 등. 불명확하면 "불명확"


@dataclass(slots=True)
class Relation:
    from_: str         # 관계 출발 인물(이름)
    to: str            # 관계 도착 인물(이름)
    relation_type: str # 관계 유형. 예: "설렘", "적대", "가족", "사제"
    directed: bool     # True=한쪽 방향(짝사랑 등), False=양방향 대칭
    evidence: str      # 그렇게 판단한 한국어 원문 근거 한 줄


@dataclass(slots=True)
class RelationExtractionResult:
    nodes: list[RelationNode] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(n) for n in self.nodes],
            "relations": [
                {"from": r.from_, "to": r.to, "relation_type": r.relation_type,
                 "directed": r.directed, "evidence": r.evidence}
                for r in self.relations
            ],
        }


RELATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "description": "인물 이름. 원문 표기 그대로."},
                    "role": {"type": "string", "description": "'주연' | '조연' | '단역' 등. 불명확하면 '불명확'."},
                },
                "required": ["name", "role"],
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "from": {"type": "string", "description": "관계 출발 인물(nodes 의 name 과 일치)."},
                    "to": {"type": "string", "description": "관계 도착 인물(nodes 의 name 과 일치)."},
                    "relation_type": {"type": "string", "description": "관계 유형. 예: '설렘','적대','가족','사제','동료'."},
                    "directed": {"type": "boolean",
                                 "description": "한쪽 방향이면 true(짝사랑 등 from→to), 양방향 대칭이면 false."},
                    "evidence": {"type": "string", "description": "그 관계로 판단한 한국어 원문 근거 한 줄."},
                },
                "required": ["from", "to", "relation_type", "directed", "evidence"],
            },
        },
    },
    "required": ["nodes", "relations"],
}

_SYSTEM = (
    "당신은 한국어 웹소설 원문에서 인물 간 '관계도'를 그리기 위한 관계 정보를 뽑는 분석가입니다. "
    "여러 화에 걸친 관계 변화를 누적해 파악하세요. 원문 근거가 있는 관계만, 지어내지 마세요. "
    "짝사랑처럼 한쪽만 성립하면 directed=true, 서로 대칭이면 false. "
    "모든 설명은 한국어로, JSON 만 반환합니다."
)


class RelationExtractor:
    """관계도 플로우 ①추출. 최대 20화 분량에서 인물·관계 추출(누적).

    추출 결과는 관계도 생성 후 휘발한다(저장 책임 없음).
    """

    def __init__(self, config: ImageConfig | None = None) -> None:
        self.config = config or ImageConfig()

    def extract(self, episodes: str | list[str]) -> RelationExtractionResult:
        source = join_episodes(episodes, max_episodes=self.config.relation_max_episodes)
        if not source.strip():
            raise ValueError("관계도 추출할 원문이 비어 있습니다.")

        if is_mock_mode():
            payload = relation_extraction_payload(source, self.config)
        else:
            payload = call_structured(
                self.config.extract_model, _SYSTEM,
                self._build_prompt(source), "webnovel_relation_extraction", RELATION_SCHEMA,
            )
        return self._result(payload)

    @staticmethod
    def _build_prompt(source: str) -> str:
        return (
            "아래 한국어 웹소설 원문(최대 20화 분량)에서 인물 관계도를 그릴 정보를 추출하세요.\n\n"
            "[규칙]\n"
            "- nodes: 관계도에 등장할 인물과 비중(role).\n"
            "- relations: 원문 근거가 있는 인물 쌍의 관계만.\n"
            "- 짝사랑·일방적 감정이면 directed=true(from→to), 대칭이면 false.\n"
            "- evidence: 그 관계로 본 한국어 원문 근거 한 줄.\n\n"
            f"[원문]\n{source}"
        )

    @staticmethod
    def _result(payload: dict[str, Any]) -> RelationExtractionResult:
        nodes = [
            RelationNode(
                name=str(n.get("name", "")).strip(),
                role=str(n.get("role", "")).strip() or "불명확",
            )
            for n in (payload.get("nodes") or [])
            if str(n.get("name", "")).strip()
        ]
        relations = [
            Relation(
                from_=str(r.get("from", "")).strip(),
                to=str(r.get("to", "")).strip(),
                relation_type=str(r.get("relation_type", "불명확")).strip() or "불명확",
                directed=bool(r.get("directed", False)),
                evidence=str(r.get("evidence", "")).strip(),
            )
            for r in (payload.get("relations") or [])
            if str(r.get("from", "")).strip() and str(r.get("to", "")).strip()
        ]
        return RelationExtractionResult(
            nodes=nodes, relations=relations, raw_response=payload.get("raw_response", {}) or {}
        )
