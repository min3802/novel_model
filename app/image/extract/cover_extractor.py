from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.translation.infra.runtime import is_mock_mode

from ..config import ImageConfig
from ..infra._extract_base import call_structured, join_episodes
from ..infra.mock_adapters import cover_extraction_payload


@dataclass(slots=True)
class CoverCharacter:
    name: str
    gender: str                 # "남" | "여" | "불명확"
    age_estimate: str           # 예: "20대 초반(추정)" | "불명확"
    appearance: list[str]       # 외형 특징
    personality: str            # 성격. 불명확하면 "불명확"
    role: str                   # "주연" | "조연" 등
    arc_summary: str            # 해당 분량(최대 10화)에서 이 인물의 행보 한 줄
    key_moments: list[str]      # 임팩트 있는 장면/모습 리스트


@dataclass(slots=True)
class CoverExtractionResult:
    characters: list[CoverCharacter] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"characters": [asdict(c) for c in self.characters]}

    def protagonist(self) -> CoverCharacter | None:
        """표지 주인공(주연 우선, 없으면 첫 캐릭터)."""
        for c in self.characters:
            if c.role.startswith("주"):
                return c
        return self.characters[0] if self.characters else None


COVER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "description": "등장인물 이름. 원문 표기 그대로."},
                    "gender": {"type": "string", "description": "'남' | '여' | '불명확'."},
                    "age_estimate": {"type": "string", "description": "추정 나이대. 단정 불가하면 '불명확'."},
                    "appearance": {"type": "array", "items": {"type": "string"},
                                   "description": "원문 근거가 있는 외형 특징. 없으면 빈 배열."},
                    "personality": {"type": "string", "description": "성격 요약. 근거 없으면 '불명확'."},
                    "role": {"type": "string", "description": "'주연' | '조연' | '단역' 등 비중."},
                    "arc_summary": {"type": "string",
                                    "description": "이 분량에서 이 인물이 보인 행보를 한국어 한 줄로. 근거 없으면 '불명확'."},
                    "key_moments": {"type": "array", "items": {"type": "string"},
                                    "description": "표지에 담을 만한 임팩트 있는 장면/모습(원문 근거). 없으면 빈 배열."},
                },
                "required": ["name", "gender", "age_estimate", "appearance",
                             "personality", "role", "arc_summary", "key_moments"],
            },
        }
    },
    "required": ["characters"],
}

_SYSTEM = (
    "당신은 한국어 웹소설 원문에서 '표지 제작에 쓸' 주요 등장인물 정보를 뽑는 분석가입니다. "
    "외형뿐 아니라, 주어진 분량 안에서 그 인물이 보인 행보와 임팩트 있는 모습까지 포착하세요. "
    "원문 근거가 있는 정보만 쓰고 지어내지 마세요. 불명확하면 '불명확'. "
    "모든 설명은 한국어로, JSON 만 반환합니다."
)


class CoverExtractor:
    """표지 플로우 ①추출. 최대 10화 분량에서 캐릭터(외형+행보+임팩트) 추출.

    추출 결과는 표지 생성 후 휘발한다(저장 책임 없음).
    """

    def __init__(self, config: ImageConfig | None = None) -> None:
        self.config = config or ImageConfig()

    def extract(self, episodes: str | list[str]) -> CoverExtractionResult:
        source = join_episodes(episodes, max_episodes=self.config.cover_max_episodes)
        if not source.strip():
            raise ValueError("표지 추출할 원문이 비어 있습니다.")

        if is_mock_mode():
            payload = cover_extraction_payload(source, self.config)
        else:
            payload = call_structured(
                self.config.extract_model, _SYSTEM,
                self._build_prompt(source), "webnovel_cover_extraction", COVER_SCHEMA,
            )
        return self._result(payload)

    @staticmethod
    def _build_prompt(source: str) -> str:
        return (
            "아래 한국어 웹소설 원문(최대 10화 분량)에서 표지 제작용 주요 등장인물을 추출하세요.\n\n"
            "[규칙]\n"
            "- 원문에 실제 등장한 인물만. 외형은 묘사 근거가 있는 것만.\n"
            "- arc_summary: 이 분량에서 그 인물이 어떤 행보를 보였는지 한 줄.\n"
            "- key_moments: 표지에 담을 만한 임팩트 있는 장면/모습(예: 무대를 장악하는 순간).\n"
            "- 단정 불가한 값은 '불명확', 빈 리스트는 빈 배열로.\n\n"
            f"[원문]\n{source}"
        )

    @staticmethod
    def _result(payload: dict[str, Any]) -> CoverExtractionResult:
        chars = [
            CoverCharacter(
                name=str(c.get("name", "")).strip(),
                gender=str(c.get("gender", "불명확")).strip() or "불명확",
                age_estimate=str(c.get("age_estimate", "불명확")).strip() or "불명확",
                appearance=[str(a).strip() for a in (c.get("appearance") or []) if str(a).strip()],
                personality=str(c.get("personality", "불명확")).strip() or "불명확",
                role=str(c.get("role", "")).strip() or "불명확",
                arc_summary=str(c.get("arc_summary", "불명확")).strip() or "불명확",
                key_moments=[str(m).strip() for m in (c.get("key_moments") or []) if str(m).strip()],
            )
            for c in (payload.get("characters") or [])
            if str(c.get("name", "")).strip()
        ]
        return CoverExtractionResult(characters=chars, raw_response=payload.get("raw_response", {}) or {})
