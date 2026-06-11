from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .work_analysis import normalize_country_code


ROOT = Path(__file__).resolve().parents[2]
KCULTURE_RAG_PATH = ROOT / "data" / "annotation_rag" / "kculture_rag_documents_reviewed.json"
CULTURAL_TERMS_PATH = ROOT / "data" / "cultural_terms" / "ko_cultural_terms.json"
CULTURAL_REVIEW_DIR = ROOT / "prompts" / "cultural_review"


COUNTRY_FILE = {
    "US": "CULTURAL_CONSTRAINTS_US.md",
    "JP": "CULTURAL_CONSTRAINTS_JP.md",
    "CN": "CULTURAL_CONSTRAINTS_CN.md",
    "TH": "CULTURAL_CONSTRAINTS_TH.md",
}

CULTURE_TRIGGER_ELEMENTS = {
    "예비군",
    "군 복무",
    "학원/입시 문화",
    "한국 의례/관습",
    "주거/돈 제도",
    "현대 한국 배경",
    "종교/의례 민감성",
}

CAUTION_TO_CONSTRAINT_KEYWORDS = {
    "성적 묘사": ("sexual", "minor"),
    "성폭력 소재": ("sexual", "violence", "minor", "abuse"),
    "잔혹 묘사": ("violence", "gore", "self-harm"),
    "트라우마/정서적 상처": ("self-harm", "harassment", "abuse"),
    "혐오/차별 가능성": ("racial", "gender", "religious", "disability", "hate"),
    "종교/의례 민감성": ("religious",),
    "미성년자 관련 표현": ("minor", "sexual"),
}


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[0-9A-Za-z\uAC00-\uD7A3]{2,}", text or "")}


@lru_cache(maxsize=1)
def _load_kculture_cards() -> list[dict[str, Any]]:
    if not KCULTURE_RAG_PATH.exists():
        return []
    payload = json.loads(KCULTURE_RAG_PATH.read_text(encoding="utf-8"))
    return [item for item in payload if isinstance(item, dict)]


@lru_cache(maxsize=1)
def _load_cultural_terms() -> list[dict[str, Any]]:
    if not CULTURAL_TERMS_PATH.exists():
        return []
    payload = json.loads(CULTURAL_TERMS_PATH.read_text(encoding="utf-8"))
    return [item for item in payload if isinstance(item, dict)]


@lru_cache(maxsize=8)
def _load_constraint_categories(country_code: str | None) -> list[dict[str, str]]:
    if not country_code:
        return []
    filename = COUNTRY_FILE.get(country_code)
    if not filename:
        return []
    path = CULTURAL_REVIEW_DIR / filename
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 5 or parts[0] == "ID" or set(parts[0]) <= {"-"}:
            continue
        rows.append(
            {
                "id": parts[0],
                "category": parts[1],
                "severity": parts[2],
                "action": parts[3],
                "triggers": parts[4],
            }
        )
    return rows


def _term_strings(card: dict[str, Any]) -> list[str]:
    metadata = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
    fields = [
        card.get("id"),
        metadata.get("keyword_ko"),
        card.get("embedding_text"),
        card.get("context_text"),
    ]
    terms: list[str] = []
    for field in fields:
        terms.extend(_tokens(str(field or "")))
    return list(dict.fromkeys(terms))


def _term_lexicon_strings(entry: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("term_ko", "terms", "aliases", "category"):
        raw = entry.get(key)
        if isinstance(raw, list):
            values.extend(str(item) for item in raw)
        elif raw:
            values.append(str(raw))
    terms: list[str] = []
    for value in values:
        terms.extend(_tokens(value))
    return list(dict.fromkeys(terms))


def _culture_query(work_profile: dict[str, Any]) -> str:
    elements = [str(item) for item in work_profile.get("confirmedElements") or []]
    cultural_elements = [item for item in elements if item in CULTURE_TRIGGER_ELEMENTS]
    if not cultural_elements:
        return ""
    query = "\n".join(
        [
            str(work_profile.get("title") or ""),
            str(work_profile.get("synopsis") or ""),
            " ".join(cultural_elements),
        ]
    )
    return query


def _match_kculture(work_profile: dict[str, Any]) -> list[dict[str, Any]]:
    query = _culture_query(work_profile)
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    matches: list[tuple[int, dict[str, Any]]] = []
    for card in _load_kculture_cards():
        metadata = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
        keyword = str(metadata.get("keyword_ko") or "").strip()
        terms = set(_term_strings(card))
        score = len(query_tokens & terms)
        if keyword and keyword in query:
            score += 5
        if score >= 3:
            matches.append((score, card))
    matches.sort(key=lambda item: item[0], reverse=True)
    return [card for _, card in matches[:5]]


def _match_lexicon(work_profile: dict[str, Any]) -> list[dict[str, Any]]:
    query = _culture_query(work_profile)
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    matches: list[dict[str, Any]] = []
    for entry in _load_cultural_terms():
        term = str(entry.get("term_ko") or "").strip()
        score = len(query_tokens & set(_term_lexicon_strings(entry)))
        if term and term in query:
            score += 5
        if score >= 2:
            matches.append(entry)
    return matches[:5]


def _note_from_card(card: dict[str, Any], country_display: str) -> dict[str, Any]:
    metadata = card.get("metadata") if isinstance(card.get("metadata"), dict) else {}
    element = str(metadata.get("keyword_ko") or card.get("id") or "한국 문화 요소")
    context = str(card.get("context_text") or card.get("embedding_text") or "").strip()
    guide = "고유명사를 무리하게 현지 제도로 바꾸기보다 첫 등장이나 소개문에서 의미를 짧게 보완하는 방향을 검토합니다."
    if "번역 가이드:" in context:
        guide = context.split("번역 가이드:", 1)[1].strip().splitlines()[0]
    return {
        "element": element,
        "issue": f"{country_display} 독자에게 {element}의 한국적 맥락이 익숙하지 않을 수 있습니다.",
        "guide": guide,
        "confidence": "high",
        "source": card.get("id"),
    }


def _has_korean_text(value: str) -> bool:
    return bool(re.search(r"[\uAC00-\uD7A3]", value or ""))


def build_cultural_localization(payload: dict[str, Any], work_profile: dict[str, Any]) -> dict[str, Any]:
    country_code = normalize_country_code(
        payload.get("targetCountry")
        or payload.get("target_country")
        or payload.get("targetMarket")
        or payload.get("target_market")
        or payload.get("country")
        or work_profile.get("targetCountry")
    )
    country_display = work_profile.get("targetCountryDisplay") or country_code or "대상 국가"
    culture_cards = _match_kculture(work_profile)
    lexicon_matches = _match_lexicon(work_profile)
    constraints = _load_constraint_categories(country_code)

    notes = [_note_from_card(card, str(country_display)) for card in culture_cards[:4]]
    cultural_elements = [
        str(item)
        for item in work_profile.get("confirmedElements") or []
        if str(item) in CULTURE_TRIGGER_ELEMENTS
    ]
    if not notes and cultural_elements:
        notes.append(
            {
                "element": cultural_elements[0],
                "issue": f"{country_display} 독자에게 {cultural_elements[0]}의 한국적 맥락이 익숙하지 않을 수 있습니다.",
                "guide": "구체적인 문화 카드가 매칭되지 않았으므로, 소개문에서는 필요한 경우에만 의미를 짧게 보완하고 본문 맥락으로 설명합니다.",
                "confidence": "medium",
                "source": "work_profile.cultural_element",
            }
        )
    if not notes and work_profile.get("mode") == "detailed":
        source_text = "\n".join(
            [
                str(work_profile.get("title") or ""),
                str(work_profile.get("genre") or ""),
                str(work_profile.get("synopsis") or ""),
            ]
        )
        if _has_korean_text(source_text):
            notes.append(
                {
                    "element": "한국어 원문 관계 표현",
                    "issue": f"{country_display} 독자에게 인물 간 호칭·말투·거리감이 직역만으로는 덜 자연스러울 수 있습니다.",
                    "guide": "작품에 없는 제도 설명을 추가하지 말고, 소개문/메타데이터에서는 관계 구도와 감정선을 자연스러운 대상 언어 표현으로 정리합니다.",
                    "confidence": "medium",
                    "source": "detailed_korean_source_text",
                }
            )
    risk_notes: list[dict[str, Any]] = []
    cautions = set(str(item) for item in work_profile.get("contentCautions") or [])
    constraint_keywords = {
        keyword
        for caution in cautions
        for keyword in CAUTION_TO_CONSTRAINT_KEYWORDS.get(caution, ())
    }
    for row in constraints:
        category = row.get("category", "")
        trigger = row.get("triggers", "")
        haystack = f"{category} {trigger}".lower()
        if constraint_keywords and any(keyword in haystack for keyword in constraint_keywords):
            risk_notes.append(
                {
                    "category": category,
                    "severity": row.get("severity"),
                    "guide": "시놉시스 수준에서는 위반으로 단정하지 말고 본문 표현 수위와 소개문 노출 정도를 확인합니다.",
                    "triggerReference": trigger,
                }
            )
        if len(risk_notes) >= 4:
            break

    if notes:
        directions = [
            "한국적 제도와 관습은 완전 대체보다 유지+짧은 의미 보완을 우선 검토합니다.",
            "제목/소개문에서는 세계관 설명을 길게 늘리기보다 주인공, 관계 구도, 핵심 갈등 이해에 필요한 문화 요소만 드러냅니다.",
        ]
    else:
        directions = [
            "현재 확인된 작품 요소만으로는 별도 문화 설명이 필요한 한국 제도/관습을 특정하지 않았습니다.",
            "로맨스 관계·작가물·계약 관계 같은 메타데이터 요소는 문화 RAG 근거 없이 한국 문화 노트로 확장하지 않습니다.",
        ]
    if lexicon_matches:
        directions.append(
            "문화 용어 후보("
            + ", ".join(str(item.get("term_ko") or item.get("id")) for item in lexicon_matches[:3])
            + ")는 번역 전 별도 표기/설명 방식을 정리합니다."
        )

    return {
        "cultureNotes": notes,
        "localizationDirections": directions,
        "cultureRiskCheckpoints": risk_notes,
        "doNotOverclaim": [
            "대상 국가의 제도와 한국 제도가 동일하다고 설명하지 않습니다.",
            "플랫폼 관찰 데이터만으로 독자 취향이나 흥행 가능성을 단정하지 않습니다.",
            "시놉시스만 보고 본문 위반 여부를 확정하지 않습니다.",
        ],
        "evidence": {
            "kcultureCardCount": len(culture_cards),
            "lexiconMatchCount": len(lexicon_matches),
            "constraintCount": len(constraints),
            "countryCode": country_code,
        },
    }
