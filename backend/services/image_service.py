"""이미지 서빙 계층 (얇은 포장).

설계 원칙(번역 기능과 동일): app/image = 모델링(추출·생성·안전검사),
backend/services/image_service = 그걸 호출해 HTTP payload 로 포장.

표지/관계도는 별개 플로우다.
  - 표지:   payload → (episodes 있으면 추출) → CoverGenerator → 안전검사 포함
  - 관계도: payload → (episodes 있으면 추출) → RelationGenerator

레거시 payload(protagonist/appearance/characters/relations 직접 전달)도 그대로 지원해
기존 api_server·테스트 호환성을 유지한다.
"""
from __future__ import annotations

from typing import Any

from dotenv import load_dotenv

from app.image import (
    CoverCharacter,
    CoverExtractionResult,
    CoverGenerator,
    ImageConfig,
    Relation,
    RelationExtractionResult,
    RelationGenerator,
    RelationNode,
)
from app.image._generate import generate_image as _generate_image

load_dotenv()

_config = ImageConfig()


def generate_image(prompt: str) -> dict[str, Any]:
    """레거시 호환: 프롬프트 직접 → 이미지."""
    return _generate_image(prompt, _config)


# ---------------------------------------------------------------------------
# 표지
# ---------------------------------------------------------------------------
def cover_image(payload: dict[str, Any]) -> dict[str, Any]:
    work_title = (payload.get("workTitle") or "작품").strip()
    country = (payload.get("targetCountry") or payload.get("country") or "").strip()
    genre = (payload.get("genre") or "").strip()
    extra = (payload.get("extraPrompt") or "").strip()

    gen = CoverGenerator(_config)
    episodes = payload.get("episodes")
    if episodes:
        # 새 플로우: 원문 → 추출 → 표지.
        return gen.generate_from_episodes(
            episodes, work_title=work_title, target_country=country,
            genre=genre, extra_prompt=extra,
        )

    # 레거시 플로우: 이미 정리된 인물 정보를 추출 결과 형태로 감싸 생성.
    extraction = _cover_extraction_from_legacy(payload)
    return gen.generate(
        extraction, work_title=work_title, target_country=country,
        genre=genre, extra_prompt=extra,
    )


def _cover_extraction_from_legacy(payload: dict[str, Any]) -> CoverExtractionResult:
    protagonist = (payload.get("protagonist") or payload.get("characterName") or "주인공").strip()
    traits = (payload.get("protagonistTraits") or payload.get("personality") or "불명확").strip() or "불명확"
    appearance_raw = payload.get("appearance") or ""
    appearance = (
        [str(a).strip() for a in appearance_raw if str(a).strip()]
        if isinstance(appearance_raw, list)
        else [appearance_raw.strip()] if appearance_raw.strip() else []
    )
    summaries = payload.get("episodeSummaries") or []
    arc = " ".join(map(str, summaries)).strip() or "불명확"
    symbols = payload.get("symbols") or []
    key_moments = [str(s).strip() for s in symbols if str(s).strip()]

    char = CoverCharacter(
        name=protagonist, gender="불명확", age_estimate="불명확",
        appearance=appearance, personality=traits, role="주연",
        arc_summary=arc, key_moments=key_moments,
    )
    return CoverExtractionResult(characters=[char])


# ---------------------------------------------------------------------------
# 관계도
# ---------------------------------------------------------------------------
def relation_image(payload: dict[str, Any]) -> dict[str, Any]:
    work_title = (payload.get("workTitle") or "작품").strip()
    extra = (payload.get("extraPrompt") or "").strip()

    gen = RelationGenerator(_config)
    episodes = payload.get("episodes")
    if episodes:
        return gen.generate_from_episodes(episodes, work_title=work_title, extra_prompt=extra)

    extraction = _relation_extraction_from_legacy(payload)
    return gen.generate(extraction, work_title=work_title, extra_prompt=extra)


def _relation_extraction_from_legacy(payload: dict[str, Any]) -> RelationExtractionResult:
    characters = payload.get("characters") or []
    relations = payload.get("relations") or []

    nodes = [
        RelationNode(name=str(c.get("name", "")).strip(), role="불명확")
        for c in characters
        if str(c.get("name", "")).strip()
    ]
    rels = [
        Relation(
            from_=str(r.get("from", "")).strip(),
            to=str(r.get("to", "")).strip(),
            relation_type=str(r.get("relation") or r.get("relation_type") or "불명확").strip() or "불명확",
            directed=bool(r.get("directed", False)),
            evidence=str(r.get("evidence", "")).strip(),
        )
        for r in relations
        if str(r.get("from", "")).strip() and str(r.get("to", "")).strip()
    ]
    return RelationExtractionResult(nodes=nodes, relations=rels)


# ---------------------------------------------------------------------------
# 레거시 호환: 프롬프트 미리보기
# ---------------------------------------------------------------------------
def visual_prompt(payload: dict[str, Any], kind: str) -> dict[str, Any]:
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
