from __future__ import annotations

from typing import Any

from ._generate import generate_image
from .config import ImageConfig
from .cover_extractor import CoverCharacter, CoverExtractionResult, CoverExtractor
from .safety import build_refusal, is_unsafe_visual_request


class CoverGenerator:
    """표지 플로우 ②생성. 추출된 캐릭터(외형+행보+임팩트) + 사용자 추가 문구 → 표지 이미지.

    안전검사(거부+대안)는 표지 플로우 전용으로 여기서 수행한다.
    """

    def __init__(self, config: ImageConfig | None = None) -> None:
        self.config = config or ImageConfig()

    # episodes 로부터 추출까지 포함한 end-to-end (표지 플로우 단독 실행용).
    def generate_from_episodes(
        self, episodes: str | list[str], *, work_title: str = "작품",
        target_country: str = "", genre: str = "", extra_prompt: str = "",
    ) -> dict[str, Any]:
        extraction = CoverExtractor(self.config).extract(episodes)
        return self.generate(
            extraction, work_title=work_title, target_country=target_country,
            genre=genre, extra_prompt=extra_prompt,
        )

    # 이미 추출된 결과로 표지 생성.
    def generate(
        self, extraction: CoverExtractionResult, *, work_title: str = "작품",
        target_country: str = "", genre: str = "", extra_prompt: str = "",
    ) -> dict[str, Any]:
        subject = extraction.protagonist()

        # 안전검사: 추출/사용자 텍스트를 합쳐 사전 필터 → 부적절 시 거부+대안.
        safety_text = " ".join(filter(None, [
            extra_prompt, work_title, genre,
            subject.arc_summary if subject else "",
            " ".join(subject.appearance) if subject else "",
            " ".join(subject.key_moments) if subject else "",
        ]))
        if is_unsafe_visual_request(safety_text):
            return build_refusal(safety_text, self.config)

        prompt = self._build_prompt(subject, work_title, target_country, genre, extra_prompt)
        return generate_image(prompt, self.config)

    def _build_prompt(
        self, subject: CoverCharacter | None, work_title: str,
        country: str, genre: str, extra: str,
    ) -> str:
        if subject is not None:
            name = subject.name
            traits = subject.personality if subject.personality != "불명확" else "clear protagonist identity and readable emotion"
            appearance = ", ".join(subject.appearance) or "derive from the episode context without overcomplicating the design"
            arc = subject.arc_summary if subject.arc_summary != "불명확" else "reflect the protagonist's presence in the selected episodes"
            moments = "\n".join(f"- {m}" for m in subject.key_moments) or "- Use the protagonist's most impactful presence as the focal moment."
        else:
            name, traits, appearance, arc = "주인공", "clear protagonist identity", "derive from context", "reflect story presence"
            moments = "- Use a genre-appropriate focal moment."

        return f"""Create a vertical commercial web novel cover illustration.
Work title: {work_title}
Target country/market: {country or "global web novel market"}
Genre: {genre or "web novel"}
Main cover subject (single protagonist focus): {name}
Protagonist traits: {traits}
Appearance features: {appearance}
Protagonist arc in these episodes: {arc}
Impactful moments to draw from:
{moments}
Additional request: {extra or "No additional request."}
Style: vertical web novel cover, strong thumbnail readability, one clear focal subject, title-safe negative space near top or bottom, polished digital illustration, genre immediately recognizable, simple background hierarchy, no generated text, no watermark, family-friendly safe-for-all-ages."""
