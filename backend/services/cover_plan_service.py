"""Cover planning service."""

from __future__ import annotations

import re
from typing import Any

from backend.store.memory_store import episodes_list, save_cover_plan, work_get

def _summarize_episode_for_cover(episode: dict[str, Any]) -> dict[str, Any]:
    body = (episode.get("body") or "").strip()
    first_sentence = re.split(r"(?<=[.!?])\s+|\n+", body)[0] if body else ""
    summary = first_sentence[:160] or body[:160] or "No episode body summary available."
    return {
        "episodeId": episode["id"],
        "title": episode.get("title", f"Episode {episode['id']}"),
        "summary": summary,
    }

def _extract_cover_brief(
    *,
    work: dict[str, Any],
    episode_summaries: list[dict[str, Any]],
    preferences: dict[str, Any],
) -> dict[str, Any]:
    joined = " ".join(row["summary"] for row in episode_summaries)
    genre = work.get("genre") or preferences.get("genre") or "웹소설"
    protagonist = preferences.get("protagonist") or "주인공"
    if "김첨지" in joined:
        protagonist = "김첨지"
    elif "소녀" in joined and "소년" in joined:
        protagonist = "소년과 소녀"
    symbols = list(dict.fromkeys(preferences.get("mustInclude") or []))
    for keyword in ["시스템창", "던전", "게이트", "검", "마법진", "슬라임", "왕관", "계약서", "징검다리", "소나기", "조약돌"]:
        if keyword in joined and keyword not in symbols:
            symbols.append(keyword)
    if not symbols:
        symbols = ["주인공", "장르 분위기", "초반 사건의 상징"]
    mood = preferences.get("tone") or []
    if not mood:
        if any(word in joined for word in ["웃", "코미디", "당황"]):
            mood.append("코미디")
        if any(word in joined for word in ["복수", "분노"]):
            mood.append("복수")
        if any(word in joined for word in ["사랑", "설렘", "소녀", "소년"]):
            mood.append("서정적")
        if not mood:
            mood.append("상업적 웹소설")
    hook = preferences.get("hook") or "초반 회차에서 드러나는 주인공 정체성과 사건의 후킹 포인트"
    if episode_summaries:
        hook = episode_summaries[0]["summary"][:120]
    return {
        "genre": genre,
        "protagonist": protagonist,
        "hook": hook,
        "mood": mood,
        "symbols": symbols[:8],
        "relationships": preferences.get("relationships") or ["주인공 중심"],
        "avoid": preferences.get("avoid") or ["조연 과다", "복잡한 배경", "읽히지 않는 제목 영역"],
    }


def _cover_concepts(brief: dict[str, Any]) -> list[dict[str, Any]]:
    protagonist = brief.get("protagonist", "주인공")
    symbols = ", ".join(brief.get("symbols", [])[:3])
    return [
        {
            "id": "commercial_thumbnail",
            "name": "상업형 썸네일 표지",
            "description": f"{protagonist}를 크게 배치하고 배경은 단순화해 장르와 후킹을 즉시 전달한다.",
            "strength": "플랫폼 목록에서 가독성과 클릭 유도가 좋다.",
            "weakness": "세계관 디테일은 일부 생략될 수 있다.",
            "recommended": True,
        },
        {
            "id": "hook_symbol",
            "name": "차별점 강조 표지",
            "description": f"{symbols or '핵심 상징'}를 전면에 두어 작품만의 독특한 설정을 강조한다.",
            "strength": "작품의 차별점이 빠르게 보인다.",
            "weakness": "상징이 많으면 화면이 복잡해질 수 있다.",
            "recommended": False,
        },
        {
            "id": "genre_mood",
            "name": "장르 무드형 표지",
            "description": f"{', '.join(brief.get('mood', [])[:3])} 분위기를 색감과 구도로 강조한다.",
            "strength": "독자가 장르와 감정선을 쉽게 인식한다.",
            "weakness": "주인공의 개별 후킹은 약해질 수 있다.",
            "recommended": False,
        },
    ]


def _cover_prompt_from_plan(brief: dict[str, Any], concept_id: str, extra_prompt: str = "") -> dict[str, Any]:
    concepts = {row["id"]: row for row in _cover_concepts(brief)}
    concept = concepts.get(concept_id) or next(iter(concepts.values()))
    image_prompt = f"""Create a vertical commercial web novel cover.
Concept: {concept['name']} - {concept['description']}
Genre: {brief.get('genre')}
Main subject: {brief.get('protagonist')}
Core hook: {brief.get('hook')}
Mood: {', '.join(brief.get('mood', []))}
Visual symbols: {', '.join(brief.get('symbols', []))}
Avoid: {', '.join(brief.get('avoid', []))}
Extra request: {extra_prompt or 'No additional request.'}
Style: strong thumbnail readability, one clear focal point, title-safe negative space, polished digital illustration, simple background hierarchy, no generated text, no watermark."""
    return {
        "conceptId": concept["id"],
        "imagePrompt": image_prompt,
        "negativePrompt": "tiny unreadable text, watermark, logo, crowded background, too many side characters, spoilers, unsafe sexual content",
        "titleLayout": {
            "top": "후킹 문구 또는 제목 1행을 둘 수 있는 여백",
            "center": "주인공/핵심 상징",
            "bottom": "제목 2~3줄 배치 가능한 안정적인 영역",
        },
        "excludeElements": brief.get("avoid", []),
    }


def cover_plan(work_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    preferences = payload.get("preferences") or {}
    episode_ids = payload.get("episodeIds") or []
    if len(episode_ids) > 10:
        raise ValueError("episodeIds can include at most 10 episodes")
    work = work_get(work_id)
    if not work:
        raise ValueError(f"work {work_id} not found")
    episode_id_set = set(map(int, episode_ids)) if episode_ids else set()
    selected = [
        ep
        for ep in episodes_list(work_id)
        if not episode_id_set or ep["id"] in episode_id_set
    ]
    selected = sorted(selected, key=lambda row: row["id"])[:10]
    if not selected:
        raise ValueError("at least one episode is required for cover planning")
    episode_summaries = [_summarize_episode_for_cover(ep) for ep in selected]
    combined_summary = " ".join(row["summary"] for row in episode_summaries)[:800]
    brief = _extract_cover_brief(work=work, episode_summaries=episode_summaries, preferences=preferences)
    concepts = _cover_concepts(brief)
    prompt = _cover_prompt_from_plan(brief, concepts[0]["id"], preferences.get("extraPrompt", ""))
    return save_cover_plan(
        work_id=work_id,
        episode_ids=[row["id"] for row in selected],
        episode_summaries=episode_summaries,
        combined_summary=combined_summary,
        cover_brief=brief,
        concepts=concepts,
        recommended_concept_id=concepts[0]["id"],
        prompt=prompt,
    )
