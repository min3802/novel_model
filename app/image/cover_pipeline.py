from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import ImageConfig
from .extract.cover_extractor import CoverExtractionResult, CoverExtractor
from .generate.cover_generator import CoverGenerator


@dataclass(slots=True)
class CoverResult:
    """표지 파이프라인 결과: 추출 결과 + 생성 이미지(또는 거부)를 함께 담는다."""
    extraction: CoverExtractionResult
    image: dict[str, Any]

    @property
    def refused(self) -> bool:
        return self.image.get("type") == "refusal"

    def to_dict(self) -> dict[str, Any]:
        return {"extraction": self.extraction.to_dict(), "image": self.image}


class CoverPipeline:
    """표지 플로우 오케스트레이터 (번역의 TranslationPipeline 패턴).

        원문(최대 10화) → ① 추출 → ② 생성(+안전검사) → CoverResult

    추출 결과는 표지 생성 후 휘발한다(파이프라인은 저장하지 않는다).
    """

    def __init__(self, config: ImageConfig | None = None) -> None:
        self.config = config or ImageConfig()
        self.extractor = CoverExtractor(self.config)
        self.generator = CoverGenerator(self.config)

    def run(
        self, episodes: str | list[str], *, work_title: str = "작품",
        target_country: str = "", genre: str = "", extra_prompt: str = "",
    ) -> CoverResult:
        extraction = self.extractor.extract(episodes)
        image = self.generator.generate(
            extraction, work_title=work_title, target_country=target_country,
            genre=genre, extra_prompt=extra_prompt,
        )
        return CoverResult(extraction=extraction, image=image)

    def generate_from_extraction(
        self, extraction: CoverExtractionResult, *, work_title: str = "작품",
        target_country: str = "", genre: str = "", extra_prompt: str = "",
    ) -> CoverResult:
        """이미 추출된 결과로 생성만 (추출 재호출 없이)."""
        image = self.generator.generate(
            extraction, work_title=work_title, target_country=target_country,
            genre=genre, extra_prompt=extra_prompt,
        )
        return CoverResult(extraction=extraction, image=image)
