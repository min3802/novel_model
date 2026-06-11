from __future__ import annotations

import re
from typing import Any


COUNTRY_DISPLAY = {
    "US": "미국",
    "JP": "일본",
    "CN": "중국",
    "TH": "태국",
}

COUNTRY_CODE_ALIASES = {
    "us": "US",
    "usa": "US",
    "united states": "US",
    "english": "US",
    "미국": "US",
    "영어권": "US",
    "jp": "JP",
    "japan": "JP",
    "일본": "JP",
    "日本": "JP",
    "cn": "CN",
    "china": "CN",
    "중국": "CN",
    "th": "TH",
    "thailand": "TH",
    "태국": "TH",
}


ELEMENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("예비군", ("예비군", "비상소집", "동원훈련")),
    ("군 복무", ("군대", "군 복무", "병역", "입대", "전역", "징병")),
    ("현대 한국 배경", ("한국", "서울", "강남")),
    ("직장물", ("회사", "직장", "상사", "팀장")),
    ("학원/입시 문화", ("학원", "수능", "입시", "고3", "재수")),
    ("회귀/전생/이세계 축", ("회귀", "전생", "이세계", "환생")),
    ("복수 서사", ("복수", "응징", "되갚")),
    ("귀족/궁정 관계", ("공녀", "왕녀", "황녀", "공작", "궁정", "귀족", "악역영애")),
    ("로맨스 관계", ("로맨스", "연애", "계약 결혼", "혼약", "남주", "여주")),
    ("작가물", ("작가", "소설가", "웹소설", "집필", "원고", "출판")),
    ("계약 관계", ("계약 관계", "계약 결혼", "계약 연애", "계약", "비즈니스 관계")),
    ("혐관 로맨스", ("혐관", "앙숙", "원수", "티격태격", "싫어하던", "대립하던")),
    ("상처 치유", ("상처", "치유", "트라우마", "회복", "구원")),
    ("감정 성장", ("감정 성장", "성장", "변화", "마음을 열", "관계가 변")),
    ("전투/생존 축", ("전투", "생존", "던전", "괴물", "마물", "전쟁")),
    ("빙의/각성 소재", ("빙의", "각성", "헌터", "스킬", "상태창")),
    ("가족/가문 갈등", ("가문", "가족", "아버지", "어머니", "형제", "자매")),
    ("한국 의례/관습", ("축의금", "49재", "제사", "장례", "명절")),
    ("주거/돈 제도", ("전세", "월세", "보증금", "대출")),
]

ELEMENT_ALIAS_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("작가물", ("작가와 작가", "작가물", "소설가", "웹소설 작가")),
    ("계약 관계", ("계약관계", "계약 관계", "계약 연애", "계약 결혼")),
    ("혐관 로맨스", ("혐관에서 로맨스", "혐관 로맨스", "혐관", "앙숙 로맨스")),
    ("상처 치유", ("상처녀", "상처 치유", "감정 치유", "전애인 트라우마")),
    ("감정 성장", ("성장형 로맨스", "감정 성장", "관계 성장")),
    ("로맨스 관계", ("순정남", "로맨스", "멜로", "휴먼 멜로", "로맨틱 코미디")),
]

CAUTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("성적 묘사", ("성적", "성인", "19금", "R18", "노출")),
    ("성폭력 소재", ("강간", "성폭력", "성추행", "비동의")),
    ("잔혹 묘사", ("잔혹", "유혈", "고문", "살해", "살인", "학살", "피의", "폭력")),
    ("트라우마/정서적 상처", ("트라우마", "정서적 상처", "학대", "상처", "불안", "우울")),
    ("미성년자 관련 표현", ("미성년", "학생", "고등학생", "중학생", "아동", "청소년")),
    ("혐오/차별 가능성", ("혐오", "차별", "비하", "인종", "성소수자", "장애")),
    ("저작권/표지 사용 권한", ("패러디", "실존", "상표", "저작권", "표지", "팬픽")),
    ("군사/국가 시스템", ("군대", "병역", "예비군", "전쟁", "국가", "징병")),
    ("종교/의례 민감성", ("종교", "불교", "기독교", "무속", "제사", "49재")),
]


def normalize_country_code(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return COUNTRY_CODE_ALIASES.get(text.lower()) or COUNTRY_CODE_ALIASES.get(text) or text.upper()


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for chunk in value.split("\n") for part in chunk.split(",") if part.strip()]
    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _explicit_terms(payload: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in ("titleElements", "title_elements", "declaredSignals", "declared_signals", "signals", "tags"):
        terms.extend(_list(payload.get(key)))
    return list(dict.fromkeys(terms))


def _canonical_element(term: str) -> str | None:
    clean = str(term or "").strip()
    if not clean:
        return None
    for label, aliases in ELEMENT_ALIAS_RULES:
        if clean == label or clean in aliases:
            return label
    for label, aliases in ELEMENT_RULES:
        if clean == label or clean in aliases:
            return label
    return clean


def _represented_by_confirmed(term: str, confirmed_elements: list[str]) -> bool:
    canonical = _canonical_element(term)
    return bool(canonical and canonical in confirmed_elements)


def _profile_mode(payload: dict[str, Any], confirmed: list[str]) -> str:
    synopsis = str(payload.get("synopsis") or "").strip()
    if len(synopsis) < 40:
        return "baseline"
    explicit = _explicit_terms(payload)
    detail_score = len(synopsis) + (len(confirmed) * 25) + (len(explicit) * 20)
    return "detailed" if detail_score >= 80 else "baseline"


def analyze_work(payload: dict[str, Any]) -> dict[str, Any]:
    """Derive a cautious synopsis-level work profile for guide routing.

    This is intentionally deterministic and conservative: it extracts elements
    that are visible in title/genre/synopsis/declared tags, and marks synopsis
    findings as guide inputs rather than final story facts.
    """

    title = str(payload.get("title") or payload.get("workTitle") or "").strip()
    genre = str(payload.get("genre") or "").strip()
    synopsis = str(payload.get("synopsis") or "").strip()
    combined = "\n".join([title, genre, synopsis, " ".join(_explicit_terms(payload))])

    confirmed_elements = [label for label, terms in ELEMENT_RULES if _contains_any(combined, terms)]
    explicit_terms = _explicit_terms(payload)
    supporting_input_signals = [
        term for term in explicit_terms if _represented_by_confirmed(term, confirmed_elements)
    ]
    additional_input_signals = [
        term for term in explicit_terms if not _represented_by_confirmed(term, confirmed_elements)
    ]

    content_cautions = [label for label, terms in CAUTION_RULES if _contains_any(combined, terms)]
    if re.search(r"\bR15\b", combined, flags=re.IGNORECASE):
        content_cautions.append("연령 등급 표시")
    if re.search(r"\bR18\b", combined, flags=re.IGNORECASE):
        content_cautions.append("성인 등급 표시")
    content_cautions = list(dict.fromkeys(content_cautions))

    country_code = normalize_country_code(
        payload.get("targetCountry")
        or payload.get("target_country")
        or payload.get("targetMarket")
        or payload.get("target_market")
        or payload.get("country")
    )

    assumptions: list[str] = []
    if not synopsis:
        assumptions.append("시놉시스가 없어 제목/장르/명시 태그 중심으로만 읽었습니다.")
    if synopsis and len(synopsis) < 80:
        assumptions.append("시놉시스가 짧아 작품 요소는 확정 사실보다 점검 후보로 취급합니다.")
    if not content_cautions:
        assumptions.append("민감 소재는 입력에서 직접 확인되지 않았습니다. 본문 수위 확인은 별도 필요합니다.")

    mode = _profile_mode(payload, confirmed_elements)
    return {
        "mode": mode,
        "title": title or "입력 작품",
        "genre": genre,
        "synopsis": synopsis,
        "targetCountry": country_code,
        "targetCountryDisplay": COUNTRY_DISPLAY.get(country_code or "", str(country_code or "")),
        "confirmedElements": confirmed_elements,
        "supportingInputSignals": supporting_input_signals,
        "additionalInputSignals": additional_input_signals,
        "contentCautions": content_cautions,
        "inputCompleteness": {
            "hasTitle": bool(title),
            "hasGenre": bool(genre),
            "hasSynopsis": bool(synopsis),
            "confirmedElementCount": len(confirmed_elements),
            "contentCautionCount": len(content_cautions),
        },
        "assumptions": assumptions,
    }
