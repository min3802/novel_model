from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
_openai_client: OpenAI | None = None


def _get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


def _is_mock_mode() -> bool:
    return os.getenv("WLIGHTER_MOCK_MODE", "true").lower() in {"1", "true", "yes", "y"}


def generate_image(prompt: str) -> dict[str, Any]:
    if _is_mock_mode():
        return {
            "type": "mock_image",
            "data": "mock://w-lighter/generated-image",
            "model": OPENAI_IMAGE_MODEL,
            "notice": "AI 생성 이미지입니다.",
            "prompt": prompt,
        }
    client = _get_openai()
    response = client.images.generate(
        model=OPENAI_IMAGE_MODEL,
        prompt=prompt,
        size="1024x1024",
        n=1,
    )
    item = response.data[0]
    b64 = getattr(item, "b64_json", None)
    url = getattr(item, "url", None)
    if b64:
        return {"type": "base64", "data": b64, "model": OPENAI_IMAGE_MODEL}
    if url:
        return {"type": "url", "data": url, "model": OPENAI_IMAGE_MODEL}
    raise RuntimeError("이미지 데이터를 찾지 못했습니다.")


def _unsafe_visual_request(text: str) -> bool:
    lowered = text.lower()
    unsafe_terms = [
        "나체",
        "전신 노출",
        "성기",
        "nude",
        "nudity",
        "fully naked",
        "genitals",
    ]
    return any(term in lowered for term in unsafe_terms)


def _visual_refusal() -> dict[str, Any]:
    return {
        "type": "refusal",
        "model": OPENAI_IMAGE_MODEL,
        "message": (
            "전신 노출처럼 성기까지 보이는 이미지는 생성해드릴 수 없습니다. "
            "대신 상의는 벗고 하의는 젖은 잠방이 또는 허리 천으로 가린 모습처럼 "
            "비노출 방향으로 조정할 수 있습니다."
        ),
    }

def cover_image(payload: dict[str, Any]) -> dict[str, Any]:
    work_title = (payload.get("workTitle") or "작품").strip()
    country = (payload.get("targetCountry") or payload.get("country") or "대상 국가").strip()
    genre = (payload.get("genre") or "").strip()
    protagonist = (payload.get("protagonist") or payload.get("characterName") or "주인공").strip()
    protagonist_traits = (payload.get("protagonistTraits") or payload.get("personality") or "").strip()
    appearance = (payload.get("appearance") or "").strip()
    episode_summaries = payload.get("episodeSummaries") or []
    symbols = payload.get("symbols") or []
    mood = payload.get("mood") or payload.get("tone") or []
    extra = (payload.get("extraPrompt") or "").strip()
    safety_text = " ".join(
        [
            work_title,
            country,
            genre,
            protagonist,
            protagonist_traits,
            appearance,
            " ".join(map(str, episode_summaries)),
            " ".join(map(str, symbols)),
            " ".join(map(str, mood)) if isinstance(mood, list) else str(mood),
            extra,
        ]
    )
    if _unsafe_visual_request(safety_text):
        return _visual_refusal()

    summaries_text = (
        "\n".join(f"- {row}" for row in episode_summaries[:10])
        if episode_summaries
        else "- Use the work title, genre, protagonist, and visual symbols as the cover brief."
    )
    symbols_text = ", ".join(map(str, symbols)) if symbols else "genre-appropriate symbolic props"
    mood_text = ", ".join(map(str, mood)) if isinstance(mood, list) else (mood or "commercial web novel cover mood")

    prompt = f"""Create a vertical commercial web novel cover illustration.
Work title: {work_title}
Target country/market: {country}
Genre: {genre or "web novel"}
Main cover subject: {protagonist}
Protagonist traits: {protagonist_traits or "clear protagonist identity and readable emotion"}
Appearance features: {appearance or "derive from the episode context without overcomplicating the design"}
Selected episode summary signals:
{summaries_text}
Visual symbols to consider: {symbols_text}
Mood: {mood_text}
Additional request: {extra or "No additional request."}
Style: vertical web novel cover, strong thumbnail readability, one clear focal subject, title-safe negative space near top or bottom, polished digital illustration, genre immediately recognizable, simple background hierarchy, no generated text, no watermark, family-friendly safe-for-all-ages."""

    return generate_image(prompt)


def relation_image(payload: dict[str, Any]) -> dict[str, Any]:
    work_title = (payload.get("workTitle") or "작품").strip()
    characters = payload.get("characters") or []
    relations = payload.get("relations") or []
    theme = (payload.get("theme") or "").strip()
    extra = (payload.get("extraPrompt") or "").strip()
    if _unsafe_visual_request(" ".join([theme, extra])):
        return _visual_refusal()

    chars_text = "\n".join(f"- {c['name']}: {c.get('description','')}" for c in characters) if characters else "- Main characters"
    rels_text = "\n".join(f"- {r['from']} → {r['to']}: {r.get('relation','')}" for r in relations) if relations else "- Connected by story"

    prompt = f"""Create a clean visual character relationship map for a web novel.
Work title: {work_title}
Characters:\n{chars_text}
Relationships:\n{rels_text}
Theme: {theme or "human drama"}
Additional request: {extra or "No additional request."}
Style: clean diagram-like composition, portrait nodes connected by relationship arrows, muted modern literary color palette, readable layout, no watermark, family-friendly."""

    return generate_image(prompt)


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
