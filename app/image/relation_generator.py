from __future__ import annotations

from typing import Any

from ._generate import generate_image
from .config import ImageConfig
from .relation_extractor import RelationExtractionResult, RelationExtractor


class RelationGenerator:
    """관계도 플로우 ②생성. 추출된 인물·관계 → 관계도(다이어그램) 이미지.

    관계도는 다이어그램이라 표지와 달리 신체 노출 위험이 없어 안전검사를 두지 않는다.
    """

    def __init__(self, config: ImageConfig | None = None) -> None:
        self.config = config or ImageConfig()

    def generate_from_episodes(
        self, episodes: str | list[str], *, work_title: str = "작품", extra_prompt: str = "",
    ) -> dict[str, Any]:
        extraction = RelationExtractor(self.config).extract(episodes)
        return self.generate(extraction, work_title=work_title, extra_prompt=extra_prompt)

    def generate(
        self, extraction: RelationExtractionResult, *, work_title: str = "작품", extra_prompt: str = "",
    ) -> dict[str, Any]:
        prompt = self._build_prompt(extraction, work_title, extra_prompt)
        return generate_image(prompt, self.config)

    @staticmethod
    def _build_prompt(extraction: RelationExtractionResult, work_title: str, extra: str) -> str:
        nodes_text = "\n".join(
            f"- {n.name} ({n.role})" for n in extraction.nodes
        ) or "- Main characters"
        rels_text = "\n".join(
            f"- {r.from_} {'→' if r.directed else '↔'} {r.to}: {r.relation_type}"
            f"{' (one-directional)' if r.directed else ' (mutual)'}"
            for r in extraction.relations
        ) or "- Connected by story"

        return f"""Create a clean visual character relationship map for a web novel.
Work title: {work_title}
Characters (nodes):
{nodes_text}
Relationships (use one-directional arrows → for unrequited/one-way, double arrows ↔ for mutual):
{rels_text}
Additional request: {extra or "No additional request."}
Style: clean diagram-like relationship map, portrait nodes connected by labeled relationship arrows, arrow direction matches one-directional vs mutual relations, muted modern literary color palette, readable layout, no watermark, family-friendly."""
