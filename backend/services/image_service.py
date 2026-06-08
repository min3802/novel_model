"""이미지 서빙 계층 (얇은 포장).

설계 원칙(번역 기능과 동일): app/image = 모델링(추출·생성·안전검사·파이프라인),
backend/services/image_service = 그걸 호출해 HTTP payload 로 포장.

표지/관계도는 별개 플로우다. 둘 다 원문(episodes) → 파이프라인 → 이미지.
  - 표지:   payload.episodes → CoverPipeline.run    (추출→생성+안전검사)
  - 관계도: payload.episodes → RelationPipeline.run  (추출→생성)
"""
from __future__ import annotations

from typing import Any

from dotenv import load_dotenv

from app.image import CoverPipeline, ImageConfig, RelationPipeline

load_dotenv()

_config = ImageConfig()


def _episodes(payload: dict[str, Any]) -> str | list[str]:
    """payload 에서 원문(화) 추출. episodes(list|str) 우선, 단일 text 폴백."""
    eps = payload.get("episodes")
    if eps:
        return eps
    return payload.get("text") or payload.get("source") or ""


def cover_image(payload: dict[str, Any]) -> dict[str, Any]:
    result = CoverPipeline(_config).run(
        _episodes(payload),
        work_title=(payload.get("workTitle") or "작품").strip(),
        target_country=(payload.get("targetCountry") or payload.get("country") or "").strip(),
        genre=(payload.get("genre") or "").strip(),
        extra_prompt=(payload.get("extraPrompt") or "").strip(),
    )
    return result.image


def relation_image(payload: dict[str, Any]) -> dict[str, Any]:
    result = RelationPipeline(_config).run(
        _episodes(payload),
        work_title=(payload.get("workTitle") or "작품").strip(),
        extra_prompt=(payload.get("extraPrompt") or "").strip(),
    )
    return result.image


def visual_prompt(payload: dict[str, Any], kind: str) -> dict[str, Any]:
    """레거시 호환: 프롬프트 미리보기(생성 호출 없이 텍스트만)."""
    work_title = payload.get("workTitle") or "작품"
    extra = payload.get("extraPrompt") or ""
    if kind == "relation":
        prompt = f"Create a clean relationship map for {work_title}. {extra}".strip()
    elif kind == "cover":
        prompt = f"Create a vertical commercial web novel cover for {work_title}. {extra}".strip()
    else:
        character = payload.get("characterName") or "주인공"
        prompt = f"Create a polished web novel character illustration for {character} in {work_title}. {extra}".strip()
    return {"kind": kind, "prompt": prompt, "status": "ready"}
