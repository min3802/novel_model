from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any


RAW_DIR = Path("data/localization_guide/platform_observation/raw")
OUT_DIR = Path("data/localization_guide/platform_observation/processed")

EXCLUDED_CONTEXT_PLATFORMS = {"WebNovel"}
EXCLUSION_REASON = "global_market_not_matched_to_regulatory_context"
EXCLUDED_CONTEXT_SOURCES = {
    ("Royal Road", "trending"): "redundant_signal_type_for_context_balance_keep_weekly_popular",
}

MARKET_SLUGS = {
    "China": "china",
    "US": "english",
    "Japan": "japan",
    "Thailand": "thailand",
}

MARKET_DISPLAY_KO = {
    "China": "중국",
    "US": "영어권/US",
    "Japan": "일본",
    "Thailand": "태국",
}

LABEL_KO: dict[str, str] = {
    # English / common
    "Fantasy": "판타지",
    "fantasy": "판타지",
    "Action": "액션",
    "ACTION": "액션",
    "Adventure": "모험",
    "ADVENTURE": "모험",
    "Romance": "로맨스",
    "ROMANCE": "로맨스",
    "Romance Fantasy": "로맨스 판타지",
    "Comedy": "코미디",
    "COMEDY": "코미디",
    "Drama": "드라마",
    "Mystery": "미스터리",
    "LitRPG": "LitRPG",
    "Progression": "성장형 판타지",
    "Portal Fantasy / Isekai": "포털 판타지/이세계",
    "Isekai": "이세계",
    "Reincarnation": "전생",
    "reincarnation": "전생",
    "transmigration": "빙의/전이",
    "TRANSMIGRATION": "빙의/전이",
    "System": "시스템",
    "SYSTEM": "시스템",
    "OVERPOWERED": "먼치킨/강자",
    "WEAKTOSTRONG": "약자에서 강자로",
    "Magic": "마법",
    "MAGIC": "마법",
    "Harem": "하렘",
    "HAREM": "하렘",
    "Smut": "성인/선정 요소",
    "SMUT": "성인/선정 요소",
    "R18": "R18",
    "Adult": "성인",
    "Ecchi": "에치/선정 요소",
    "Male Lead": "남성 주인공",
    "Female Lead": "여성 주인공",
    "Strong Lead": "강한 주인공",
    "Slice of Life": "일상",
    "SLICEOFLIFE": "일상",
    "Martial Arts": "무술/무협",
    "Cultivation": "수련/선협",
    "CULTIVATION": "수련/선협",
    "Academy": "학원",
    "ACADEMY": "학원",
    "WAIT_UNTIL_FREE": "기다리면 무료",
    "ON_GOING": "연재중",
    "ONGOING": "연재중",
    "Original": "오리지널",
    # Japanese
    "R15": "R15",
    "異世界転生": "이세계 전생",
    "異世界転移": "이세계 전이",
    "異世界〔恋愛〕": "이세계 로맨스",
    "ハイファンタジー〔ファンタジー〕": "하이 판타지",
    "異世界ファンタジー": "이세계 판타지",
    "恋愛": "연애/로맨스",
    "ラブコメ": "러브 코미디",
    "男主人公": "남성 주인공",
    "女主人公": "여성 주인공",
    "残酷な描写あり": "잔혹 묘사 있음",
    "ハッピーエンド": "해피엔딩",
    "ざまぁ": "사이다/복수",
    "魔法": "마법",
    "チート": "치트",
    "ほのぼの": "훈훈함/잔잔함",
    "シリアス": "시리어스",
    "日常": "일상",
    "西洋": "서양풍",
    "学園": "학원",
    "小説": "소설",
    "連載中": "연재중",
    "長編": "장편",
    # Chinese
    "原创": "오리지널",
    "爱情": "사랑/로맨스",
    "言情": "로맨스",
    "女主视角": "여성 주인공 시점",
    "主受视角": "수 시점/BL",
    "纯爱": "BL/순애",
    "近代现代": "근현대",
    "架空历史": "가상 역사",
    "甜文": "달달한 이야기",
    "爽文": "사이다/쾌감형",
    "情有独钟": "일편단심",
    "轻松": "가벼운 톤",
    "热血": "열혈",
    "天之骄子": "엘리트/천재형 인물",
    "穿越时空": "시공간 이동",
    "强强": "강자 대 강자",
    "系统": "시스템",
    "玄幻奇幻": "현환/판타지",
    "东方玄幻": "동양 판타지",
    "传统玄幻": "전통 판타지",
    # Thai
    "Love Novel": "로맨스 소설",
    "โรแมนติก": "로맨틱",
    "นิยายรัก": "로맨스 소설",
    "มหาวิทยาลัย": "대학",
    "วิศวะ": "공대",
    "รักวัยรุ่น": "청춘 로맨스",
    "โรมานซ์": "로맨스",
    "18+": "18+",
    "แอบรัก": "짝사랑",
    "ดรามา": "드라마",
    "Feel good": "필굿",
    "น่ารัก": "귀여움",
    "ตลก": "코미디",
    "วาย": "BL/보이즈러브",
    "นิยายรักจีนโบราณ": "중국 고전풍 로맨스",
}

LABEL_KO.update(
    {
        # English / platform genre tags
        "Supernatural": "초자연",
        "High Fantasy": "하이 판타지",
        "COMPLETED": "완결",
        "completed": "완결",
        "Mature": "성인/성숙한 독자",
        "Girls Love": "GL/걸즈러브",
        "romance": "로맨스",
        "ongoing": "연재중",
        "magic": "마법",
        "School Life": "학원/학교생활",
        "GameLit": "게임릿",
        "Strategy": "전략",
        "Anti-Hero Lead": "안티히어로 주인공",
        "Sci-fi": "SF",
        "Gender Bender": "성별 전환",
        "Kingdom Building": "국가/영지 건설",
        "War and Military": "전쟁/군사",
        "adventure": "모험",
        "Action Fantasy": "액션 판타지",
        "Romance Subplot": "로맨스 서브플롯",
        "Secret Identity": "비밀 정체",
        "texttospeech": "TTS 지원",
        "Modern Knowledge": "현대 지식",
        "Local Protagonist": "현지인 주인공",
        "Attractive Lead": "매력적인 주인공",
        "Psychological": "심리",
        "Multiple Lead Characters": "다중 주인공",
        "love": "사랑/로맨스",
        "action": "액션",
        "Post Apocalyptic": "포스트 아포칼립스",
        "Apocalypse": "아포칼립스",
        "Urban Fantasy": "어반 판타지",
        "BL": "BL/보이즈러브",
        "Survival": "생존",
        "Crafting": "제작/크래프팅",
        "Ruling Class": "지배 계층/귀족",
        "Dungeon Crawler": "던전 크롤러",
        "villainess": "악역영애",
        "Mythos": "신화",
        "System Invasion": "시스템 침공",
        "femaleprotagonist": "여성 주인공",
        "isekai": "이세계",
        "Non-Human Lead": "비인간 주인공",
        "Dystopia": "디스토피아",
        "slowburn": "슬로우번",
        "Grimdark": "그림다크",
        "Magitech": "마법공학",
        "Wuxia": "무협",
        "darkfantasy": "다크 판타지",
        "fantasyadventure": "판타지 모험",
        "Low Fantasy": "로우 판타지",
        "royalty": "왕족/왕실",
        "comedy": "코미디",
        "Technologically Engineered": "기술 개조/공학",
        "Time Travel": "시간여행",
        "Multiple Lovers": "다자 관계",
        "Fan Fiction": "팬픽션",
        "Soft Sci-fi": "소프트 SF",
        "First Contact": "퍼스트 콘택트",
        # Japanese tags
        "異世界": "이세계",
        "成り上がり": "신분상승/성공담",
        "ダンジョン": "던전",
        "婚約破棄": "혼약 파기",
        "主人公最強": "최강 주인공",
        "ローファンタジー〔ファンタジー〕": "로우 판타지",
        "ギャグ": "개그",
        "冒険": "모험",
        "溺愛": "집착적 사랑/溺愛",
        "内政": "내정",
        "ファンタジー": "판타지",
        "ハーレム": "하렘",
        "現代ファンタジー": "현대 판타지",
        "スローライフ": "슬로우 라이프",
        "ヤンデレ": "얀데레",
        "現代": "현대",
        "書籍化": "서적화",
        "中世": "중세",
        "短編": "단편",
        "悪役令嬢": "악역영애",
        "カクヨムオンリー": "카쿠요무 온리",
        "配信": "방송/스트리밍",
        "コメディ": "코미디",
        "ＥＳＮ大賞１０": "ESN 대상 10",
        "追放": "추방",
        "勘違い": "착각",
        "乙女ゲーム": "오토메 게임",
        "ＢＷＫ大賞１": "BWK 대상 1",
        "曇らせ": "고통/피폐 전개",
        "スキル": "스킬",
        "青春": "청춘",
        "料理": "요리",
        "転生": "전생",
        "コミカライズ": "코미컬라이즈",
        "聖女": "성녀",
        "ゲーム": "게임",
        "HJ大賞7": "HJ 대상 7",
        "貴族": "귀족",
        "最強": "최강",
        "掲示板": "게시판",
        "職業もの": "직업물",
        "ダンジョン配信": "던전 방송",
        "ざまあ": "사이다/복수",
        "オリジナル戦記": "오리지널 전기",
        "BK小説大賞2": "BK 소설 대상 2",
        "歴史〔文芸〕": "역사 문예",
        "身分差": "신분 차이",
        "幼馴染": "소꿉친구",
        "王女": "왕녀",
        "男性向け": "남성향",
        "激重感情": "무거운 감정선",
        "人外": "인외",
        "集英社小説大賞７": "슈에이샤 소설 대상 7",
        "切ない": "애절함",
        "政略結婚": "정략결혼",
        "令嬢": "영애",
        "現地主人公": "현지인 주인공",
        "現代ダンジョン": "현대 던전",
        "飯テロ": "음식 묘사/먹방",
        # Chinese tags
        "天作之合": "천생연분",
        "豪门世家": "재벌/명문가",
        "剧情": "드라마/서사",
        "正剧": "정극",
        "幻想未来": "미래 판타지",
        "业界精英": "업계 엘리트",
        "穿书": "책빙의",
        "仙侠": "선협",
        "都市": "도시",
        "成长": "성장",
        "衍生": "파생/팬덤",
        "仙侠修真": "선협/수진",
        "古色古香": "고전풍",
        "男主视角": "남성 주인공 시점",
        "治愈": "힐링",
        "宫廷侯爵": "궁정/귀족",
        "灵异神怪": "괴담/초자연",
        "暗恋": "짝사랑",
        "幻想空间": "판타지 공간",
        "升级流": "레벨업/성장류",
        "无CP": "무CP",
        "东方衍生": "동양풍 파생",
        "快穿": "퀵 트랜스미션",
        "沙雕": "병맛/개그",
        "双视角视角": "쌍방 시점",
        "群像": "군상극",
        "重生": "환생/회귀",
        "种田文": "전원/경영물",
        "HE": "해피엔딩",
        "剑道": "검도/검술",
        "高岭之花": "고고한 인물",
        "美食": "음식/미식",
        "萌宠": "귀여운 반려동물",
        "团宠": "총애받는 인물",
        "万人迷": "만인의 사랑/인기인",
        "经营": "경영",
        "武侠仙侠": "무협/선협",
        "异能": "이능력",
        "青梅竹马": "소꿉친구",
        "励志": "격려/성공담",
        "生子": "출산/임신",
        "综漫": "종합 애니 팬픽",
        "文野": "문호 스트레이독스 팬픽",
        "脑洞": "상상력/아이디어",
        "末世": "아포칼립스",
        "基建": "기반 건설",
        "先婚后爱": "선결혼 후연애",
        "狗血": "막장/자극적 전개",
        "欢喜冤家": "티격태격 커플",
        "日久生情": "시간이 지나며 싹트는 사랑",
        "无限流": "무한류",
        "随身空间": "휴대/개인 공간",
        "少年": "소년",
        # Thai tags
        "นิยายโรแมนติก": "로맨스 소설",
        "ความรัก": "사랑",
        "นิยายรักวัยรุ่น": "청춘 로맨스 소설",
        "นิยายโรมานซ์": "로맨스 소설",
        "นิยายรักวัยว้าวุ่น": "청춘 로맨스",
        "หวาน": "달달함",
        "ทะลุมิติ": "차원이동/빙의",
        "ดราม่า": "드라마",
        "มาเฟีย": "마피아",
        "เพื่อนสนิท": "절친",
        "อดีต ปัจจุบัน อนาคต": "과거/현재/미래",
        "รุ่นพี่": "선배",
        "เกิดใหม่": "환생/전생",
        "ย้อนอดีต": "과거 회귀",
        "นิยายจีน": "중국 소설",
        "แต่งงาน": "결혼",
        "พีเรียดจีน (จีนโบราณ)": "중국 시대극/고전",
        "นิยายจีนโบราณ": "중국 고전 소설",
        "มหาลัย": "대학",
        "รุ่นพี่รุ่นน้อง": "선후배",
        "ตบจูบ": "강압적 로맨스",
        "แอบรักเพื่อน": "친구 짝사랑",
        "ท้อง": "임신",
        "ย้อนยุค": "시대 회귀/복고",
        "หมอ": "의사",
        "รักสามเส้า": "삼각관계",
        "รักต่างวัย": "나이차 로맨스",
        "แก้แค้น": "복수",
        "มีลูก": "육아/자녀",
        "นางร้าย": "악녀",
        "พีเรียด": "시대극",
        "ตัวร้าย": "악역",
        "เพื่อนสนิทคิดไม่ซื่อ": "절친 짝사랑",
        "Erotic": "에로틱",
        "โหด": "거친/잔혹",
        "หื่น": "선정적",
        "พระเอกสายเปย์": "재력가 남주",
        "แฟนฟิคนิยาย การ์ตูน เกม": "팬픽션",
        "เกิดใหม่ในนิยาย": "소설 속 환생/빙의",
        "ไทยพีเรียด": "태국 시대극",
        "พระเอกกินเด็ก": "나이차/연상남",
        "แอบรักเพื่อนสนิท": "절친 짝사랑",
        "คลั่งรัก": "집착적 사랑",
        "พีเรียดไทย": "태국 시대극",
        "โคแก่": "나이차 로맨스",
        "แฟนเก่า": "전 연인",
        "รีเทิร์น": "재회",
        "นักศึกษา": "대학생",
        "หวง": "소유욕",
        "พี่ว๊าก": "선배/기강 문화",
        "โรงเรียน": "학교",
        "คลั่งรักขั้นสุด": "강한 집착/헌신",
        "วัยรุ่น": "청소년/청춘",
    }
)

EXCLUDED_ANALYSIS_LABEL_PREFIXES = ("joylada_ranking_box_",)

EXCLUDED_ANALYSIS_LABELS = {
    # Service / monetization / publication-state labels.
    "WAIT_UNTIL_FREE",
    "ON_GOING",
    "ONGOING",
    "ongoing",
    "COMPLETED",
    "completed",
    "Original",
    "texttospeech",
    "TTS",
    # Japanese platform/publication/award/format labels.
    "小説",
    "連載中",
    "長編",
    "短編",
    "完結",
    "完結済",
    "完結保証",
    "書籍化",
    "コミカライズ",
    "カクヨムオンリー",
    "ＥＳＮ大賞１０",
    "ＢＷＫ大賞１",
    "HJ大賞7",
    "BK小説大賞2",
    "集英社小説大賞７",
    "JR西じゆうに大賞1",
    "春チャレンジ2026",
    # Chinese publication/source labels.
    "原创",
}

SENSITIVE_LABEL_HINTS = {
    "R15",
    "R18",
    "18+",
    "Adult",
    "Smut",
    "SMUT",
    "Ecchi",
    "잔혹",
    "残酷な描写あり",
    "Harem",
    "HAREM",
    "BL",
    "GL",
    "วาย",
    "純愛",
    "纯爱",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep a BOM for Windows PowerShell/Notepad-friendly Korean/Japanese display.
    path.write_text(text, encoding="utf-8-sig")


def label_ko(label: str) -> str:
    return LABEL_KO.get(label, label)


CANONICAL_ID_OVERRIDES: dict[str, str] = {
    "로맨스": "romance",
    "연애/로맨스": "romance",
    "사랑/로맨스": "romance",
    "로맨스 판타지": "romance_fantasy",
    "이세계": "isekai",
    "이세계 전생": "isekai_reincarnation",
    "이세계 전이": "isekai_transmigration",
    "차원이동/빙의": "portal_transmigration",
    "환생/전생": "reincarnation",
    "전생": "reincarnation",
    "회귀": "regression",
    "혼약 파기": "engagement_break",
    "정략결혼": "political_marriage",
    "결혼": "marriage",
    "악역영애": "villainess",
    "악녀": "villainess",
    "사이다/복수": "revenge_payoff",
    "사이다/쾌감형": "revenge_payoff",
    "복수": "revenge",
    "해피엔딩": "happy_ending",
    "마법": "magic",
    "귀족": "nobility",
    "왕족/왕실": "royalty",
    "학원": "academy",
    "학원/학교생활": "school_life",
    "던전": "dungeon",
    "영지 건설": "territory_building",
    "국가/영지 건설": "kingdom_building",
    "R15": "r15",
    "R18": "r18",
    "18+": "adult_18_plus",
    "잔혹 묘사 있음": "cruel_depiction",
    "성인": "adult",
    "성인/선정 요소": "adult_smut",
    "BL/보이즈러브": "boys_love",
    "GL/걸즈러브": "girls_love",
}


def canonical_label_id(label_display: str) -> str:
    if label_display in CANONICAL_ID_OVERRIDES:
        return CANONICAL_ID_OVERRIDES[label_display]
    digest = hashlib.sha1(label_display.encode("utf-8")).hexdigest()[:10]
    return f"label_{digest}"


def label_category(label_display: str, original: str = "") -> str:
    text = f"{label_display} {original}"
    if any(token in text for token in ["R15", "R18", "18+", "성인", "선정", "잔혹", "피폐", "강압", "BL", "GL", "하렘"]):
        return "content_flag"
    if any(token in text for token in ["해피엔딩", "HE", "완결"]):
        return "ending_signal"
    if any(token in text for token in ["로맨스", "판타지", "무협", "선협", "SF", "액션", "코미디", "드라마", "공포", "미스터리", "LitRPG"]):
        return "genre"
    if any(token in text for token in ["전생", "회귀", "빙의", "전이", "이세계", "혼약", "결혼", "추방", "복수", "사이다", "쾌감", "시스템", "치트", "성장", "레벨업", "재건", "건설", "차원이동"]):
        return "plot_device"
    if any(token in text for token in ["시리어스", "훈훈", "잔잔", "개그", "달달", "가벼운", "힐링", "필굿", "애절", "집착", "소유욕", "열혈"]):
        return "tone"
    if any(token in text for token in ["학원", "학교", "던전", "왕궁", "왕실", "귀족", "중세", "현대", "서양", "도시", "영지", "궁정", "대학", "역사"]):
        return "setting"
    if any(token in text for token in ["주인공", "영애", "성녀", "남주", "여주", "악녀", "악역", "귀여운 반려동물", "엘리트", "재력가"]):
        return "character"
    return "other"


def display_note_for_label(item: dict[str, Any]) -> str:
    coverage = item.get("platform_coverage") or {}
    observed = coverage.get("observed", 0)
    total = coverage.get("total", 0)
    if observed and total and observed == total:
        return "모든 포함 플랫폼 샘플에서 반복 관찰됨"
    if observed and total:
        return f"{observed}/{total} 플랫폼 샘플에서 관찰됨"
    return "랭킹/인기 공개 샘플에서 관찰됨"


def is_analysis_label(label: Any) -> bool:
    text = str(label)
    return (
        bool(text)
        and text not in EXCLUDED_ANALYSIS_LABELS
        and not text.startswith(EXCLUDED_ANALYSIS_LABEL_PREFIXES)
    )


def analysis_labels(row: dict[str, Any]) -> list[str]:
    return [str(label) for label in row.get("labels") or [] if is_analysis_label(label)]


def load_records(raw_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(raw_dir.rglob("*.json")):
        payload = read_json(path)
        for idx, record in enumerate(payload.get("records") or [], start=1):
            row = dict(record)
            row["source_file"] = str(path.as_posix())
            row["record_id"] = (
                f"{row.get('market')}::{row.get('platform')}::{row.get('signal_type')}::"
                f"{row.get('rank', idx)}::{idx}"
            )
            row["labels_raw"] = list(row.get("labels") or [])
            row["rank_band"] = rank_bucket(row.get("rank"))
            row["synopsis_present"] = bool(str(row.get("synopsis") or "").strip())
            row["available_metric_keys"] = sorted((row.get("public_metrics") or {}).keys())
            source_key = (str(row.get("platform")), str(row.get("signal_type")))
            included = (
                row.get("platform") not in EXCLUDED_CONTEXT_PLATFORMS
                and row.get("market") in MARKET_SLUGS
                and source_key not in EXCLUDED_CONTEXT_SOURCES
            )
            row["included_in_context_pack"] = included
            if not included:
                row["exclusion_reason"] = EXCLUDED_CONTEXT_SOURCES.get(source_key, EXCLUSION_REASON)
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def top_labels(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in records:
        counter.update(analysis_labels(row))
    total = len(records) or 1
    return [
        {
            "label_original": label,
            "label_ko": label_ko(label),
            "count": count,
            "share": round(count / total, 4),
        }
        for label, count in counter.most_common(limit)
    ]


def top_label_groups(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    originals: dict[str, Counter[str]] = defaultdict(Counter)
    for row in records:
        seen_in_record = set()
        for label in analysis_labels(row):
            ko = label_ko(label)
            originals[ko][label] += 1
            seen_in_record.add(ko)
        counter.update(seen_in_record)
    total = len(records) or 1
    return [
        {
            "label_ko": ko,
            "count": count,
            "share": round(count / total, 4),
            "source_labels": [label for label, _ in originals[ko].most_common(5)],
        }
        for ko, count in counter.most_common(limit)
    ]


def platform_balanced_label_groups(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_platform[str(row.get("platform") or "unknown")].append(row)

    label_platform_stats: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_labels: dict[str, Counter[str]] = defaultdict(Counter)
    for platform, rows in by_platform.items():
        platform_total = len(rows) or 1
        present: Counter[str] = Counter()
        for row in rows:
            seen = set()
            for label in analysis_labels(row):
                ko = label_ko(label)
                seen.add(ko)
                source_labels[ko][label] += 1
            present.update(seen)
        for ko, count in present.items():
            label_platform_stats[ko].append(
                {
                    "platform": platform,
                    "count": count,
                    "record_count": len(rows),
                    "share": count / platform_total,
                }
            )

    out: list[dict[str, Any]] = []
    platform_count = len(by_platform) or 1
    for ko, stats in label_platform_stats.items():
        avg_share = sum(item["share"] for item in stats) / platform_count
        out.append(
            {
                "label_ko": ko,
                "platforms_observed": len(stats),
                "platform_count": platform_count,
                "avg_platform_share": round(avg_share, 4),
                "max_platform_share": round(max(item["share"] for item in stats), 4),
                "source_labels": [label for label, _ in source_labels[ko].most_common(5)],
                "platform_breakdown": sorted(stats, key=lambda item: (-item["share"], item["platform"]))[:5],
            }
        )
    return sorted(out, key=lambda item: (-item["avg_platform_share"], -item["platforms_observed"], item["label_ko"]))[:limit]


def signal_type_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[(str(row.get("platform")), str(row.get("signal_type")))].append(row)
    out: list[dict[str, Any]] = []
    for (platform, signal_type), rows in sorted(grouped.items()):
        out.append(
            {
                "platform": platform,
                "signal_type": signal_type,
                "record_count": len(rows),
                "top_label_groups": top_label_groups(rows, 8),
                "synopsis_present_share": round(
                    sum(1 for row in rows if str(row.get("synopsis") or "").strip()) / (len(rows) or 1),
                    4,
                ),
            }
        )
    return out


def label_frequency_by_group(records: list[dict[str, Any]], group_fields: list[str], limit: int | None = None) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[tuple(row.get(field) for field in group_fields)].append(row)
    out: list[dict[str, Any]] = []
    for key, group_rows in sorted(grouped.items(), key=lambda item: tuple(str(x) for x in item[0])):
        labels = top_labels(group_rows, limit or 10_000)
        for item in labels:
            out.append({field: value for field, value in zip(group_fields, key)} | {"record_count": len(group_rows)} | item)
    return out


def label_cooccurrence(records: list[dict[str, Any]], group_field: str = "market", limit: int = 50) -> list[dict[str, Any]]:
    grouped: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    totals: Counter[str] = Counter()
    for row in records:
        group = str(row.get(group_field) or "unknown")
        labels = sorted(set(analysis_labels(row)))
        if len(labels) < 2:
            continue
        totals[group] += 1
        for a, b in combinations(labels, 2):
            if label_ko(a) == label_ko(b):
                continue
            grouped[group][(a, b)] += 1

    out: list[dict[str, Any]] = []
    for group, counter in sorted(grouped.items()):
        for (a, b), count in counter.most_common(limit):
            out.append(
                {
                    group_field: group,
                    "label_a_original": a,
                    "label_a_ko": label_ko(a),
                    "label_b_original": b,
                    "label_b_ko": label_ko(b),
                    "co_count": count,
                    "records_with_label_pairs": totals[group],
                }
            )
    return out


def rank_bucket(rank: Any) -> str:
    try:
        value = int(rank)
    except (TypeError, ValueError):
        return "unknown"
    if value <= 10:
        return "top_10"
    if value <= 30:
        return "rank_11_30"
    if value <= 50:
        return "rank_31_50"
    if value <= 100:
        return "rank_51_100"
    return "rank_101_plus"


def rank_bucket_label_frequency(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[(str(row.get("market")), rank_bucket(row.get("rank")))].append(row)
    out: list[dict[str, Any]] = []
    for (market, bucket), group_rows in sorted(grouped.items()):
        for item in top_labels(group_rows, 30):
            out.append({"market": market, "rank_bucket": bucket, "bucket_record_count": len(group_rows)} | item)
    return out


RANK_BAND_WEIGHTS = {
    "top_10": 1.0,
    "rank_11_30": 0.7,
    "rank_31_50": 0.45,
    "rank_51_100": 0.25,
    "rank_101_plus": 0.15,
    "unknown": 0.1,
}


def record_label_groups(row: dict[str, Any]) -> set[str]:
    return {label_ko(label) for label in analysis_labels(row)}


def build_label_dictionary(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in records:
        market = str(row.get("market") or "unknown")
        for raw_label in analysis_labels(row):
            display = label_ko(raw_label)
            item = grouped.setdefault(
                display,
                {
                    "canonical_label_id": canonical_label_id(display),
                    "label_ko": display,
                    "label_en": "",
                    "category": label_category(display, raw_label),
                    "raw_variants": set(),
                    "markets": set(),
                    "match_type": "tag_normalization" if display != raw_label else "direct_label",
                    "notes": "",
                },
            )
            item["raw_variants"].add(raw_label)
            item["markets"].add(market)
            if item["category"] == "other":
                item["category"] = label_category(display, raw_label)

    labels = []
    for item in grouped.values():
        labels.append(
            item
            | {
                "raw_variants": sorted(item["raw_variants"]),
                "markets": sorted(item["markets"]),
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "Canonical display labels used for platform observation UI/stat projections.",
        "categories": [
            "genre",
            "plot_device",
            "tone",
            "setting",
            "character",
            "content_flag",
            "ending_signal",
            "other",
        ],
        "labels": sorted(labels, key=lambda item: (item["category"], item["label_ko"])),
    }


def market_tag_snapshot(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_market[str(row.get("market"))].append(row)

    out: list[dict[str, Any]] = []
    for market, rows in sorted(by_market.items()):
        platforms = sorted({str(row.get("platform")) for row in rows})
        total_weight = sum(RANK_BAND_WEIGHTS.get(str(row.get("rank_band")), 0.1) for row in rows) or 1.0
        label_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        raw_examples: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            for raw_label in analysis_labels(row):
                display = label_ko(raw_label)
                label_records[display].append(row)
                raw_examples[display][raw_label] += 1

        labels: list[dict[str, Any]] = []
        for display, label_rows in label_records.items():
            seen_records = {row["record_id"]: row for row in label_rows}.values()
            band_counter = Counter(str(row.get("rank_band") or "unknown") for row in seen_records)
            platform_counter = Counter(str(row.get("platform")) for row in seen_records)
            weighted = sum(RANK_BAND_WEIGHTS.get(str(row.get("rank_band")), 0.1) for row in seen_records)
            item = {
                "canonical_label_id": canonical_label_id(display),
                "label_ko": display,
                "category": label_category(display),
                "raw_examples": [label for label, _ in raw_examples[display].most_common(5)],
                "count": len(list(seen_records)),
                "share": round(len(list(seen_records)) / (len(rows) or 1), 4),
                "platform_coverage": {"observed": len(platform_counter), "total": len(platforms)},
                "avg_platform_share": round(
                    sum(platform_counter.get(platform, 0) / max(1, sum(1 for row in rows if row.get("platform") == platform)) for platform in platforms)
                    / (len(platforms) or 1),
                    4,
                ),
                "max_platform_share": round(
                    max(
                        [platform_counter.get(platform, 0) / max(1, sum(1 for row in rows if row.get("platform") == platform)) for platform in platforms]
                        or [0]
                    ),
                    4,
                ),
                "rank_band_distribution": {band: band_counter.get(band, 0) for band in RANK_BAND_WEIGHTS},
                "weighted_score": round(weighted, 4),
                "weighted_share": round(weighted / total_weight, 4),
            }
            item["display_note"] = display_note_for_label(item)
            labels.append(item)
        labels.sort(key=lambda item: (-item["weighted_score"], -item["count"], item["label_ko"]))
        out.append(
            {
                "market": market,
                "market_ko": MARKET_DISPLAY_KO.get(market, market),
                "record_count": len(rows),
                "platform_count": len(platforms),
                "labels": labels,
            }
        )
    return out


def platform_tag_profiles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    market_snapshots = {item["market"]: {label["label_ko"]: label for label in item["labels"]} for item in market_tag_snapshot(records)}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[(str(row.get("market")), str(row.get("platform")))].append(row)

    profiles: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (market, platform), rows in sorted(grouped.items()):
        top = top_label_groups(rows, 12)
        top_labels = [
            {
                "canonical_label_id": canonical_label_id(item["label_ko"]),
                "label_ko": item["label_ko"],
                "category": label_category(item["label_ko"]),
                "count": item["count"],
                "share": item["share"],
                "raw_examples": item.get("source_labels") or [],
            }
            for item in top
        ]
        distinctive = []
        for item in top_labels:
            market_item = market_snapshots.get(market, {}).get(item["label_ko"]) or {}
            market_share = float(market_item.get("share") or 0)
            if item["count"] < 3 or market_share <= 0:
                continue
            lift = item["share"] / market_share
            if lift >= 1.25:
                distinctive.append(
                    {
                        "canonical_label_id": item["canonical_label_id"],
                        "label_ko": item["label_ko"],
                        "category": item["category"],
                        "platform_share": item["share"],
                        "market_share": round(market_share, 4),
                        "lift": round(lift, 2),
                    }
                )
        distinctive.sort(key=lambda item: (-item["lift"], -item["platform_share"], item["label_ko"]))
        metrics = sorted({key for row in rows for key in (row.get("public_metrics") or {}).keys()})
        top_text = ", ".join(item["label_ko"] for item in top_labels[:4]) or "반복해서 보인 작품 태그 없음"
        profiles[market].append(
            {
                "platform": platform,
                "signal_types": sorted({str(row.get("signal_type")) for row in rows}),
                "record_count": len(rows),
                "top_labels": top_labels,
                "distinctive_labels": distinctive[:8],
                "available_metrics": metrics,
                "synopsis_present_share": round(sum(1 for row in rows if row.get("synopsis_present")) / (len(rows) or 1), 4),
                "summary_sentence": f"{platform} 순위권 작품에서는 {top_text} 계열 태그가 상대적으로 눈에 띕니다.",
            }
        )
    return [
        {
            "market": market,
            "market_ko": MARKET_DISPLAY_KO.get(market, market),
            "platform_profiles": rows,
        }
        for market, rows in sorted(profiles.items())
    ]


def rank_band_profiles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row.get("market"))].append(row)

    out: list[dict[str, Any]] = []
    for market, rows in sorted(grouped.items()):
        market_counts = Counter()
        for row in rows:
            market_counts.update(record_label_groups(row))
        bands = []
        for band in RANK_BAND_WEIGHTS:
            band_rows = [row for row in rows if row.get("rank_band") == band]
            if not band_rows:
                continue
            band_top = top_label_groups(band_rows, 12)
            top_labels = [
                {
                    "canonical_label_id": canonical_label_id(item["label_ko"]),
                    "label_ko": item["label_ko"],
                    "category": label_category(item["label_ko"]),
                    "count": item["count"],
                    "share": item["share"],
                }
                for item in band_top
            ]
            concentrated = []
            for item in top_labels:
                market_share = market_counts[item["label_ko"]] / (len(rows) or 1)
                if item["count"] >= 2 and market_share > 0 and item["share"] / market_share >= 1.25:
                    concentrated.append(
                        {
                            "canonical_label_id": item["canonical_label_id"],
                            "label_ko": item["label_ko"],
                            "category": item["category"],
                            "band_share": item["share"],
                            "market_share": round(market_share, 4),
                            "lift": round(item["share"] / market_share, 2),
                        }
                    )
            bands.append(
                {
                    "rank_band": band,
                    "record_count": len(band_rows),
                    "top_labels": top_labels,
                    "labels_with_top_band_concentration": concentrated[:8],
                }
            )
        out.append({"market": market, "market_ko": MARKET_DISPLAY_KO.get(market, market), "rank_bands": bands})
    return out


def cooccurrence_patterns(records: list[dict[str, Any]], min_count: int = 10) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row.get("market"))].append(row)

    out: list[dict[str, Any]] = []
    for market, rows in sorted(grouped.items()):
        label_counts = Counter()
        pair_counts = Counter()
        pair_platforms: dict[tuple[str, str], set[str]] = defaultdict(set)
        pair_bands: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        platforms = sorted({str(row.get("platform")) for row in rows})
        for row in rows:
            labels = sorted(record_label_groups(row))
            label_counts.update(labels)
            for a, b in combinations(labels, 2):
                pair = (a, b)
                pair_counts[pair] += 1
                pair_platforms[pair].add(str(row.get("platform")))
                pair_bands[pair][str(row.get("rank_band") or "unknown")] += 1

        pairs = []
        for (a, b), count in pair_counts.items():
            if count < min_count:
                continue
            union = label_counts[a] + label_counts[b] - count
            expected = (label_counts[a] / (len(rows) or 1)) * (label_counts[b] / (len(rows) or 1))
            observed = count / (len(rows) or 1)
            lift = observed / expected if expected else 0
            if not (count >= 20 or len(pair_platforms[(a, b)]) >= 2 or lift >= 1.2):
                continue
            pairs.append(
                {
                    "label_pair": [canonical_label_id(a), canonical_label_id(b)],
                    "label_ko": [a, b],
                    "categories": [label_category(a), label_category(b)],
                    "count": count,
                    "jaccard": round(count / union, 4) if union else 0,
                    "lift": round(lift, 2),
                    "platform_coverage": {"observed": len(pair_platforms[(a, b)]), "total": len(platforms)},
                    "rank_band_distribution": {band: pair_bands[(a, b)].get(band, 0) for band in RANK_BAND_WEIGHTS},
                    "display_sentence": "두 태그가 같은 순위권 작품 안에서 함께 보인 경우가 있습니다.",
                }
            )
        pairs.sort(key=lambda item: (-item["count"], -item["lift"], item["label_ko"]))
        out.append({"market": market, "market_ko": MARKET_DISPLAY_KO.get(market, market), "pairs": pairs[:80]})
    return out


def metric_distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"available_count": 0, "min": None, "median": None, "max": None}
    return {
        "available_count": len(values),
        "min": min(values),
        "median": statistics.median(values),
        "max": max(values),
    }


def metric_coverage(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row.get("platform"))].append(row)
    out: list[dict[str, Any]] = []
    for platform, group_rows in sorted(grouped.items()):
        metric_values: dict[str, list[float]] = defaultdict(list)
        for row in group_rows:
            for key, value in (row.get("public_metrics") or {}).items():
                if isinstance(value, (int, float)):
                    metric_values[key].append(float(value))
        for metric, values in sorted(metric_values.items()):
            out.append(
                {
                    "platform": platform,
                    "record_count": len(group_rows),
                    "metric": metric,
                    **metric_distribution(values),
                }
            )
    return out


def synopsis_coverage(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row.get("platform"))].append(row)
    out: list[dict[str, Any]] = []
    for platform, group_rows in sorted(grouped.items()):
        present = [row for row in group_rows if str(row.get("synopsis") or "").strip()]
        out.append(
            {
                "platform": platform,
                "record_count": len(group_rows),
                "synopsis_present_count": len(present),
                "synopsis_present_share": round(len(present) / (len(group_rows) or 1), 4),
                "usage_note": "시놉 기반 내용 신호 보조 가능" if present else "시놉 기반 분석 제한",
            }
        )
    return out


def sensitive_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in records:
        matched = []
        labels = analysis_labels(row)
        for label in labels:
            if label in SENSITIVE_LABEL_HINTS or any(hint in label for hint in SENSITIVE_LABEL_HINTS):
                matched.append({"label_original": label, "label_ko": label_ko(label)})
        if matched:
            out.append(
                {
                    "record_id": row["record_id"],
                    "market": row.get("market"),
                    "platform": row.get("platform"),
                    "signal_type": row.get("signal_type"),
                    "rank": row.get("rank"),
                    "matched_labels": matched,
                    "evidence_source": "labels",
                    "usage_note": "규정/규제 데이터와 결합할 때 검토 후보로만 사용",
                }
            )
    return out


def platform_summary(records: list[dict[str, Any]], platform: str) -> dict[str, Any]:
    rows = [row for row in records if row.get("platform") == platform]
    signal_types = sorted(set(str(row.get("signal_type")) for row in rows))
    metrics = sorted({key for row in rows for key in (row.get("public_metrics") or {}).keys()})
    present = sum(1 for row in rows if str(row.get("synopsis") or "").strip())
    return {
        "platform": platform,
        "market": rows[0].get("market") if rows else None,
        "record_count": len(rows),
        "signal_types": signal_types,
        "top_labels": top_labels(rows, 12),
        "top_label_groups": top_label_groups(rows, 12),
        "available_metrics": metrics,
        "synopsis_present_share": round(present / (len(rows) or 1), 4),
    }


def market_pack(records: list[dict[str, Any]], market: str) -> dict[str, Any]:
    rows = [row for row in records if row.get("market") == market]
    platforms = sorted(set(str(row.get("platform")) for row in rows))
    signal_types = sorted(set(str(row.get("signal_type")) for row in rows))
    return {
        "market": market,
        "market_ko": MARKET_DISPLAY_KO.get(market, market),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_scope": "platform_observation_context_only",
        "record_count": len(rows),
        "platforms": platforms,
        "signal_types": signal_types,
        "use_limits": [
            "랭킹/인기 페이지 공개 샘플에서 관찰된 라벨·공개 지표 집계입니다.",
            "추천, 성과 예측, 시장 적합도 판단, 창작 방향 제안에 사용하지 않습니다.",
            "표현은 '관찰됨', '샘플 내 빈도', '검토 참고 항목'으로 제한합니다.",
            "플랫폼 간 public metric은 의미가 달라 직접 비교하지 않습니다.",
            "개별 작품명과 시놉시스는 대표 사례/근거 인용 없이 context pack에 넣지 않습니다.",
        ],
        "observed_top_labels": top_labels(rows, 30),
        "observed_top_label_groups": top_label_groups(rows, 30),
        "platform_balanced_label_groups": platform_balanced_label_groups(rows, 30),
        "platform_summaries": [platform_summary(rows, platform) for platform in platforms],
        "signal_type_summaries": signal_type_summaries(rows),
        "frequent_label_pairs": [
            item for item in label_cooccurrence(rows, "market", 30) if item["market"] == market
        ],
        "metric_coverage": [item for item in metric_coverage(rows)],
        "synopsis_coverage": synopsis_coverage(rows),
        "sensitive_label_candidates": [
            item for item in sensitive_candidates(rows)[:50]
        ],
    }


def render_markdown(pack: dict[str, Any]) -> str:
    def display_label_counts(items: list[dict[str, Any]], limit: int = 10) -> str:
        return ", ".join(f"{item['label_ko']}({item['count']})" for item in items[:limit]) or "없음"

    def display_pair_counts(items: list[dict[str, Any]], limit: int = 20) -> list[str]:
        counts: Counter[tuple[str, str]] = Counter()
        for item in items:
            a = str(item["label_a_ko"])
            b = str(item["label_b_ko"])
            if a == b:
                continue
            pair = tuple(sorted((a, b)))
            counts[pair] += int(item["co_count"])
        return [f"- {a} + {b}: {count}건" for (a, b), count in counts.most_common(limit)]

    lines: list[str] = []
    lines.append(f"# {pack['market_ko']} 플랫폼 관찰 Context Pack")
    lines.append("")
    lines.append("## 1. 데이터 범위")
    lines.append(f"- 시장: {pack['market']} / {pack['market_ko']}")
    lines.append(f"- 관찰 레코드 수: {pack['record_count']}")
    lines.append(f"- 포함 플랫폼: {', '.join(pack['platforms'])}")
    lines.append(f"- signal_type: {', '.join(pack['signal_types'])}")
    lines.append("")
    lines.append("## 2. 사용 제한")
    for note in pack["use_limits"]:
        lines.append(f"- {note}")
    lines.append("- 국가 전체 합산 count는 플랫폼별 표본 수 차이의 영향을 받으므로, 플랫폼 균등 가중치와 platform/signal_type별 요약을 함께 해석합니다.")
    lines.append("")
    lines.append("## 3. 수집 샘플 합산 기준 상위 관찰 태그: 한국어 표시명 기준")
    lines.append("")
    lines.append("> 이 섹션은 플랫폼별 수집 건수가 동일하지 않기 때문에 표본 수가 큰 플랫폼의 영향을 더 크게 받습니다.")
    lines.append("")
    lines.append("| 한국어 표시 | count | share | 주요 원문 태그 예시 |")
    lines.append("|---|---:|---:|---|")
    for item in pack["observed_top_label_groups"][:25]:
        source_labels = ", ".join(item["source_labels"])
        lines.append(
            f"| {item['label_ko']} | {item['count']} | {item['share']:.1%} | {source_labels} |"
        )
    lines.append("")
    lines.append("### 원문 태그별 상위 관찰")
    lines.append("| 원문 태그 | 한국어 표시 | count | share |")
    lines.append("|---|---|---:|---:|")
    for item in pack["observed_top_labels"][:15]:
        lines.append(
            f"| {item['label_original']} | {item['label_ko']} | {item['count']} | {item['share']:.1%} |"
        )
    lines.append("")
    lines.append("## 4. 플랫폼 균등 가중치 기준 상위 관찰 태그")
    lines.append("")
    lines.append("> 각 플랫폼 내 출현율을 계산한 뒤 플랫폼별 표본 수와 무관하게 평균낸 값입니다. 시장 대표값이 아니라 과대표집 완화용 참고값입니다.")
    lines.append("")
    lines.append("| 한국어 표시 | 관찰 플랫폼 수 | 평균 플랫폼 내 출현율 | 최대 플랫폼 내 출현율 | 주요 원문 태그 예시 |")
    lines.append("|---|---:|---:|---:|---|")
    for item in pack["platform_balanced_label_groups"][:20]:
        source_labels = ", ".join(item["source_labels"])
        lines.append(
            f"| {item['label_ko']} | {item['platforms_observed']}/{item['platform_count']} | "
            f"{item['avg_platform_share']:.1%} | {item['max_platform_share']:.1%} | {source_labels} |"
        )
    lines.append("")
    lines.append("## 5. 플랫폼별 관찰 요약")
    for platform in pack["platform_summaries"]:
        labels = display_label_counts(platform["top_label_groups"], 10)
        metrics = ", ".join(platform["available_metrics"]) or "없음"
        lines.append(f"### {platform['platform']}")
        lines.append(f"- 레코드 수: {platform['record_count']}")
        lines.append(f"- signal_type: {', '.join(platform['signal_types'])}")
        lines.append(f"- 상위 관찰 태그: {labels}")
        lines.append(f"- 사용 가능한 public metrics: {metrics}")
        lines.append(f"- 시놉시스 존재 비율: {platform['synopsis_present_share']:.1%}")
    lines.append("")
    lines.append("## 6. Platform / signal_type별 관찰 요약")
    for item in pack["signal_type_summaries"]:
        labels = display_label_counts(item["top_label_groups"], 8)
        lines.append(f"### {item['platform']} / {item['signal_type']}")
        lines.append(f"- 레코드 수: {item['record_count']}")
        lines.append(f"- 상위 관찰 태그: {labels}")
        lines.append(f"- 시놉시스 존재 비율: {item['synopsis_present_share']:.1%}")
    lines.append("")
    lines.append("## 7. 자주 함께 관찰된 태그 조합")
    lines.extend(display_pair_counts(pack["frequent_label_pairs"], 20))
    lines.append("")
    lines.append("## 8. 시놉/민감 라벨 사용 메모")
    lines.append("- 시놉시스는 창작 방향 추천이 아니라 태그에 없는 내용 신호 확인과 규정/규제 검토 후보 보조에만 사용합니다.")
    lines.append("- 민감 라벨 후보는 규정/규제 데이터와 결합할 때 검토 대상으로만 사용하며, 위반 판단으로 단정하지 않습니다.")
    lines.append("")
    return "\n".join(lines)


def build_global_overview(records: list[dict[str, Any]], included: list[dict[str, Any]]) -> str:
    excluded = [row for row in records if not row.get("included_in_context_pack")]
    by_market = Counter(str(row.get("market")) for row in included)
    by_platform = Counter(str(row.get("platform")) for row in included)
    lines = [
        "# 플랫폼 관찰 데이터 개요",
        "",
        f"- 전체 raw 레코드: {len(records)}",
        f"- context pack 포함 레코드: {len(included)}",
        f"- context pack 제외 레코드: {len(excluded)}",
        "",
        "## 포함 시장",
    ]
    for market, count in by_market.most_common():
        lines.append(f"- {market} / {MARKET_DISPLAY_KO.get(market, market)}: {count}건")
    lines.extend(["", "## 포함 플랫폼"])
    for platform, count in by_platform.most_common():
        lines.append(f"- {platform}: {count}건")
    lines.extend(
        [
            "",
            "## 사용 원칙",
            "- 본 데이터는 랭킹/인기 페이지 관찰 샘플입니다.",
            "- 추천, 성과 예측, 시장 적합도 판단, 창작 방향 제안에 사용하지 않습니다.",
            "- 시장별 분석에는 해당 시장 context pack만 사용합니다.",
            "- 플랫폼 간 public metric은 직접 비교하지 않습니다.",
            "",
            "## 제외 데이터",
            "다음 데이터는 국가/규정 매칭 기준이 불명확하여 현지화 context pack 생성 대상에서 제외했습니다.",
        ]
    )
    excluded_sources = sorted({f"{row.get('platform')} / {row.get('signal_type')}" for row in excluded})
    for source in excluded_sources:
        lines.append(f"- {source}")
    if excluded_sources:
        lines.extend(
            [
                "",
                "제외 사유:",
                f"- {EXCLUSION_REASON}",
                "- market 값이 Global이거나 국가별 규정/규제 데이터와 결합하기 어렵습니다.",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build market-specific Korean context packs from raw platform observation data.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    records = load_records(args.raw_dir)
    included = [row for row in records if row.get("included_in_context_pack")]
    out_dir = args.out_dir
    pack_dir = out_dir / "context_packs"
    out_dir.mkdir(parents=True, exist_ok=True)
    pack_dir.mkdir(parents=True, exist_ok=True)

    write_jsonl(out_dir / "normalized_records.jsonl", records)
    dump_json(out_dir / "raw_records_normalized.json", records)
    dump_json(out_dir / "label_dictionary.json", build_label_dictionary(included))
    dump_json(out_dir / "label_frequency_by_market.json", label_frequency_by_group(included, ["market"]))
    dump_json(out_dir / "label_frequency_by_platform.json", label_frequency_by_group(included, ["market", "platform"]))
    dump_json(out_dir / "label_cooccurrence_by_market.json", label_cooccurrence(included))
    dump_json(out_dir / "rank_bucket_label_frequency.json", rank_bucket_label_frequency(included))
    dump_json(out_dir / "market_tag_snapshot.json", market_tag_snapshot(included))
    dump_json(out_dir / "platform_tag_profiles.json", platform_tag_profiles(included))
    dump_json(out_dir / "rank_band_profiles.json", rank_band_profiles(included))
    dump_json(out_dir / "cooccurrence_patterns.json", cooccurrence_patterns(included))
    dump_json(out_dir / "metric_coverage_by_platform.json", metric_coverage(included))
    dump_json(out_dir / "synopsis_coverage_by_platform.json", synopsis_coverage(included))
    dump_json(out_dir / "sensitive_label_candidates.json", sensitive_candidates(included))

    pack_index: list[dict[str, Any]] = []
    for market, slug in MARKET_SLUGS.items():
        pack = market_pack(included, market)
        if pack["record_count"] <= 0:
            continue
        dump_json(pack_dir / f"{slug}_observation_context_ko.json", pack)
        write_markdown(pack_dir / f"{slug}_observation_context_ko.md", render_markdown(pack))
        pack_index.append(
            {
                "market": market,
                "slug": slug,
                "record_count": pack["record_count"],
                "json": f"context_packs/{slug}_observation_context_ko.json",
                "markdown": f"context_packs/{slug}_observation_context_ko.md",
            }
        )

    write_markdown(pack_dir / "global_observation_overview_ko.md", build_global_overview(records, included))
    dump_json(
        out_dir / "dataset_summary.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "raw_record_count": len(records),
            "context_record_count": len(included),
            "excluded_record_count": len(records) - len(included),
            "excluded_platforms": sorted(EXCLUDED_CONTEXT_PLATFORMS),
            "excluded_sources": [
                {"platform": platform, "signal_type": signal_type, "reason": reason}
                for (platform, signal_type), reason in sorted(EXCLUDED_CONTEXT_SOURCES.items())
            ],
            "exclusion_reason": EXCLUSION_REASON,
            "context_packs": pack_index,
        },
    )

    print(f"Built {len(pack_index)} context packs under {pack_dir}")
    print(f"Included records: {len(included)} / raw records: {len(records)}")


if __name__ == "__main__":
    main()
