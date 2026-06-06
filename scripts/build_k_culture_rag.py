from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = Path.home() / "Downloads" / "K-Culture_desc.json"
DEFAULT_OUTPUT = ROOT / "data" / "annotation_rag" / "k_culture_annotation_cards.json"

PARTICLES_AND_ENDINGS = (
    "으로써",
    "으로서",
    "에서는",
    "에게는",
    "까지",
    "부터",
    "처럼",
    "에서",
    "에게",
    "으로",
    "라고",
    "이라",
    "라고",
    "이나",
    "이나마",
    "이나",
    "와",
    "과",
    "의",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "로",
    "도",
    "만",
)

STOP_TERMS = {
    "한국",
    "한국인",
    "한국의",
    "한국인들",
    "한국에서는",
    "사람",
    "사람들",
    "학생들",
    "관중들",
    "방법",
    "하나",
    "많은",
    "대부분",
    "사진",
    "속",
    "때",
    "중",
    "위해",
    "이기기",
    "돕는",
    "먹는다",
    "부르고",
    "춘다",
    "일컬어",
    "이라고",
    "라고",
    "이라",
    "말은",
    "같은",
    "뜻의",
    "먹어야",
    "좋아하",
    "줄여서",
    "것을",
    "끝난",
    "추가",
    "들으러",
    "경우",
    "문화",
    "의미",
    "일컫는",
    "부른다",
    "나뉜다",
    "하기도",
    "있다",
    "한다",
    "있는",
    "있어",
    "하는",
    "만든",
    "먹는",
    "주로",
    "가장",
    "많이",
    "함께",
    "등을",
    "등의",
    "표현",
    "대표적인",
    "다양한",
    "전통",
    "지역",
    "모양",
    "이름",
    "식사",
    "가족",
    "가격",
    "특정",
    "개인",
    "또는",
    "학교",
    "수업",
    "학원",
    "간다",
    "정규",
    "원기",
    "회복",
    "음식",
    "다함께",
    "춤을",
    "학생",
    "붙인",
    "하는",
    "주위",
    "차를",
    "사면",
    "바퀴",
    "차량",
    "구울",
    "기름",
    "차려",
    "가문",
    "조상",
    "따라",
    "걸을",
    "길을",
    "잃지",
    "지표",
    "전통적인",
    "우리나라",
    "우리나라에",
    "대한민국",
    "상징적인",
    "대중적인",
    "이용하여",
    "결합되어",
    "여겨진다",
    "유명하다",
    "다양하다",
    "어린이들",
    "저장하기",
    "기원하며",
    "따뜻하게",
    "표현으로",
    "조롱하거나",
    "무시하고",
    "주의해야",
    "프로그램",
    "동그랗게",
    "지하철역",
    "고등학교",
    "미끄러운",
    "전세계적",
    "아십니까",
    "간편하게",
    "오래도록",
    "동아시아",
    "만들어진",
    "자연스러운",
    "사랑받고",
    "할머니는",
}

WEAK_TERM_SUFFIXES = (
    "하는",
    "있는",
    "먹는",
    "받는",
    "높은",
    "많은",
    "위한",
    "통해",
    "따라",
    "때문",
    "등을",
    "등의",
    "적인",
    "하여",
    "되어",
    "진다",
    "하다",
    "한다",
    "였다",
    "었다",
    "았다",
    "으며",
    "면서",
    "에게",
    "에는",
    "에서",
    "으로",
    "라고",
    "처럼",
    "하게",
    "러운",
    "스러운",
    "어진",
    "받고",
    "받는",
    "이라",
)

CULTURAL_TERM_HINTS = (
    "절",
    "제사",
    "차례",
    "명절",
    "추석",
    "설날",
    "초복",
    "중복",
    "말복",
    "삼복",
    "삼계탕",
    "김치",
    "소주",
    "막걸리",
    "한복",
    "온돌",
    "찜질방",
    "학원",
    "대치동",
    "야구장",
    "응원가",
    "응원단",
    "치어리더",
    "떼창",
    "얼죽아",
    "인생네컷",
    "금수저",
    "수저",
    "붉은악마",
    "해녀",
    "장독",
    "DMZ",
)

ALLOWED_PHRASE_KEYWORDS = (
    "기원식",
    "삼겹살",
    "파티",
    "수능맘",
    "인스타",
    "감성",
    "숙취",
    "금수저",
    "프리미엄",
    "성당",
    "윤동주",
    "이육사",
    "붉은",
    "악마",
    "해녀",
    "장독",
    "베를린",
    "장벽",
    "군고구마",
    "고구마",
    "종친회",
    "노래방",
    "깻잎",
    "논쟁",
    "서울대학교",
    "선물세트",
    "모범택시",
    "임산부",
    "배려석",
    "인생네컷",
    "안전",
    "명절",
    "감사예배",
    "해장",
    "찜질방",
    "탑골공원",
    "프로포즈",
    "오징어",
    "게임",
)

BANNED_CONTEXT_PATTERNS = (
    re.compile(r"도요[우노]*\s*우시노\s*히"),
)

CATEGORY_TAGS = {
    "Food and Drinks": ["food", "drink", "daily_life"],
    "Traditions and Rituals": ["tradition", "ritual", "custom"],
    "Knowledge and Stories": ["knowledge", "story", "daily_life"],
    "Tools and Objects": ["object", "material_culture"],
    "Music, Sports and Arts": ["music", "sports", "arts", "fan_culture"],
    "Language": ["language", "slang", "expression"],
    "Architecture": ["architecture", "place"],
    "Economy and Work": ["economy", "workplace"],
    "Politics and Government": ["politics", "government"],
    "Environment and Geography": ["environment", "geography"],
    "Greater Community": ["community", "society"],
    "Values": ["values", "social_norm"],
    "Techniques and Skills": ["technique", "skill"],
    "Education": ["education", "school"],
    "Entertainment": ["entertainment"],
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_context_text(value: Any) -> str:
    text = clean_text(value)
    for pattern in BANNED_CONTEXT_PATTERNS:
        text = pattern.sub("타문화의 유사한 여름 보양식 풍습", text)
    return text


def slug(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-zA-Z가-힣]+", "_", text).strip("_")
    return text[:64] or "unknown"


def strip_particle(value: str) -> str:
    text = value.strip(" .,!?:;\"'“”‘’()[]{}")
    for suffix in PARTICLES_AND_ENDINGS:
        stem = text[: -len(suffix)] if text.endswith(suffix) else ""
        if len(stem) >= 2:
            return stem
    return text


def quoted_korean_terms(text: str) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(r"['\"“”‘’]([^'\"“”‘’]{2,30})['\"“”‘’]", text):
        candidate = clean_text(match.group(1))
        if (
            re.search(r"[가-힣]", candidate)
            and len(candidate) <= 18
            and not re.search(r"[.?!…,:]", candidate)
            and "라고" not in candidate
            and "라며" not in candidate
        ):
            terms.append(candidate)
    return terms


def token_terms(text: str) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9·+-]{1,24}", text):
        raw = match.group(0)
        term = strip_particle(raw)
        if ":" in raw:
            continue
        if not re.search(r"[가-힣]", term):
            continue
        if re.search(r"[A-Za-z]", term) and not re.match(r"^(PC|SNS|MBTI|K)[A-Za-z가-힣0-9+-]*$", term):
            continue
        if len(term) < 2 or term in STOP_TERMS:
            continue
        if not is_strong_trigger_term(term):
            continue
        if term.endswith(("한다", "있다", "된다", "했다", "였다", "이다", "한다", "어야", "아야", "라서")):
            continue
        terms.append(term)
    return terms


def raw_token_terms(text: str, *, max_terms: int = 24) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9·+-]{1,24}", text):
        raw = match.group(0)
        term = strip_particle(raw)
        if ":" in raw:
            continue
        if not re.search(r"[가-힣]", term):
            continue
        if re.search(r"[A-Za-z]", term) and not re.match(r"^(PC|SNS|MBTI|K)[A-Za-z가-힣0-9+-]*$", term):
            continue
        if len(term) < 2:
            continue
        terms.append(term)
        if len(terms) >= max_terms:
            break
    return terms


def is_strong_trigger_term(term: str) -> bool:
    text = clean_text(term).strip(" .,!?:;\"'“”‘’()[]{}")
    compact = re.sub(r"\s+", "", text)
    if not compact or compact in STOP_TERMS:
        return False
    if len(compact) <= 2 and not re.search(r"[A-Za-z0-9]", compact):
        return False
    if compact.endswith(WEAK_TERM_SUFFIXES):
        return False
    if re.fullmatch(r"[가-힣]{2,3}", compact) and compact not in CULTURAL_TERM_HINTS:
        return False
    if " " in text:
        words = text.split()
        if len(words) > 4:
            return False
        if not any(keyword in compact for keyword in ALLOWED_PHRASE_KEYWORDS):
            return False
        if any(word.endswith(WEAK_TERM_SUFFIXES) for word in words):
            return False
        if any(word in STOP_TERMS for word in words):
            return False
        if re.search(r"(주세요|합니다|했다|됐다|된다|하네|하나|같다|모이자|찍자|오는가|웃으면서|고개를|마음속으로)", text):
            return False
        # Keep compact cultural noun phrases such as "인스타 감성", "안전 기원식",
        # "도요우노 우시노 히"; drop sentence fragments.
        if len(compact) > 14 and not re.search(r"(식|탕|장|절|제|굿|놀이|감성|기원식|파티|음료|해녀|성당|도르트문트)$", compact):
            return False
    return True


def is_weak_term(term: str) -> bool:
    text = clean_text(term)
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return False
    if is_strong_trigger_term(text):
        return False
    if len(compact) > 12:
        return False
    return True


def semantic_keyword_terms(row: dict[str, Any], trigger_terms: list[str], *, max_terms: int = 8) -> list[str]:
    description = clean_text(row.get("Description"))
    category = clean_text(row.get("Category"))
    candidates: list[str] = []
    for term in raw_token_terms(description, max_terms=32):
        if term in trigger_terms:
            continue
        if term in STOP_TERMS:
            continue
        if len(term) <= 2:
            continue
        if term.endswith(WEAK_TERM_SUFFIXES):
            continue
        candidates.append(term)
    if category:
        category_hint = {
            "Food and Drinks": "한국 음식 문화",
            "Traditions and Rituals": "한국 의례와 전통",
            "Knowledge and Stories": "한국 생활 문화",
            "Education": "한국 교육 문화",
            "Language": "한국어 표현 문화",
            "Music, Sports and Arts": "한국 대중문화와 여가",
            "Architecture": "한국 건축과 공간 문화",
            "Economy and Work": "한국 경제와 직장 문화",
            "Values": "한국 가치관과 사회 규범",
        }.get(category)
        if category_hint:
            candidates.append(category_hint)
    return ordered_unique(candidates, limit=max_terms)


def weak_keyword_terms(row: dict[str, Any], trigger_terms: list[str], semantic_keywords: list[str], *, max_terms: int = 8) -> list[str]:
    description = clean_text(row.get("Description"))
    candidates = [
        term
        for term in raw_token_terms(description, max_terms=40)
        if term not in trigger_terms and term not in semantic_keywords and is_weak_term(term)
    ]
    return ordered_unique(candidates, limit=max_terms)


def ordered_unique(values: list[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def extract_anchor_terms(row: dict[str, Any], *, max_terms: int = 10) -> list[str]:
    description = clean_text(row.get("Description"))
    candidates: list[str] = []
    candidates.extend(term for term in quoted_korean_terms(description) if is_strong_trigger_term(term))
    candidates.extend(token_terms(description))

    # Triggers should be compact source-side cultural terms from Description.
    # ScenarioBody remains semantic context only; dialogue/comparison phrases in
    # scenarios can include foreign culture examples or incidental dialogue and
    # must not become exact-match boost triggers.
    return ordered_unique(candidates, limit=max_terms)


def mcqa_text(mcqa: Any) -> str:
    if not isinstance(mcqa, dict):
        return ""
    parts = [
        clean_text(mcqa.get("Question")),
        clean_text(mcqa.get("Choices")),
        clean_text(mcqa.get("Explanation")),
    ]
    return "\n".join(part for part in parts if part)


def mcqa_explanation(mcqa: Any) -> str:
    if not isinstance(mcqa, dict):
        return ""
    return clean_text(mcqa.get("Explanation"))


def annotation_summary_for(category: str, keyword: str, description: str) -> str:
    category_hint = {
        "Food and Drinks": "음식 자체보다 언제, 왜 먹는지에 담긴 계절감·보양·사회적 의미를 보충한다.",
        "Traditions and Rituals": "행동의 목적이 기원, 예절, 의례 중 무엇인지 짧게 밝혀 오해를 줄인다.",
        "Education": "한국식 사교육·입시 경쟁·학원 문화가 장면 이해에 영향을 줄 때만 설명한다.",
        "Language": "직역하면 의미가 흐려지는 줄임말·유행어·사회적 뉘앙스를 자연스럽게 풀어준다.",
        "Music, Sports and Arts": "관객 참여, 팬 문화, 공연/응원 방식처럼 장면 분위기를 만드는 관습을 설명한다.",
        "Architecture": "공간 구조나 장소의 사회적 쓰임이 독자에게 낯설 때 간단히 보충한다.",
        "Economy and Work": "소비·직장·경제 관행의 사회적 맥락이 대사 의미를 바꿀 때 설명한다.",
        "Knowledge and Stories": "한국 생활상이나 배경지식이 장면의 전제를 만들 때 필요한 만큼만 보충한다.",
        "Tools and Objects": "물건의 용도나 상징성이 장면 이해에 중요할 때 기능 중심으로 설명한다.",
        "Greater Community": "공동체 관습이나 집단 행동의 의미가 드러날 때 사회적 맥락을 보충한다.",
        "Politics and Government": "제도·공공기관·사회 규칙이 독자에게 낯설 때 장면 이해에 필요한 수준으로 설명한다.",
        "Environment and Geography": "지역·계절·지리 조건이 행동의 이유를 설명할 때 자연스럽게 보충한다.",
        "Techniques and Skills": "기술이나 숙련 방식이 문화적 배경을 갖는 경우 기능과 맥락을 함께 설명한다.",
        "Entertainment": "놀이·콘텐츠 소비 방식이 장면 분위기나 인물 관계를 만들 때 설명한다.",
        "Values": "체면, 정, 위계, 가족관 같은 가치관이 인물 판단에 영향을 줄 때만 보충한다.",
    }.get(category)
    if category_hint:
        return f"{keyword} 관련 한국 문화 맥락이다. {category_hint}"
    return f"{keyword} 관련 한국 문화 맥락이다. {description}"


def translation_guide_for(category: str, keyword: str, description: str) -> str:
    if category == "Food and Drinks":
        return "이 항목은 음식명만 옮기지 말고, 문맥상 필요하면 먹는 시기나 보양/기념 의미를 함께 풀어준다."
    if category == "Traditions and Rituals":
        return "이 항목은 행위 자체보다 기원·예절·의례의 목적이 중요하므로, 직역으로 이상해지면 짧은 설명을 덧붙인다."
    if category == "Education":
        return "이 항목은 단순한 학교/수업이 아니라 한국식 학업 경쟁이나 사교육 맥락일 수 있으므로, 인물의 부담과 일정 맥락을 살린다."
    if category == "Language":
        return "이 항목은 말장난·줄임말·유행어일 수 있으므로, 원어를 보존할지 의미를 풀지 대상 독자의 이해도를 기준으로 결정한다."
    if category == "Music, Sports and Arts":
        return "이 항목은 문화 행사나 팬 참여 방식이 핵심이면 분위기와 참여 강도를 자연스러운 대상어 표현으로 옮긴다."
    if category == "Architecture":
        return "이 항목은 장소명보다 공간의 기능과 생활 방식이 중요할 수 있으므로, 장면 이해에 필요한 기능 설명을 우선한다."
    if category == "Economy and Work":
        return "이 항목은 한국의 소비·노동·조직 문화 맥락이 드러나면 대상 문화의 유사 제도로 무리하게 치환하지 않는다."
    if category == "Values":
        return "이 항목은 한국식 관계·예절·가치 판단이 핵심이면 인물 감정과 사회적 압박이 보이도록 번역한다."
    if category == "Knowledge and Stories":
        return "이 항목은 배경지식 자체를 길게 설명하기보다, 인물이 왜 그렇게 행동하거나 말하는지 이해되는 정도로만 풀어준다."
    if category == "Tools and Objects":
        return "이 항목은 물건 이름보다 사용 목적과 장면 속 기능이 중요하면 기능 중심으로 옮긴다."
    if category == "Greater Community":
        return "이 항목은 공동체 관습이나 집단 분위기가 핵심이면 개인 행동으로 축소하지 말고 사회적 맥락을 살린다."
    if category == "Politics and Government":
        return "이 항목은 제도명을 무리하게 현지 제도로 치환하지 말고, 필요한 경우 한국 제도임을 짧게 드러낸다."
    if category == "Environment and Geography":
        return "이 항목은 지역·계절·지리 조건이 행동 이유와 연결되면 그 인과관계가 보이도록 옮긴다."
    if category == "Techniques and Skills":
        return "이 항목은 기술명보다 수행 방식과 문화적 쓰임이 중요하면 그 기능을 자연스럽게 풀어준다."
    if category == "Entertainment":
        return "이 항목은 놀이·콘텐츠 소비 방식이 핵심이면 대상 독자가 비슷한 분위기를 느낄 수 있게 풀어준다."
    return f"이 항목은 한국 문화 요소로 보고, '{description}'의 핵심 의미가 대상 독자에게 자연스럽게 전달되도록 보존·풀어쓰기·짧은 설명 중 하나를 선택한다."


def make_annotation_card(row: dict[str, Any]) -> dict[str, Any]:
    description_id = int(row.get("DescriptionID") or 0)
    description = clean_context_text(row.get("Description"))
    category = clean_text(row.get("Category")) or "K-Culture"
    trigger_terms = extract_anchor_terms(row)
    semantic_fallback = semantic_keyword_terms(row, trigger_terms, max_terms=1)
    keyword = " / ".join(trigger_terms[:3]) if trigger_terms else (semantic_fallback[0] if semantic_fallback else category)
    annotation_summary = annotation_summary_for(category, keyword, description)
    translation_guide = translation_guide_for(category, keyword, description)
    context_lines = [
        f"키워드: {keyword}",
        f"핵심 요약: {description}",
        f"주석 설명: {annotation_summary}",
        f"번역 가이드: {translation_guide}",
    ]

    return {
        "id": f"KCULTURE_{description_id:04d}",
        "embedding_text": description,
        "context_text": "\n".join(line for line in context_lines if line.strip()),
        "trigger_terms": trigger_terms,
        "metadata": {
            "culture_id": f"KCULTURE_{description_id:04d}",
            "category": category,
            "culture_type_ko": "한국 문화 주석 후보",
            "keyword_ko": keyword,
        },
    }


def make_k_culture_card(row: dict[str, Any], locale: str | None = None) -> dict[str, Any]:
    """Backward-compatible alias for older tests/imports.

    K-Culture rows are now annotation cards, not locale-specific translation
    references. The optional locale parameter is intentionally ignored.
    """
    return make_annotation_card(row)


def load_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list: {path}")
    return [row for row in data if isinstance(row, dict)]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build_annotation_dataset(input_path: Path, output_path: Path) -> dict[str, Any]:
    k_rows = load_json_list(input_path)
    cards = [make_annotation_card(row) for row in k_rows]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report: dict[str, Any] = {
        "source": str(input_path),
        "k_culture_rows": len(k_rows),
        "annotation_cards": len(cards),
        "output": display_path(output_path),
        "category_counts": dict(Counter(clean_text(row.get("Category")) for row in k_rows)),
        "card_shape": "annotation_rag",
        "note": "K-Culture cards are source-side cultural annotation candidates, not translation-expression references.",
    }
    report_path = output_path.parent / "_k_culture_annotation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def build_augmented_datasets(input_path: Path, output_dir: Path) -> dict[str, Any]:
    """Backward-compatible wrapper.

    Older code used this function to append K-Culture rows into locale RAG.
    The refactored behavior writes one annotation dataset instead.
    """
    return build_annotation_dataset(input_path, output_dir / "k_culture_annotation_cards.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build annotation RAG cards from K-Culture_desc.json.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    report = build_annotation_dataset(input_path, output_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
