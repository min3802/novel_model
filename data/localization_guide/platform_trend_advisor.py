
from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from data.localization_guide.platform_trend_guide import (
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
    "romance": ["romance", "love", "marriage", "husband", "wife", "duke", "prince", "villainess", "\uc57d\ud63c", "\uacb0\ud63c", "\uacf5\uc791", "\ud669\ud0dc\uc790", "\uc545\ub140", KO_ROMANCE, "\uc0ac\ub791"],
    "progression": ["level", "skill", "system", "rank", "dungeon", "quest", "\uc131\uc7a5", "\uc2a4\ud0ac", "\ub808\ubca8", "\uc2dc\uc2a4\ud15c", "\ub358\uc804", "\ub7ad\ucee4"],
    "isekai": ["reincarn", "isekai", "another world", "transport", "\ud68c\uadc0", KO_REINCARNATION, "\ube59\uc758", KO_ISEKAI, "\ud658\uc0dd"],
    "action": ["battle", "war", "fight", "survival", "apocalypse", "\uc804\ud22c", "\uc804\uc7c1", "\uc0dd\uc874", "\uba78\ub9dd", "\uc544\ud3ec\uce7c\ub9bd\uc2a4"],
    "bl": ["omega", "alpha", "bl", "boys love", "\ub0a8\uc790", "\uc624\uba54\uac00", "\uc54c\ud30c"],
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
    words = re.findall(r"[a-z][a-z0-9+/-]{2,}|[?-?]{2,}|[?-??-??-??]{2,}", lowered)
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
    countries = build_country_profiles(collection_profiles)
    return {
        "countries": [
            {
                "country": country.country,
                "topGenres": country.top_genres[:8],
                "topTags": country.top_tags[:12],
                "platforms": [f"{p.platform} / {p.collection}" for p in country.collections],
            }
            for country in countries
        ],
        "genres": sorted(GENRE_ALIASES.keys()),
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
        score = 0.0
        reasons: Counter[str] = Counter()
        evidence_rows: list[tuple[float, dict[str, Any], str]] = []
        for row in records:
            text = _row_search_text(row)
            genre_hits = _match_count(text, genre_needles)
            synopsis_hits = _match_count(text, synopsis_needles)
            rank = int(row.get("rank") or 999)
            rank_weight = max(0.1, (120 - min(rank, 120)) / 120)
            row_score = (genre_hits * 3.0 + synopsis_hits * 1.2) * rank_weight
            if row_score <= 0:
                continue
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
        evidence = [_evidence_from_row(row, reason) for _, row, reason in sorted(evidence_rows, key=lambda x: x[0], reverse=True)[:8]]
        recommendations.append(
            Recommendation(
                country=country,
                score=round(score, 3),
                reasons=[f"{label} ({count})" for label, count in reasons.most_common(5)],
                evidence=evidence,
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
    return {
        "market_trend_fit": {
            "title": "\uc2dc\uc7a5 \ud2b8\ub80c\ub4dc \uc801\ud569\ub3c4",
            "items": [
                f"\uc120\ud0dd/\ucd94\ucc9c \uad6d\uac00: {target_country}",
                f"\uc694\uccad \uc7a5\ub974: {genre or '\ubbf8\uc9c0\uc815'}",
                f"\uc0c1\uc704 \uc7a5\ub974 \uadfc\uac70: {', '.join(f'{g}({c})' for g, c in top_genres[:5]) or '\uadfc\uac70 \ubd80\uc871'}",
                "\uc2dc\ub189\uc2dc\uc2a4 \uae30\ubc18 \uad6d\uac00 \ucd94\ucc9c \ud750\ub984\uc785\ub2c8\ub2e4." if synopsis_mode else "\uad6d\uac00\uc640 \uc7a5\ub974 \uc120\ud0dd \uae30\ubc18 \uac00\uc774\ub4dc \ud750\ub984\uc785\ub2c8\ub2e4.",
            ],
        },
        "genre_trope_alignment": {
            "title": "\uc7a5\ub974/\ud2b8\ub85c\ud504 \uc815\ub82c",
            "items": signals[:6] + [f"\ubc18\ubcf5 \ud0dc\uadf8: {', '.join(f'{t}({c})' for t, c in top_tags[:8])}"] if top_tags else signals[:6],
        },
        "title_synopsis_localization": {
            "title": "\uc81c\ubaa9/\uc2dc\ub189\uc2dc\uc2a4 \ud604\uc9c0\ud654",
            "items": [
                "\ud50c\ub7ab\ud3fc \uc0c1\uc704 \ub178\ucd9c\uc791\uc758 \uc81c\ubaa9\u00b7\uc18c\uac1c\ubb38\uc740 \uc7a5\ub974 \ud6c5\uc744 \ube60\ub974\uac8c \ub4dc\ub7ec\ub0b4\ub294 \ubc29\ud5a5\uc73c\ub85c \uc555\ucd95\ud569\ub2c8\ub2e4.",
                "\uc2dc\ub189\uc2dc\uc2a4\uac00 \uc81c\uacf5\ub41c \uacbd\uc6b0, \uc6d0\ubb38 \uc18c\uc7ac\ub97c \uc2dc\uc7a5 \uc0c1\uc704 \uc7a5\ub974/\ud0dc\uadf8 \uc5b8\uc5b4\ub85c \uc7ac\uc815\ub82c\ud569\ub2c8\ub2e4." if synopsis_mode else "\uc2dc\ub189\uc2dc\uc2a4\uac00 \uc5c6\uc73c\ubbc0\ub85c \uc120\ud0dd \uc7a5\ub974\uc758 \ub300\ud45c \ud6c5 \uad6c\uc870\ub97c \uba3c\uc800 \uc81c\uc548\ud569\ub2c8\ub2e4.",
                "\uacf5\uac1c \uc2dc\ub189\uc2dc\uc2a4\ub294 \uc2e0\ud638 \ubd84\uc11d\uc5d0\ub9cc \uc4f0\uace0 \ubb38\uc7a5\uc744 \ubcf5\uc0ac\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.",
            ],
        },
        "terminology_glossary_risks": {
            "title": "\uc6a9\uc5b4/\uae00\ub85c\uc11c\ub9ac \ub9ac\uc2a4\ud06c",
            "items": [
                "\uace0\uc720\uba85\uc0ac, \uc2a4\ud0ac\uba85, \uacc4\uae09\uba85, \ud638\uce6d\uc740 \uc791\ud488 \ub2e8\uc704 glossary\ub85c \uace0\uc815\ud569\ub2c8\ub2e4.",
                "\ud55c\uad6d \uc81c\ub3c4/\ud559\uad50/\uad70\ub300/\uac00\uc871 \ud638\uce6d\uc740 \ub300\uc0c1 \uc2dc\uc7a5 \ub3c5\uc790\uac00 \uc774\ud574\ud560 \uc218 \uc788\uac8c \uc124\uba85\ub7c9\uc744 \uc870\uc808\ud569\ub2c8\ub2e4.",
                "\uc7a5\ub974 \ud0dc\uadf8\uc640 \ubcf8\ubb38 \uc6a9\uc5b4\uac00 \ucda9\ub3cc\ud558\uc9c0 \uc54a\ub3c4\ub85d \ubc88\uc5ed \ud6c4 consistency check\uac00 \ud544\uc694\ud569\ub2c8\ub2e4.",
            ],
        },
        "content_rating_sensitivity": {
            "title": "\uc5f0\ub839\ub4f1\uae09/\ubbfc\uac10\ub3c4",
            "items": cautions[:5] + ["\ud50c\ub7ab\ud3fc\ubcc4 \ub178\ucd9c \uc21c\uc11c\ub294 \uc2dc\uc7a5 \uc804\uccb4\uac00 \uc544\ub2c8\ub77c \ud574\ub2f9 \ud50c\ub7ab\ud3fc \uc99d\uac70\ub85c\ub9cc \ud45c\ud604\ud569\ub2c8\ub2e4."],
        },
        "adaptation_checklist": {
            "title": "\uad6c\uccb4 \uc801\uc6a9 \uccb4\ud06c\ub9ac\uc2a4\ud2b8",
            "items": guidance[:6] + [
                "\ucd5c\uc885 \uac00\uc774\ub4dc\uc5d0\ub294 \uc0ac\uc6a9\ud55c \ud50c\ub7ab\ud3fc, \uc218\uc9d1\uc77c, rank evidence\ub97c \ud568\uaed8 \ub0a8\uae41\ub2c8\ub2e4.",
                "\ubcf8\ubb38 \uc218\uc9d1 \uc5c6\uc774 \uacf5\uac1c \uba54\ud0c0\ub370\uc774\ud130\uc640 \uc2dc\ub189\uc2dc\uc2a4 \uc2e0\ud638\ub9cc \uc0ac\uc6a9\ud569\ub2c8\ub2e4.",
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
        "task": "Generate a Korean webnovel localization guide using the selected/recommended market and platform trend evidence.",
        "original": original,
        "targetCountry": target_country,
        "recommendedCountries": [asdict(rec) for rec in recommendations[:3]],
        "evidence": [asdict(ev) for ev in evidence],
        "requiredOutputSections": list(sections.keys()),
        "claimLimit": "Phrase conclusions as platform trend evidence, not national readership certainty.",
        "evidencePolicy": {
            "allowed": ["public rank/exposure metadata", "title", "genre", "tags", "public metrics", "public synopsis/description"],
            "excluded": ["episode/story body text", "paid or locked content", "login-only data", "image downloads"],
        },
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
        f"<li>{esc(rec.country)}: {esc(rec.score)} ? {esc('; '.join(rec.reasons[:3]))}</li>"
        for rec in recommendations[:3]
    )
    return f"""
    <div class="guide-report">
      <div class="guide-cover">
        <div class="guide-cover-label">Localization Guide ? Platform Trend Evidence</div>
        <div class="guide-cover-title">{esc(target_country)} ???<br><em>??? ???</em></div>
        <div class="guide-cover-sub"><span>{esc(mode_label)}</span><span>{esc(genre or 'genre unspecified')}</span><span>current platform trends</span></div>
      </div>
      <div class="guide-legacy-anchors">작성 방향 ? 문화 주의사항 ? 플랫폼 규정</div>
      <div class="guide-section"><div class="guide-section-header"><span class="guide-section-title">추천 국가 후보</span></div><ul class="guide-list">{rec_html}</ul></div>
      {''.join(section_html)}
    </div>
    """


def build_localization_advice(payload: dict[str, Any], *, data_path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    data = load_trend_data(data_path)
    genre = _text(payload.get("genre"))
    synopsis = _text(payload.get("synopsis") or payload.get("desc"))
    requested_country = normalize_country(payload.get("targetCountry") or payload.get("country"))

    if not synopsis and not requested_country:
        return {
            "mode": "needs_country_and_genre_selection",
            "requiresSelection": True,
            "message": "????? ??? ??? ??? ?? ???? ???.",
            "availableOptions": available_options(data),
            "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    recommendations = rank_countries(data, genre=genre, synopsis=synopsis)
    target_country = requested_country or (recommendations[0].country if recommendations else "US/global English")
    profile = _country_profile(data, target_country)
    evidence = _select_evidence(data, country=target_country, genre=genre, synopsis=synopsis)
    mode = "synopsis_country_recommendation" if synopsis else "country_genre_guide"
    sections = _section_payload(
        profile,
        target_country=target_country,
        genre=genre,
        synopsis=synopsis,
        recommendations=recommendations,
        evidence=evidence,
    )
    original = {
        "title": payload.get("title"),
        "genre": genre,
        "synopsis": synopsis,
        "tags": payload.get("tags") or [],
        "ageRating": payload.get("ageRating") or payload.get("rating"),
        "glossary": payload.get("glossary") or {},
    }
    mode_label = "???? ?? ?? ??" if synopsis else "??/?? ?? ??"
    result = {
        "mode": mode,
        "requiresSelection": False,
        "title": f"{target_country} ??? ???",
        "country": target_country,
        "targetCountry": target_country,
        "genre": genre,
        "synopsis": synopsis,
        "recommendedCountries": [asdict(rec) for rec in recommendations[:3]],
        "sections": sections,
        "evidenceUsed": [asdict(ev) for ev in evidence],
        "modelPromptPayload": _model_prompt_payload(
            original=original,
            target_country=target_country,
            recommendations=recommendations,
            sections=sections,
            evidence=evidence,
        ),
        "htmlReport": _html_report(
            title=f"{target_country} ??? ???",
            mode_label=mode_label,
            target_country=target_country,
            genre=genre,
            sections=sections,
            recommendations=recommendations,
        ),
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    # Backward-compatible aliases for older UI/tests.
    result["writingDirection"] = {"genre_formula": sections["genre_trope_alignment"]["items"], "chapter_structure": sections["title_synopsis_localization"]["items"]}
    result["cultureNotes"] = {"avoid": sections["content_rating_sensitivity"]["items"], "prefer": sections["adaptation_checklist"]["items"]}
    result["platformRules"] = {"common_bans": sections["content_rating_sensitivity"]["items"], "platforms": []}
    result["localizationTips"] = {"marketing_tags": sections["title_synopsis_localization"]["items"], "translation_quality": sections["terminology_glossary_risks"]["items"]}
    result["tags"] = [genre, target_country, "???", "??? ???"]
    return result
