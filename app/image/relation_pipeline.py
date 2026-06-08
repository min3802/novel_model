from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import ImageConfig
from .extract.relation_extractor import RelationExtractionResult, RelationExtractor
from .generate.relation_generator import RelationGenerator


@dataclass(slots=True)
class RelationResult:
    """관계도 파이프라인 결과: 추출 결과 + 생성 이미지를 함께 담는다."""
    extraction: RelationExtractionResult
    image: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"extraction": self.extraction.to_dict(), "image": self.image}


class RelationPipeline:
    """관계도 플로우 오케스트레이터 (번역의 TranslationPipeline 패턴).

        원문(최대 20화) → ① 추출 → ② 생성 → RelationResult

    추출 결과는 관계도 생성 후 휘발한다(파이프라인은 저장하지 않는다).
    """

    def __init__(self, config: ImageConfig | None = None) -> None:
        self.config = config or ImageConfig()
        self.extractor = RelationExtractor(self.config)
        self.generator = RelationGenerator(self.config)

    def run(
        self, episodes: str | list[str], *, work_title: str = "작품", extra_prompt: str = "",
    ) -> RelationResult:
        extraction = self.extractor.extract(episodes)
        image = self.generator.generate(extraction, work_title=work_title, extra_prompt=extra_prompt)
        return RelationResult(extraction=extraction, image=image)
