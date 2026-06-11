
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.guide.platform_trend_guide import (
    DEFAULT_INPUT,
    build_collection_profiles,
    build_country_profiles,
    load_trend_data,
)


KO_US = "\ubbf8\uad6d"
KO_ENGLISH_ZONE = "\uc601\uc5b4\uad8c"
KO_JAPAN = "\uc77c\ubcf8"
JP_JAPAN = "\u65e5\u672c"
KO_ROMANCE_FANTASY_SHORT = "\ub85c\ud310"
KO_ROMANCE_FANTASY = "\ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0"
KO_ROMANCE = "\ub85c\ub9e8\uc2a4"
KO_FANTASY = "\ud310\ud0c0\uc9c0"
KO_ACTION_FANTASY = "\uc561\uc158 \ud310\ud0c0\uc9c0"
KO_GAME_FANTASY = "\uac8c\uc784\ud310\ud0c0\uc9c0"
KO_WUXIA = "\ubb34\ud611"
KO_ISEKAI = "\uc774\uc138\uacc4"
KO_REINCARNATION = "\uc804\uc0dd"

JP_ISEKAI_ROMANCE = "\u7570\u4e16\u754c\u3014\u604b\u611b\u3015"
JP_HIGH_FANTASY = "\u30cf\u30a4\u30d5\u30a1\u30f3\u30bf\u30b8\u30fc"
JP_LOW_FANTASY = "\u30ed\u30fc\u30d5\u30a1\u30f3\u30bf\u30b8\u30fc"
JP_VR_GAME = "VR\u30b2\u30fc\u30e0"
JP_ISEKAI_REINCARNATION = "\u7570\u4e16\u754c\u8ee2\u751f"
JP_ISEKAI_TRANSFER = "\u7570\u4e16\u754c\u8ee2\u79fb"
JP_ENGAGEMENT_BREAK = "\u5a5a\u7d04\u7834\u68c4"
JP_DOTING = "\u6eba\u611b"

COUNTRY_ALIASES = {
    "us": "US/global English",
    "usa": "US/global English",
    "united states": "US/global English",
    "america": "US/global English",
    KO_US: "US/global English",
    KO_ENGLISH_ZONE: "US/global English",
    "english": "US/global English",
    "japan": "Japan",
    "jp": "Japan",
    KO_JAPAN: "Japan",
    JP_JAPAN: "Japan",
    "china": "China",
    "cn": "China",
    "\uc911\uad6d": "China",
    "thailand": "Thailand",
    "th": "Thailand",
    "\ud0dc\uad6d": "Thailand",
}

EXCLUDED_RECOMMENDATION_COUNTRIES = {"Global"}

ALLOWED_COUNTRY_ORDER = ["Japan", "China", "US/global English", "Thailand"]

COUNTRY_DISPLAY_KO = {
    "Japan": "일본",
    "China": "중국",
    "US/global English": "미국",
    "Thailand": "태국",
}

GENRE_ALIASES = {
    "romance fantasy": ["Romance Fantasy", "Romance", JP_ISEKAI_ROMANCE, "villainess", JP_ENGAGEMENT_BREAK, JP_DOTING],
    "romantasy": ["Romance Fantasy", "Romance", JP_ISEKAI_ROMANCE, "villainess"],
    KO_ROMANCE_FANTASY_SHORT: ["Romance Fantasy", "Romance", JP_ISEKAI_ROMANCE, "villainess", JP_ENGAGEMENT_BREAK, JP_DOTING],
    KO_ROMANCE_FANTASY: ["Romance Fantasy", "Romance", JP_ISEKAI_ROMANCE],
    "romance": ["Romance", "Romance Fantasy", JP_ISEKAI_ROMANCE, "BL", "LGBTQ+"],
    KO_ROMANCE: ["Romance", "Romance Fantasy", JP_ISEKAI_ROMANCE, "BL", "LGBTQ+"],
    "bl": ["BL", "LGBTQ+", "Romance"],
    "fantasy": ["Fantasy", "High Fantasy", JP_HIGH_FANTASY, JP_LOW_FANTASY, "Magic", "Adventure"],
    KO_FANTASY: ["Fantasy", "High Fantasy", JP_HIGH_FANTASY, JP_LOW_FANTASY, "Magic", "Adventure"],
    "action fantasy": ["Action Fantasy", "Action", "Adventure", "Fantasy"],
    KO_ACTION_FANTASY: ["Action Fantasy", "Action", "Adventure", "Fantasy"],
    "litrpg": ["LitRPG", "GameLit", "Progression", "System", "Skill"],
    KO_GAME_FANTASY: ["LitRPG", "GameLit", "Progression", "System", "Skill", JP_VR_GAME],
    KO_WUXIA: ["Cultivation", "Martial Arts", "Wuxia"],
    "isekai": ["Isekai", "Portal Fantasy / Isekai", JP_ISEKAI_REINCARNATION, JP_ISEKAI_TRANSFER, "Reincarnation"],
    KO_ISEKAI: ["Isekai", "Portal Fantasy / Isekai", JP_ISEKAI_REINCARNATION, JP_ISEKAI_TRANSFER, "Reincarnation"],
    KO_REINCARNATION: ["Reincarnation", JP_ISEKAI_REINCARNATION, "Isekai"],
}

SYNOPSIS_KEYWORDS = {
    "romance": ["romance", "love", "marriage", "husband", "wife", "duke", "prince", "villainess", "\uc57d\ud63c", "\uacb0\ud63c", "\uacf5\uc791", "\ud669\ud0dc\uc790", "\uc545\ub140", "공녀", "귀족", "가문", KO_ROMANCE, "\uc0ac\ub791"],
    "progression": ["level", "skill", "system", "rank", "dungeon", "quest", "\uc131\uc7a5", "\uc2a4\ud0ac", "\ub808\ubca8", "\uc2dc\uc2a4\ud15c", "\ub358\uc804", "\ub7ad\ucee4"],
    "isekai": ["reincarn", "isekai", "another world", "transport", "\ud68c\uadc0", "돌아와", "다시", KO_REINCARNATION, "\ube59\uc758", KO_ISEKAI, "\ud658\uc0dd"],
    "action": ["battle", "war", "fight", "survival", "apocalypse", "\uc804\ud22c", "\uc804\uc7c1", "복수", "잔혹", "피", "\uc0dd\uc874", "\uba78\ub9dd", "\uc544\ud3ec\uce7c\ub9bd\uc2a4"],
    "bl": ["omega", "alpha", "bl", "boys love", "\ub0a8\uc790", "\uc624\uba54\uac00", "\uc54c\ud30c"],
}

SYNOPSIS_MOTIF_LABELS = {
    "romance": "관계/로맨스 축",
    "progression": "성장·시스템 축",
    "isekai": "회귀·전생·이세계 축",
    "action": "전투·생존 축",
    "bl": "BL/관계성 축",
}

@dataclass(frozen=True)
class EvidenceItem:
    platform: str
    collection: str
    rank: int
    title: str
    genre: str | None
    tags: list[str]
    source_url: str | None
    reason: str


@dataclass(frozen=True)
class Recommendation:
    country: str
    score: float
    reasons: list[str]
    evidence: list[EvidenceItem]


def normalize_country(value: str | None) -> str | None:
    key = (value or "").strip().lower()
    if not key:
        return None
    return COUNTRY_ALIASES.get(key, value.strip())


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tokens(value: str) -> list[str]:
    lowered = value.lower()
    words = re.findall(r"[a-z][a-z0-9+/-]{2,}|[가-힣]{2,}|[ぁ-んァ-ン一-龯]{2,}", lowered)
    return words


def _genre_needles(genre: str | None) -> list[str]:
    raw = _text(genre)
    lowered = raw.lower()
    needles: list[str] = []
    for key, values in GENRE_ALIASES.items():
        if key in lowered or key in raw:
            needles.extend(values)
    if raw:
        needles.append(raw)
    return list(dict.fromkeys(needles))


def _synopsis_needles(synopsis: str | None) -> list[str]:
    text = _text(synopsis).lower()
    needles: list[str] = []
    for values in SYNOPSIS_KEYWORDS.values():
        if any(keyword.lower() in text for keyword in values):
            needles.extend(values)
    needles.extend(_tokens(text)[:30])
    return list(dict.fromkeys([needle for needle in needles if needle]))


def _synopsis_motifs(synopsis: str | None) -> list[str]:
    text = _text(synopsis).lower()
    if not text:
        return []
    motifs: list[str] = []
    for key, values in SYNOPSIS_KEYWORDS.items():
        if any(keyword.lower() in text for keyword in values):
            motifs.append(SYNOPSIS_MOTIF_LABELS.get(key, key))
    return list(dict.fromkeys(motifs))


def _synopsis_input_note(synopsis: str | None) -> str:
    motifs = _synopsis_motifs(synopsis)
    if not _text(synopsis):
        return "시놉시스가 없어 세부 소재·관계·수위 요소는 확정하지 않고, 입력 장르와 대상 국가 기준으로만 확인합니다."
    if motifs:
        return f"시놉시스에서 {', '.join(motifs)}을 조심스러운 추정 요소로 읽었습니다."
    return "시놉시스는 제공됐지만 준비된 키워드 기준으로 특정 소재 축을 강하게 확정하지 않았습니다."


def _row_search_text(row: dict[str, Any]) -> str:
    return " ".join(
        [
            _text(row.get("title")),
            _text(row.get("genre")),
            " ".join(_text(x) for x in row.get("genres") or []),
            " ".join(_text(x) for x in row.get("tags") or []),
            _text(row.get("synopsis")),
        ]
    ).lower()


def _match_count(text: str, needles: list[str]) -> int:
    return sum(1 for needle in needles if needle and needle.lower() in text)


def _country_records(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for records in (data.get("collections") or {}).values():
        for row in records:
            grouped[row.get("country") or "unknown"].append(row)
    return grouped


def available_options(data: dict[str, Any]) -> dict[str, Any]:
    collection_profiles = build_collection_profiles(data)
    profiles = {country.country: country for country in build_country_profiles(collection_profiles)}
    return {
        "countries": [
            {
                "country": country,
                "displayCountry": COUNTRY_DISPLAY_KO.get(country, country),
                "topGenres": profiles.get(country).top_genres[:8] if profiles.get(country) else [],
                "topTags": profiles.get(country).top_tags[:12] if profiles.get(country) else [],
                "platforms": [f"{p.platform} / {p.collection}" for p in profiles.get(country).collections] if profiles.get(country) else [],
            }
            for country in ALLOWED_COUNTRY_ORDER
        ],
        "genres": ["Romance", "Romance Fantasy", "Fantasy", "LitRPG", "Isekai", "Action Fantasy", "BL", "Wuxia"],
    }


def _available_countries() -> list[dict[str, str]]:
    return [{"country": country, "display": COUNTRY_DISPLAY_KO.get(country, country)} for country in ALLOWED_COUNTRY_ORDER]


def _recommendation_notice(*, synopsis_present: bool) -> str:
    if synopsis_present:
        return "이 추천은 시장 흥행 예측이 아니라 장르와 시놉시스 기준의 1차 현지화 적합도 참고입니다. 작품의 줄거리, 결말, 캐릭터 정체성, 중심 갈등은 바꾸지 않습니다."
    return "시놉시스가 없어 국가 추천은 제공하지 않고, 선택한 국가를 기준으로 번역 전 현지화 기준서만 만듭니다."


def _translation_profile(country: str, *, genre: str, synopsis_present: bool) -> dict[str, Any]:
    display = COUNTRY_DISPLAY_KO.get(country, country)
    localization_level = "balanced" if synopsis_present else "conservative"
    if country == "Japan":
        dialogue_style = "장면 톤을 살리는 자연스러운 구어체와 호칭 체계를 우선한다."
        proper_noun_policy = "고유명사는 원문 음차와 작품 glossary를 우선하고, 호칭은 일본 독자 기준으로 무리하게 바꾸지 않는다."
        culture_policy = "한국 문화 요소는 현지 제도로 바꾸기보다 의미를 유지한 채 자연스럽게 풀어준다."
    elif country == "China":
        dialogue_style = "관계와 긴장감을 살리는 간결한 구어체를 우선한다."
        proper_noun_policy = "고유명사는 병기 기준을 유지하고, 호칭·직책은 작품 glossary를 우선한다."
        culture_policy = "한국 문화 요소는 설명을 덧붙이되 현지 권력/제도로 치환하지 않는다."
    elif country == "Thailand":
        dialogue_style = "대사 리듬과 감정선을 우선하는 자연스러운 구어체를 쓴다."
        proper_noun_policy = "고유명사는 음차 우선, 호칭은 작품 내 관계망을 훼손하지 않는 방식으로 유지한다."
        culture_policy = "한국 문화 요소는 과한 현지화 대신 맥락 설명 중심으로 다룬다."
    else:
        dialogue_style = "웹소설 문체의 속도감과 캐릭터 말맛을 살리는 자연스러운 구어체를 우선한다."
        proper_noun_policy = "고유명사는 glossary 중심으로 고정하고, 필요할 때만 짧게 보충 설명한다."
        culture_policy = "한국 문화 요소는 삭제하거나 다른 문화로 치환하지 말고, 이해를 돕는 최소 설명만 덧붙인다."

    return {
        "tone": f"{display} 독자에게도 과장 없이 읽히되 웹소설 특유의 속도감과 감정선을 살리는 톤",
        "dialogue_style": dialogue_style,
        "narration_style": "장면 기능과 시점 일관성을 유지하는 문장으로, 교과서식 평탄화는 피한다.",
        "localization_level": localization_level,
        "proper_noun_policy": proper_noun_policy,
        "culture_policy": culture_policy,
        "do_not": [
            "줄거리 변경 제안 금지",
            "결말 변경 제안 금지",
            "캐릭터 정체성 변경 제안 금지",
            "중심 갈등 변경 제안 금지",
            "장르나 서사 자체를 대상 국가에 맞춰 바꾸라는 제안 금지",
        ],
        "genre": genre,
        "country": country,
    }


def _evidence_from_row(row: dict[str, Any], reason: str) -> EvidenceItem:
    return EvidenceItem(
        platform=row.get("platform") or "unknown",
        collection=row.get("collection") or "unknown",
        rank=int(row.get("rank") or 0),
        title=row.get("title") or "",
        genre=row.get("genre"),
        tags=list(row.get("tags") or [])[:10],
        source_url=row.get("source_url"),
        reason=reason,
    )


def rank_countries(data: dict[str, Any], *, genre: str | None, synopsis: str | None) -> list[Recommendation]:
    genre_needles = _genre_needles(genre)
    synopsis_needles = _synopsis_needles(synopsis)
    grouped = _country_records(data)
    recommendations: list[Recommendation] = []
    for country, records in grouped.items():
        if country in EXCLUDED_RECOMMENDATION_COUNTRIES:
            continue
        score = 0.0
        reasons: Counter[str] = Counter()
        evidence_rows: list[tuple[float, dict[str, Any], str]] = []
        matched_rows = 0
        for row in records:
            text = _row_search_text(row)
            genre_hits = _match_count(text, genre_needles)
            synopsis_hits = _match_count(text, synopsis_needles)
            rank = int(row.get("rank") or 999)
            rank_weight = max(0.1, (120 - min(rank, 120)) / 120)
            row_score = (genre_hits * 3.0 + synopsis_hits * 1.2) * rank_weight
            if row_score <= 0:
                continue
            matched_rows += 1
            score += row_score
            if genre_hits:
                reasons["requested genre overlaps with platform-visible genres/tags"] += genre_hits
            if synopsis_hits:
                reasons["synopsis motifs overlap with exposed titles/descriptions/tags"] += synopsis_hits
            evidence_rows.append((row_score, row, f"genre hits={genre_hits}, synopsis hits={synopsis_hits}, rank={rank}"))
        if score == 0 and records:
            # Keep available countries visible even for weak matches; use top exposure as fallback evidence.
            top = sorted(records, key=lambda r: int(r.get("rank") or 999))[:3]
            evidence_rows = [(0.1, row, "fallback top platform exposure") for row in top]
            reasons["fallback: no strong genre/synopsis overlap found"] = 1
            score = 0.1
        else:
            # Normalize so larger crawls do not dominate the "country fit" chart just
            # because they have more rows. The score remains an overlap reference,
            # not a market-success prediction.
            coverage_bonus = min(1.0, matched_rows / max(1, len(records))) * 20.0
            score = (score / max(1, len(records))) * 100.0 + coverage_bonus
        evidence = [_evidence_from_row(row, reason) for _, row, reason in sorted(evidence_rows, key=lambda x: x[0], reverse=True)[:8]]
        recommendations.append(
            Recommendation(
                country=country,
                score=round(score, 3),
                reasons=[f"{label} ({count})" for label, count in reasons.most_common(5)],
                evidence=evidence,
            )
        )
    seen = {rec.country for rec in recommendations}
    for country in ALLOWED_COUNTRY_ORDER:
        if country in seen or country in EXCLUDED_RECOMMENDATION_COUNTRIES:
            continue
        recommendations.append(
            Recommendation(
                country=country,
                score=0.0,
                reasons=["fallback: no matching public platform evidence in the dataset"],
                evidence=[],
            )
        )
    return sorted(recommendations, key=lambda rec: rec.score, reverse=True)


def _country_profile(data: dict[str, Any], country: str):
    profiles = build_country_profiles(build_collection_profiles(data))
    normalized = normalize_country(country) or country
    for profile in profiles:
        if profile.country == normalized:
            return profile
    return profiles[0] if profiles else None


def _select_evidence(data: dict[str, Any], *, country: str, genre: str | None, synopsis: str | None, limit: int = 10) -> list[EvidenceItem]:
    normalized = normalize_country(country) or country
    recs = rank_countries(data, genre=genre, synopsis=synopsis)
    for rec in recs:
        if rec.country == normalized:
            return rec.evidence[:limit]
    records = _country_records(data).get(normalized, [])[:limit]
    return [_evidence_from_row(row, "country top exposure") for row in records]


def _section_payload(country_profile: Any, *, target_country: str, genre: str, synopsis: str, recommendations: list[Recommendation], evidence: list[EvidenceItem]) -> dict[str, Any]:
    top_genres = country_profile.top_genres[:8] if country_profile else []
    top_tags = country_profile.top_tags[:14] if country_profile else []
    signals = country_profile.localization_signals if country_profile else []
    guidance = country_profile.adaptation_guidance if country_profile else []
    cautions = country_profile.caution_points if country_profile else []
    synopsis_mode = bool(synopsis.strip())
    best_reasons = recommendations[0].reasons if recommendations else []
    genre_label = genre or '\ubbf8\uc9c0\uc815'  # '미지정' (py3.10 f-string 백슬래시 제약 회피)
    _top_genre_join = ', '.join(f'{g}({c})' for g, c in top_genres[:5])
    top_genres_label = _top_genre_join or '\uadfc\uac70 \ubd80\uc871'  # '근거 부족'
    synopsis_note = _synopsis_input_note(synopsis)
    inferred_motifs = _synopsis_motifs(synopsis)
    top_tag_line = f"순위권에서 자주 보인 키워드: {', '.join(f'{t}({c})' for t, c in top_tags[:8])}" if top_tags else "순위권 키워드 근거가 충분하지 않습니다."
    target_label = _display_country_label(target_country)
    recommendation_note = _recommendation_notice(synopsis_present=synopsis_mode)
    return {
        "market_trend_fit": {
            "title": "현지화 기준서 요약",
            "items": [
                f"대상 국가: {target_label} / 입력 장르: {genre_label}",
                synopsis_note,
                f"상위 장르 근거: {top_genres_label}",
                recommendation_note,
            ],
        },
        "genre_trope_alignment": {
            "title": "번역/표현 방향을 이렇게 읽었어요",
            "items": [
                f"입력 장르 `{genre_label}`을 우선 기준으로 삼되, 이야기 구조를 바꾸지 않고 번역 방향만 정리했습니다.",
                synopsis_note,
                f"추정 소재 축: {', '.join(inferred_motifs)}" if inferred_motifs else "추정 소재 축: 시놉시스 근거 부족 또는 미입력",
                "장면 톤과 캐릭터 말투는 살리고, 문장을 교과서식으로 평평하게 만들지 않습니다.",
            ]
            + signals[:4],
        },
        "title_synopsis_localization": {
            "title": f"{target_label} 독자에게는 어떻게 소개하면 좋을까요?",
            "items": [
                "플랫폼 상위 노출작은 장르 훅과 관계 축을 빠르게 드러내는 방식이 많지만, 이 가이드는 흥행 예측이 아니라 표현 방향 참고만 제공합니다.",
                f"시놉시스 기준으로는 {', '.join(inferred_motifs)}이 먼저 보입니다. 이 표현은 확정 태그가 아니라 소개문/태그 후보를 점검하기 위한 추정입니다." if inferred_motifs else "시놉시스 근거가 부족하므로 제목·소개문 후보는 장르의 대표 기대치 수준에서만 확인합니다.",
                "공개 시놉시스는 신호 분석에만 쓰고 문장을 그대로 복사하지 않습니다.",
            ],
        },
        "terminology_glossary_risks": {
            "title": f"{target_label} 고유명사·호칭·문화 요소 처리",
            "items": [
                top_tag_line,
                "이 키워드는 적용 지시가 아니라 대상 플랫폼에서 자주 보인 공개 태그/장르 표현입니다.",
                "고유명사, 스킬명, 계급명, 호칭은 작품 단위 glossary로 고정하고 태그 표현과 충돌하지 않는지 확인합니다.",
            ],
        },
        "content_rating_sensitivity": {
            "title": "플랫폼/문화권 검토 항목",
            "items": [
                "연령등급, 잔혹/성적 표현, 플랫폼별 금지·제한 표현은 시장 분위기와 별개로 확인합니다.",
                "시놉시스에서 나온 민감 요소는 위반 확정이 아니라 게시 전 확인 후보로 표시합니다." if synopsis_mode else "시놉시스가 없으면 민감 요소 확인은 장르 일반론을 넘어서 확정하지 않습니다.",
            ]
            + cautions[:5]
            + ["플랫폼별 노출 순서는 시장 전체가 아니라 해당 플랫폼 증거로만 표현합니다."],
        },
        "adaptation_checklist": {
            "title": "피해야 할 방식과 다음 확인",
            "items": guidance[:6] + [
                "최종 가이드는 스토리 수정 지시가 아니라 번역/현지화 기준서로만 사용합니다.",
                "본문 수집 없이 공개 메타데이터와 사용자가 입력한 시놉시스 신호만 사용합니다.",
            ],
        },
        "evidence_used": {
            "title": "\uc0ac\uc6a9 \uadfc\uac70",
            "items": [
                f"{ev.platform}/{ev.collection} rank {ev.rank}: {ev.title} ({ev.genre or 'genre unknown'}) - {ev.reason}"
                for ev in evidence[:8]
            ] or best_reasons or ["No direct evidence selected."],
        },
    }


def _model_prompt_payload(*, original: dict[str, Any], target_country: str, recommendations: list[Recommendation], sections: dict[str, Any], evidence: list[EvidenceItem]) -> dict[str, Any]:
    return {
        "role": "localization_guide_generator",
        "task": "Generate a pre-translation localization criteria guide. Do not rewrite the story, ending, character identity, or central conflict.",
        "original": original,
        "targetCountry": target_country,
        "recommendedCountries": [asdict(rec) for rec in recommendations[:3]],
        "evidence": [asdict(ev) for ev in evidence],
        "requiredOutputSections": list(sections.keys()),
        "claimLimit": "Phrase conclusions as first-pass localization fit, not market success prediction or national readership certainty.",
        "evidencePolicy": {
            "allowed": ["public rank/exposure metadata", "title", "genre", "tags", "public metrics", "public synopsis/description"],
            "excluded": ["episode/story body text", "paid or locked content", "login-only data", "image downloads"],
        },
        "translation_profile": _translation_profile(target_country, genre=original.get("genre") or "", synopsis_present=bool(original.get("synopsis"))),
    }


def _html_report(*, title: str, mode_label: str, target_country: str, genre: str, sections: dict[str, Any], recommendations: list[Recommendation]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value if value is not None else ""))

    section_html = []
    for key, section in sections.items():
        items = "".join(f"<li>{esc(item)}</li>" for item in section.get("items", []))
        section_html.append(
            f"<div class='guide-section'><div class='guide-section-header'><span class='guide-section-title'>{esc(section.get('title', key))}</span></div><ul class='guide-list'>{items}</ul></div>"
        )
    rec_html = "".join(
        f"<li>{esc(rec.country)}: {esc(rec.score)} — {esc('; '.join(rec.reasons[:3]))}</li>"
        for rec in recommendations[:3]
    )
    display_country = _display_country_label(target_country)
    return f"""
    <div class="guide-report">
      <div class="guide-cover">
        <div class="guide-cover-label">번역 전 현지화 기준서 · 플랫폼 참고 근거</div>
        <div class="guide-cover-title">{esc(display_country)} 현지화 기준서<br><em>번역/표현 방향 리포트</em></div>
        <div class="guide-cover-sub"><span>{esc(mode_label)}</span><span>{esc(genre or 'genre unspecified')}</span><span>current platform trends</span></div>
      </div>
      <div class="guide-legacy-anchors">번역 방향 · 문화 주의사항 · 플랫폼 검토 항목</div>
      <div class="guide-section"><div class="guide-section-header"><span class="guide-section-title">추천 국가 후보</span></div><ul class="guide-list">{rec_html}</ul></div>
      {''.join(section_html)}
    </div>
    """


def _display_country_label(target_country: str) -> str:
    key = str(target_country).strip()
    return COUNTRY_DISPLAY_KO.get(key, key)


def _recommendation_payload(recommendations: list[Recommendation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in recommendations:
        item = asdict(rec)
        item["displayCountry"] = _display_country_label(rec.country)
        rows.append(item)
    return rows


def recommend_country(payload: dict[str, Any], *, data_path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    data = load_trend_data(data_path)
    genre = _text(payload.get("genre"))
    synopsis = _text(payload.get("synopsis") or payload.get("desc"))
    requested_country = normalize_country(payload.get("targetCountry") or payload.get("country"))
    recommendations = rank_countries(data, genre=genre, synopsis=synopsis)
    available_options_payload = available_options(data)
    limitation_notice = _recommendation_notice(synopsis_present=bool(synopsis))

    if not synopsis and not requested_country:
        return {
            "mode": "needs_country_and_genre_selection",
            "requiresSelection": True,
            "message": "시놉시스가 없어 국가 추천은 제공할 수 없습니다. 대상 국가를 직접 선택하면 번역 전 현지화 기준서를 만들 수 있습니다.",
            "availableOptions": available_options_payload,
            "available_countries": _available_countries(),
            "limitation_notice": limitation_notice,
            "recommendation_reasons": [],
            "recommended_country": None,
            "recommendedCountries": [],
            "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    if synopsis and not requested_country:
        top = recommendations[0] if recommendations else None
        return {
            "mode": "synopsis_country_recommendation",
            "requiresSelection": True,
            "title": "추천 국가를 먼저 확인해 주세요",
            "genre": genre,
            "synopsis": synopsis,
            "availableOptions": available_options_payload,
            "available_countries": _available_countries(),
            "recommended_country": top.country if top else None,
            "recommended_country_display": _display_country_label(top.country) if top else None,
            "recommendation_reasons": top.reasons if top else [],
            "recommendedCountries": _recommendation_payload(recommendations[:3]),
            "limitation_notice": limitation_notice,
            "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    selected_country = requested_country or (recommendations[0].country if recommendations else "US/global English")
    top = recommendations[0] if recommendations else None
    selected_display = _display_country_label(selected_country)
    return {
        "mode": "synopsis_country_recommendation" if synopsis else "country_genre_guide",
        "requiresSelection": False,
        "targetCountry": selected_country,
        "targetCountryDisplay": selected_display,
        "country": selected_country,
        "displayCountry": selected_display,
        "recommended_country": top.country if top else None,
        "recommended_country_display": _display_country_label(top.country) if top else None,
        "recommendation_reasons": top.reasons if top else [],
        "recommendedCountries": _recommendation_payload(recommendations[:3]),
        "available_countries": _available_countries(),
        "limitation_notice": limitation_notice,
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def generate_localization_guide(payload: dict[str, Any], *, data_path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    data = load_trend_data(data_path)
    genre = _text(payload.get("genre"))
    synopsis = _text(payload.get("synopsis") or payload.get("desc"))
    requested_country = normalize_country(payload.get("targetCountry") or payload.get("country"))
    if not requested_country:
        return recommend_country(payload, data_path=data_path)

    recommendations = rank_countries(data, genre=genre, synopsis=synopsis)
    top = recommendations[0] if recommendations else None
    selected_country = requested_country
    selected_display = _display_country_label(selected_country)
    profile = _country_profile(data, selected_country)
    evidence = _select_evidence(data, country=selected_country, genre=genre, synopsis=synopsis)
    synopsis_present = bool(synopsis)
    generation_mode = (
        "recommended_country_selected"
        if synopsis_present and top and selected_country == top.country
        else "manual_country_after_recommendation"
        if synopsis_present
        else "manual_country_without_synopsis"
    )
    sections = _section_payload(
        profile,
        target_country=selected_country,
        genre=genre,
        synopsis=synopsis,
        recommendations=recommendations,
        evidence=evidence,
    )
    translation_profile = _translation_profile(selected_country, genre=genre, synopsis_present=synopsis_present)
    recommendation_notice = _recommendation_notice(synopsis_present=synopsis_present)
    recommended_country = top.country if synopsis_present and top else None
    recommendation_reasons = top.reasons if synopsis_present and top else (
        ["시놉시스가 없어 국가 추천을 제공하지 않았습니다."]
        if not synopsis_present
        else []
    )
    display_title = f"{selected_display} 현지화 기준서"
    summary_text = (
        f"{selected_display} 중심으로 번역 전 현지화 기준을 정리했습니다."
        if not synopsis_present
        else f"{selected_display}는 시놉시스 기반 1차 적합도 추천을 반영한 현지화 기준서입니다."
    )
    original = {
        "title": payload.get("title"),
        "genre": genre,
        "synopsis": synopsis,
        "tags": payload.get("tags") or [],
        "ageRating": payload.get("ageRating") or payload.get("rating"),
        "glossary": payload.get("glossary") or {},
    }
    result = {
        "mode": "country_genre_guide",
        "generationMode": generation_mode,
        "generation_mode": generation_mode,
        "requiresSelection": False,
        "title": display_title,
        "country": selected_country,
        "targetCountry": selected_country,
        "displayCountry": selected_display,
        "targetCountryDisplay": selected_display,
        "genre": genre,
        "synopsis": synopsis,
        "recommended_country": recommended_country,
        "recommended_country_display": _display_country_label(recommended_country) if recommended_country else None,
        "recommendation_reasons": recommendation_reasons,
        "limitation_notice": recommendation_notice,
        "available_countries": _available_countries(),
        "availableOptions": available_options(data),
        "recommendedCountries": _recommendation_payload(recommendations[:3]) if synopsis_present else [],
        "translation_profile": translation_profile,
        "translationProfile": translation_profile,
        "summary_text": summary_text,
        "summaryText": summary_text,
        "sections": sections,
        "evidenceUsed": [asdict(ev) for ev in evidence],
        "modelPromptPayload": _model_prompt_payload(
            original=original,
            target_country=selected_country,
            recommendations=recommendations,
            sections=sections,
            evidence=evidence,
        ),
        "guide_html": _html_report(
            title=display_title,
            mode_label="시놉시스 기반 추천 반영" if synopsis_present else "국가/장르 기반 기준서",
            target_country=selected_country,
            genre=genre,
            sections=sections,
            recommendations=recommendations,
        ),
        "htmlReport": _html_report(
            title=display_title,
            mode_label="시놉시스 기반 추천 반영" if synopsis_present else "국가/장르 기반 기준서",
            target_country=selected_country,
            genre=genre,
            sections=sections,
            recommendations=recommendations,
        ),
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    # Backward-compatible aliases for older UI/tests.
    result["writingDirection"] = {
        "genre_formula": sections["genre_trope_alignment"]["items"],
        "chapter_structure": sections["title_synopsis_localization"]["items"],
    }
    result["cultureNotes"] = {"avoid": sections["content_rating_sensitivity"]["items"], "prefer": sections["adaptation_checklist"]["items"]}
    result["platformRules"] = {"common_bans": sections["content_rating_sensitivity"]["items"], "platforms": []}
    result["localizationTips"] = {"marketing_tags": sections["title_synopsis_localization"]["items"], "translation_quality": sections["terminology_glossary_risks"]["items"]}
    result["tags"] = [genre, selected_country, "현지화", "플랫폼 트렌드"]
    return result


def build_localization_advice(payload: dict[str, Any], *, data_path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    """Backward-compatible wrapper for the guide flow."""

    return generate_localization_guide(payload, data_path=data_path)

