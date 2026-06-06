from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "data" / "legacy_idiom_rag" / "seed" / "modern_korea_mvp_terms.json"


TERMS: list[tuple[str, str, str, str, list[str]]] = [
    # honorific / relationship
    ("형", "hyung", "honorific", "contextual_translate_or_preserve", ["honorific", "relationship", "male_speaker"]),
    ("형님", "hyungnim", "honorific", "contextual_translate_or_preserve", ["honorific", "respect", "relationship"]),
    ("오빠", "oppa", "honorific", "contextual_translate_or_preserve", ["honorific", "relationship", "female_speaker"]),
    ("누나", "noona", "honorific", "contextual_translate_or_preserve", ["honorific", "relationship", "male_speaker"]),
    ("언니", "eonni", "honorific", "contextual_translate_or_preserve", ["honorific", "relationship", "female_speaker"]),
    ("선배", "senior", "honorific", "contextual_translate", ["honorific", "school", "workplace", "hierarchy"]),
    ("선배님", "senior", "honorific", "contextual_translate", ["honorific", "respect", "hierarchy"]),
    ("후배", "junior", "honorific", "contextual_translate", ["honorific", "school", "workplace", "hierarchy"]),
    ("아저씨", "ajeossi", "honorific", "contextual_translate_or_preserve", ["honorific", "address_term"]),
    ("아줌마", "ajumma", "honorific", "contextual_translate_or_preserve", ["honorific", "address_term"]),
    ("아주머니", "ma'am", "honorific", "contextual_translate", ["honorific", "address_term"]),
    ("사장님", "boss", "honorific", "contextual_translate", ["honorific", "workplace", "service"]),
    ("팀장님", "team lead", "honorific", "contextual_translate", ["workplace", "title", "hierarchy"]),
    ("대리님", "assistant manager", "honorific", "contextual_translate", ["workplace", "title", "hierarchy"]),
    ("과장님", "manager", "honorific", "contextual_translate", ["workplace", "title", "hierarchy"]),
    ("부장님", "department head", "honorific", "contextual_translate", ["workplace", "title", "hierarchy"]),
    ("대표님", "CEO", "honorific", "contextual_translate", ["workplace", "title", "hierarchy"]),
    ("선생님", "teacher", "honorific", "contextual_translate", ["honorific", "school", "respect"]),
    ("교수님", "professor", "honorific", "contextual_translate", ["honorific", "school", "respect"]),
    ("작가님", "author", "honorific", "contextual_translate", ["honorific", "creator", "respect"]),
    ("기사님", "driver", "honorific", "contextual_translate", ["honorific", "service", "daily_life"]),
    ("남친", "boyfriend", "relationship", "contextual_translate", ["relationship", "slang", "romance"]),
    ("여친", "girlfriend", "relationship", "contextual_translate", ["relationship", "slang", "romance"]),
    ("썸남", "a guy she/he is seeing", "relationship", "contextual_translate", ["relationship", "dating", "slang"]),
    ("썸녀", "a girl she/he is seeing", "relationship", "contextual_translate", ["relationship", "dating", "slang"]),
    ("전남친", "ex-boyfriend", "relationship", "contextual_translate", ["relationship", "dating"]),
    ("전여친", "ex-girlfriend", "relationship", "contextual_translate", ["relationship", "dating"]),
    ("동창", "schoolmate", "relationship", "contextual_translate", ["relationship", "school"]),
    ("절친", "best friend", "relationship", "contextual_translate", ["relationship", "slang"]),
    ("알바생", "part-time worker", "relationship", "contextual_translate", ["work", "part_time", "daily_life"]),
    # food / drink
    ("설렁탕", "seolleongtang", "food", "transliterate_with_gloss", ["food", "korean_culture"]),
    ("국밥", "gukbap", "food", "transliterate_with_gloss", ["food", "daily_life"]),
    ("해장국", "haejangguk", "food", "transliterate_with_gloss", ["food", "drinking_culture"]),
    ("김치찌개", "kimchi jjigae", "food", "transliterate_with_gloss", ["food", "korean_culture"]),
    ("된장찌개", "doenjang jjigae", "food", "transliterate_with_gloss", ["food", "korean_culture"]),
    ("떡볶이", "tteokbokki", "food", "preserve_transliteration", ["food", "street_food"]),
    ("순대", "sundae", "food", "transliterate_with_gloss", ["food", "street_food"]),
    ("삼겹살", "samgyeopsal", "food", "transliterate_with_gloss", ["food", "drinking_culture"]),
    ("치맥", "chimaek", "food", "transliterate_with_gloss", ["food", "drinking_culture", "slang"]),
    ("막걸리", "makgeolli", "drink", "preserve_transliteration", ["drink", "korean_culture"]),
    ("소주", "soju", "drink", "preserve_transliteration", ["drink", "drinking_culture"]),
    ("라면", "ramyeon", "food", "contextual_translate_or_preserve", ["food", "daily_life"]),
    ("컵라면", "cup ramyeon", "food", "contextual_translate_or_preserve", ["food", "convenience_store"]),
    ("편의점 도시락", "convenience-store lunchbox", "food", "contextual_translate", ["food", "convenience_store"]),
    ("분식", "bunsik", "food", "transliterate_with_gloss", ["food", "street_food"]),
    ("족발", "jokbal", "food", "transliterate_with_gloss", ["food", "delivery_food"]),
    ("보쌈", "bossam", "food", "transliterate_with_gloss", ["food", "delivery_food"]),
    ("안주", "anju", "food", "transliterate_with_gloss", ["food", "drinking_culture"]),
    ("해장", "hangover recovery", "food", "contextual_translate", ["drinking_culture", "daily_life"]),
    # venues / places / housing
    ("포장마차", "pojangmacha", "venue", "transliterate_with_gloss", ["venue", "street_food", "drinking_culture"]),
    ("포차", "pocha", "venue", "transliterate_with_gloss", ["venue", "street_food", "drinking_culture"]),
    ("노래방", "noraebang", "venue", "transliterate_with_gloss", ["venue", "entertainment"]),
    ("PC방", "PC bang", "venue", "transliterate_with_gloss", ["venue", "gaming", "youth_culture"]),
    ("피시방", "PC bang", "venue", "transliterate_with_gloss", ["venue", "gaming", "youth_culture"]),
    ("학원", "hagwon", "venue", "transliterate_with_gloss", ["school", "education"]),
    ("고시원", "gosiwon", "housing", "transliterate_with_gloss", ["housing", "daily_life", "economic_context"]),
    ("고시텔", "gositel", "housing", "transliterate_with_gloss", ["housing", "daily_life"]),
    ("원룸", "studio apartment", "housing", "contextual_translate", ["housing", "daily_life"]),
    ("반지하", "semi-basement apartment", "housing", "contextual_translate", ["housing", "economic_context"]),
    ("편의점", "convenience store", "venue", "contextual_translate", ["venue", "daily_life"]),
    ("분식집", "bunsik restaurant", "venue", "transliterate_with_gloss", ["venue", "food", "daily_life"]),
    ("찜질방", "jjimjilbang", "venue", "transliterate_with_gloss", ["venue", "bathhouse", "daily_life"]),
    ("모텔", "motel", "venue", "contextual_translate", ["venue", "daily_life"]),
    ("술집", "bar", "venue", "contextual_translate", ["venue", "drinking_culture"]),
    ("독서실", "study room", "venue", "contextual_translate", ["venue", "education"]),
    ("스터디카페", "study cafe", "venue", "contextual_translate", ["venue", "education"]),
    ("지하철역", "subway station", "place", "contextual_translate", ["transportation", "daily_life"]),
    ("버스정류장", "bus stop", "place", "contextual_translate", ["transportation", "daily_life"]),
    ("강남", "Gangnam", "place", "preserve_name_with_context", ["place", "seoul", "class_context"]),
    ("홍대", "Hongdae", "place", "preserve_name_with_context", ["place", "seoul", "youth_culture"]),
    ("이태원", "Itaewon", "place", "preserve_name_with_context", ["place", "seoul", "urban_life"]),
    ("대학로", "Daehangno", "place", "preserve_name_with_context", ["place", "seoul", "culture"]),
    ("판교", "Pangyo", "place", "preserve_name_with_context", ["place", "tech", "workplace"]),
    # school / work / social
    ("야근", "overtime work", "school_work", "contextual_translate", ["workplace", "daily_life"]),
    ("회식", "company dinner", "school_work", "contextual_translate", ["workplace", "drinking_culture"]),
    ("출근", "go to work", "school_work", "contextual_translate", ["workplace", "daily_life"]),
    ("퇴근", "get off work", "school_work", "contextual_translate", ["workplace", "daily_life"]),
    ("지각", "being late", "school_work", "contextual_translate", ["school", "workplace"]),
    ("야자", "night self-study", "school_work", "contextual_translate", ["school", "education"]),
    ("수능", "CSAT", "school_work", "preserve_name_with_context", ["school", "exam", "korean_culture"]),
    ("내신", "school grades", "school_work", "contextual_translate", ["school", "education"]),
    ("과외", "private tutoring", "school_work", "contextual_translate", ["school", "education"]),
    ("알바", "part-time job", "school_work", "contextual_translate", ["work", "slang", "daily_life"]),
    ("정규직", "full-time employee", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("비정규직", "non-regular worker", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("계약직", "contract worker", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("인턴", "intern", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("신입", "new hire", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("경력직", "experienced hire", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("퇴사", "resignation", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("입사", "joining a company", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("면접", "job interview", "school_work", "contextual_translate", ["workplace", "employment"]),
    ("자기소개서", "personal statement", "school_work", "contextual_translate", ["workplace", "school"]),
    ("월급", "monthly salary", "school_work", "contextual_translate", ["workplace", "money"]),
    ("연봉", "annual salary", "school_work", "contextual_translate", ["workplace", "money"]),
    ("갑질", "abuse of power", "school_work", "contextual_translate", ["workplace", "social_issue"]),
    ("꼰대", "kkondae", "school_work", "contextual_translate_or_preserve", ["workplace", "social_issue", "slang"]),
    ("눈치", "nunchi", "social_expression", "contextual_translate_or_preserve", ["social_expression", "korean_culture"]),
    # digital / dating / social slang
    ("카톡", "KakaoTalk message", "digital", "contextual_translate", ["digital", "daily_life"]),
    ("단톡방", "group chat", "digital", "contextual_translate", ["digital", "social"]),
    ("읽씹", "leaving someone on read", "digital", "contextual_translate", ["digital", "slang"]),
    ("안읽씹", "leaving a message unread", "digital", "contextual_translate", ["digital", "slang"]),
    ("인스타", "Instagram", "digital", "contextual_translate", ["digital", "social_media"]),
    ("셀카", "selfie", "digital", "contextual_translate", ["digital", "daily_life"]),
    ("악플", "malicious comment", "digital", "contextual_translate", ["digital", "social_issue"]),
    ("현질", "spending real money in-game", "digital", "contextual_translate", ["digital", "gaming", "slang"]),
    ("과금", "in-app purchase", "digital", "contextual_translate", ["digital", "gaming"]),
    ("배달앱", "delivery app", "digital", "contextual_translate", ["digital", "daily_life"]),
    ("택배", "parcel delivery", "daily_life", "contextual_translate", ["daily_life"]),
    ("중고거래", "secondhand transaction", "daily_life", "contextual_translate", ["daily_life", "digital"]),
    ("썸", "the talking stage", "social_expression", "contextual_translate", ["dating", "slang"]),
    ("소개팅", "blind date", "social_expression", "contextual_translate", ["dating", "daily_life"]),
    ("밀당", "push-and-pull flirting", "social_expression", "contextual_translate", ["dating", "slang"]),
    ("철벽", "putting up a wall", "social_expression", "contextual_translate", ["dating", "slang"]),
]


ALIASES = {
    "PC방": ["피시방"],
    "포장마차": ["포차"],
    "고시원": ["고시텔"],
    "형": ["형님"],
    "선배": ["선배님"],
    "아줌마": ["아주머니"],
}


WARNINGS = {
    "honorific": "한국어 호칭은 친족, 친밀도, 위계, 화자 성별을 함께 드러내므로 영어 친족어로 항상 고정하지 않는다.",
    "relationship": "관계어와 연애 속어는 장면의 친밀도와 말투를 확인해 과하게 설명하지 않는다.",
    "food": "음식명을 일반 음식명으로만 대체하면 한국적 생활감이 약해질 수 있다.",
    "drink": "한국 음주문화와 연결된 표현은 단순한 주류명 대체로 뉘앙스가 약해질 수 있다.",
    "venue": "한국식 공간문화가 중요한 경우 단순 시설명으로 일반화하지 않는다.",
    "housing": "주거 형태가 계층성이나 생활 조건을 드러낼 수 있으므로 단순 apartment/dormitory로 일반화하지 않는다.",
    "place": "지명이 계층, 문화권, 도시 이미지를 암시하는 경우 필요하면 짧은 맥락을 보존한다.",
    "school_work": "학교/회사 제도 표현은 대상 문화권의 직역어와 완전히 대응하지 않을 수 있다.",
    "digital": "한국 플랫폼/인터넷 속어는 독자가 이해할 수 있게 자연스럽게 풀되 과도한 설명은 피한다.",
    "daily_life": "생활어는 자연스러움과 한국적 맥락 보존 사이의 균형을 확인한다.",
    "social_expression": "사회적 눈치, 연애, 관계 표현은 직역보다 관계 역학을 살리는 번역이 중요하다.",
}


REASONS = {
    "honorific": "현대물에서 인물 관계와 거리감을 빠르게 드러내는 핵심 호칭이다.",
    "relationship": "현대물의 관계성과 감정선을 드러내는 반복 표현이다.",
    "food": "현대 한국의 일상성과 문화 배경을 드러내는 음식명이다.",
    "drink": "술자리, 회식, 친밀도 변화 장면에서 한국적 분위기를 만든다.",
    "venue": "현대 한국 생활공간과 장면 분위기를 설명하는 장소어다.",
    "housing": "인물의 경제상태와 생활 조건을 드러낼 수 있는 주거 표현이다.",
    "place": "서울/수도권의 도시 이미지, 계층성, 청년문화를 암시할 수 있는 지명이다.",
    "school_work": "학교·회사 제도와 한국식 위계를 드러내는 현대물 핵심 표현이다.",
    "digital": "메신저, 게임, 플랫폼 사용이 많은 현대물 장면에서 자주 등장하는 생활어다.",
    "daily_life": "한국 현대 생활의 구체성을 보존하는 데 도움이 되는 표현이다.",
    "social_expression": "관계의 미묘한 거리감과 현대 한국식 사회적 감각을 드러낸다.",
}


def slug(value: str) -> str:
    text = re.sub(r"\s+", "", value.lower())
    text = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", text).strip("_")
    return text[:48] or "unknown"


def build_rows() -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for source, target, category, strategy, tags in TERMS:
        if source in seen:
            continue
        seen.add(source)
        rows.append(
            {
                "id": f"seed_modern_ko_{category}_{slug(source)}",
                "locale": "ko_en_us",
                "category": category,
                "source_expression": source,
                "source_aliases": ALIASES.get(source, []),
                "target_expression": target,
                "target_explanation": "",
                "strategy": strategy,
                "reason": REASONS.get(category, "현대물 번역에서 반복적으로 등장할 수 있는 한국어 표현이다."),
                "example_source": "",
                "example_translation": "",
                "warnings": [WARNINGS.get(category, "문맥에 따라 번역 전략을 검토한다.")],
                "tags": tags,
                "confidence": 0.55,
                "source_type": "manual_seed",
                "review_status": "needs_review",
                "quality_flags": ["needs_human_review", "mvp_seed"],
                "legacy": {},
            }
        )
    return rows


def main() -> None:
    rows = build_rows()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)} rows={len(rows)}")


if __name__ == "__main__":
    main()
