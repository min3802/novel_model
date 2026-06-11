"""Agent-orchestrated Tavily + GPT localization report generator.

Final goal:
    User inputs a target country and webnovel genre.
    The orchestrator searches public web evidence with Tavily and renders
    a website/PDF-friendly HTML localization report.

Design:
    Tavily handles public-web evidence collection.
    GPT-4.1 mini handles evidence-grounded synthesis.

Usage:
    conda run -n fn_env python localization_orchestrator.py --country 미국 --genre 현대 로맨스
    conda run -n fn_env python localization_orchestrator.py --country JP --genre 이세계 판타지 --max-results 5

Environment:
    TAVILY_API_KEY must exist in .env or process environment.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "raw"
CACHE_DIR = DATA_DIR / "tavily_cache"
REPORT_DIR = DATA_DIR / "localization_reports"
EXAMPLE_HTML = DATA_DIR / "us_webnovel_localization_guide.html"


COUNTRY_ALIASES: dict[str, dict[str, str]] = {
    "US": {
        "ko": "미국",
        "en": "United States",
        "tavily": "united states",
        "market_terms": "US webnovel online fiction reader market",
        "native_terms": "webnovel reader preferences romance fantasy BookTok Wattpad Tapas Radish",
        "locale_note": "영어권 공개 웹문서·커뮤니티 자료가 많아 공개 웹 근거 수집 효율이 높습니다.",
    },
    "JP": {
        "ko": "일본",
        "en": "Japan",
        "tavily": "japan",
        "market_terms": "Japan web novel light novel reader market",
        "native_terms": "日本 Web小説 ライトノベル 小説家になろう カクヨム 人気 ジャンル 読者 傾向",
        "locale_note": "일본어 쿼리를 병행해야 하며, 검색 결과는 플랫폼 내부 원천 랭킹이 아니라 공개 웹 근거입니다.",
    },
    "CN": {
        "ko": "중국",
        "en": "China",
        "tavily": "china",
        "market_terms": "China web novel online literature market",
        "native_terms": "中国 网络文学 网文 起点中文网 热门 类型 趋势 读者",
        "locale_note": "폐쇄적 플랫폼과 검색 접근성 이슈 때문에 2차 자료·시장 기사 비중이 높을 수 있습니다.",
    },
    "TH": {
        "ko": "태국",
        "en": "Thailand",
        "tavily": "thailand",
        "market_terms": "Thailand web novel online fiction reader market",
        "native_terms": "นิยายออนไลน์ ไทย readAwrite Dek-D ธัญวลัย แนว ยอดนิยม",
        "locale_note": "영어와 태국어 쿼리를 병행해야 하며, 로컬 플랫폼 자료는 공개 검색 노출에 영향을 받습니다.",
    },
}


COUNTRY_LOOKUP: dict[str, str] = {
    "미국": "US",
    "usa": "US",
    "us": "US",
    "united states": "US",
    "일본": "JP",
    "japan": "JP",
    "jp": "JP",
    "중국": "CN",
    "china": "CN",
    "cn": "CN",
    "태국": "TH",
    "thailand": "TH",
    "th": "TH",
}


GENRE_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    "romance": {
        "match": ("로맨스", "romance", "현대 로맨스", "romantasy"),
        "queries": (
            "{country_en} webnovel {genre} romance tropes reader preferences 2026",
            "{native_terms} {genre} romance trope trend 2026",
            "{country_en} BookTok Wattpad romance webnovel trend {genre}",
        ),
        "tips": (
            "감정선과 관계 진전 속도를 명확히 설계합니다.",
            "동의(consent), 권력 불균형, 독성 관계의 미화 여부를 점검합니다.",
            "트로프 태그를 제목·소개·마케팅 문구에 일관되게 반영합니다.",
        ),
    },
    "fantasy": {
        "match": ("판타지", "fantasy", "이세계", "isekai", "무협", "xianxia"),
        "queries": (
            "{country_en} webnovel {genre} fantasy tropes reader preferences 2026",
            "{native_terms} fantasy isekai progression trend 2026",
            "{country_en} online fiction fantasy worldbuilding reader expectations",
        ),
        "tips": (
            "초반 3화 안에 세계관 규칙과 주인공 목표를 분명히 제시합니다.",
            "고유명사·계급·마법 체계는 독자가 추적 가능한 방식으로 반복 설명합니다.",
            "장르 클리셰는 유지하되 현지 독자가 피로해하는 설명 과잉을 줄입니다.",
        ),
    },
    "bl": {
        "match": ("bl", "비엘", "boys love", "yaoi"),
        "queries": (
            "{country_en} BL webnovel reader trend 2026",
            "{native_terms} BL boys love online fiction trend",
            "{country_en} LGBTQ romance web fiction reader expectations",
        ),
        "tips": (
            "관계의 권력 구도와 동의 표현을 명확히 처리합니다.",
            "퀴어 정체성을 장식적 장치로만 사용하지 않도록 주의합니다.",
            "플랫폼별 성인물·민감 콘텐츠 규정을 별도로 확인합니다.",
        ),
    },
    "thriller": {
        "match": ("스릴러", "thriller", "미스터리", "mystery", "공포", "horror"),
        "queries": (
            "{country_en} webnovel thriller mystery reader preferences 2026",
            "{native_terms} thriller mystery horror online fiction trend",
            "{country_en} serialized fiction suspense pacing reader expectations",
        ),
        "tips": (
            "챕터 말미의 정보 공개량과 반전을 연재 리듬에 맞춥니다.",
            "현지 금기·범죄 묘사 수위·실제 사건 연상 가능성을 점검합니다.",
            "초반 훅, 단서 회수, 신뢰할 수 없는 화자 장치를 명확히 설계합니다.",
        ),
    },
}


@dataclass(frozen=True)
class ReportRequest:
    country_code: str
    genre: str
    max_results: int = 5
    model: str = "gpt-4.1-mini"


@dataclass(frozen=True)
class SearchTask:
    lane: str
    query: str
    country: str


@dataclass
class Evidence:
    lane: str
    query: str
    title: str
    url: str
    content: str
    score: float = 0.0


@dataclass
class ReportModel:
    request: ReportRequest
    country: dict[str, str]
    generated_at: str
    queries: list[SearchTask]
    evidence: list[Evidence]
    insights: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class EnvAgent:
    """Loads runtime dependencies.

    Tavily is used for evidence collection. OpenAI GPT-4.1 mini is used for
    report synthesis.
    """

    def run(self) -> TavilyClient:
        load_dotenv(ROOT / ".env")
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY가 .env 또는 환경변수에 없습니다.")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        return TavilyClient(api_key=api_key)

    def openai(self) -> OpenAI:
        load_dotenv(ROOT / ".env")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY가 .env 또는 환경변수에 없습니다.")
        return OpenAI(api_key=api_key)


class QueryPlannerAgent:
    """Converts user country/genre into independent Tavily search lanes."""

    def run(self, request: ReportRequest) -> list[SearchTask]:
        country = COUNTRY_ALIASES[request.country_code]
        genre_key = detect_genre_key(request.genre)
        genre_plan = GENRE_HINTS[genre_key]
        base = {
            "country_ko": country["ko"],
            "country_en": country["en"],
            "native_terms": country["native_terms"],
            "genre": request.genre,
        }

        tasks = [
            SearchTask(
                lane="market",
                query=f"{country['market_terms']} {request.genre} trend 2026 localization",
                country=country["tavily"],
            ),
            SearchTask(
                lane="culture",
                query=f"{country['en']} cultural sensitivity localization Korean web novel {request.genre}",
                country=country["tavily"],
            ),
            SearchTask(
                lane="platform",
                query=f"{country['en']} webnovel platform publishing marketing {request.genre} Wattpad Tapas",
                country=country["tavily"],
            ),
        ]
        for query_template in genre_plan["queries"]:
            tasks.append(
                SearchTask(
                    lane="genre",
                    query=query_template.format(**base),
                    country=country["tavily"],
                )
            )
        return tasks


class TavilyResearchAgent:
    """Runs Tavily searches with cache. Each SearchTask is independent."""

    def __init__(self, client: TavilyClient, *, refresh: bool = False):
        self.client = client
        self.refresh = refresh

    def run_one(self, task: SearchTask, max_results: int) -> list[Evidence]:
        payload = {
            "query": task.query,
            "country": task.country,
            "topic": "general",
            "search_depth": "advanced",
            "time_range": "year",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_usage": True,
        }
        response = self._cached_search(payload)
        return [
            Evidence(
                lane=task.lane,
                query=task.query,
                title=(item.get("title") or "").strip(),
                url=(item.get("url") or "").strip(),
                content=(item.get("content") or "").strip(),
                score=float(item.get("score") or 0.0),
            )
            for item in response.get("results", [])
            if item.get("url")
        ]

    def _cached_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = CACHE_DIR / f"{stable_hash(payload)}.json"
        if path.exists() and not self.refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        response = self.client.search(timeout=30, **payload)
        response["_cached_at"] = datetime.now(timezone.utc).isoformat()
        response["_params"] = payload
        path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
        return response


class EvidenceCuratorAgent:
    """Deduplicates and keeps the strongest evidence per URL."""

    def run(self, rows: Iterable[Evidence]) -> list[Evidence]:
        best: dict[str, Evidence] = {}
        for row in rows:
            if not row.url:
                continue
            old = best.get(row.url)
            if old is None or row.score > old.score:
                best[row.url] = row
        return sorted(best.values(), key=lambda item: item.score, reverse=True)


class InsightSynthesizerAgent:
    """Creates conservative Korean report bullets from evidence snippets.

    No external LLM is used. The output is evidence-aware but intentionally
    conservative: it says "public web evidence suggests" rather than claiming
    full-platform statistics.
    """

    def run(self, request: ReportRequest, evidence: list[Evidence]) -> tuple[dict[str, list[str]], list[str], list[str]]:
        genre_key = detect_genre_key(request.genre)
        country = COUNTRY_ALIASES[request.country_code]
        corpus = " ".join([e.title + " " + e.content for e in evidence]).lower()

        insights = {
            "작성 방향": [
                f"{country['ko']} {request.genre} 독자를 겨냥할 때는 공개 웹 근거상 반복 노출되는 장르 키워드와 트로프를 초반 소개·태그·챕터 훅에 명확히 반영하는 편이 안전합니다.",
                "검색 근거가 플랫폼 내부 전체 데이터가 아니므로, 수치 단정 대신 ‘공개 웹에서 관찰되는 경향’으로 표현해야 합니다.",
                *GENRE_HINTS[genre_key]["tips"],
            ],
            "시장/독자 신호": self._market_signals(corpus, request, country),
            "문화 주의사항": self._culture_warnings(corpus, request, country),
            "플랫폼/마케팅": self._platform_signals(corpus, request, country),
        }
        warnings = [
            country["locale_note"],
            "Tavily 검색 결과는 공개 웹 색인 기반이므로 Reddit/YouTube/플랫폼 내부 데이터 전체를 대표하지 않습니다.",
            "PDF/웹사이트에 표시할 때는 주요 판단마다 출처 URL을 함께 남기는 구성이 안전합니다.",
        ]
        recommendations = [
            "출시 전 동일 쿼리를 다시 실행해 최신 결과로 갱신합니다.",
            "상위 근거 URL 중 공식 플랫폼·업계 리포트·작가 가이드 성격의 문서를 우선 인용합니다.",
            "장르별 금기/성인물/저작권/커뮤니티 규정은 플랫폼 업로드 직전에 별도 재확인합니다.",
            "최종 HTML을 브라우저 인쇄 또는 Playwright/WeasyPrint 등으로 PDF 변환합니다.",
        ]
        return insights, warnings, recommendations

    def _market_signals(self, corpus: str, request: ReportRequest, country: dict[str, str]) -> list[str]:
        signals = []
        if has_any(corpus, "booktok", "tiktok"):
            signals.append("BookTok/TikTok 관련 근거가 관찰되어 짧은 훅·트로프 중심 마케팅 문구가 중요합니다.")
        if has_any(corpus, "wattpad"):
            signals.append("Wattpad 관련 결과가 포함되어 태그·장르 분류·연재형 독자 유입을 고려할 수 있습니다.")
        if has_any(corpus, "romance", "romantasy", "enemies to lovers", "slow burn"):
            signals.append("로맨스/로맨타지 트로프가 반복 노출되므로 관계 구도와 감정선 키워드를 전면에 배치합니다.")
        if has_any(corpus, "fantasy", "isekai", "progression", "leveling"):
            signals.append("판타지·성장형 키워드가 보이면 세계관 규칙, 성장 보상, 회차별 목표를 빠르게 제시합니다.")
        if not signals:
            signals.append(f"{country['ko']} {request.genre} 관련 공개 웹 근거를 기반으로 장르 키워드·독자 기대·플랫폼 노출 방식을 보수적으로 추정합니다.")
        return signals

    def _culture_warnings(self, corpus: str, request: ReportRequest, country: dict[str, str]) -> list[str]:
        warnings = [
            "한국식 호칭, 위계, 가족/직장 문화는 직역보다 장면 맥락 안에서 기능을 설명하거나 현지 독자에게 익숙한 관계 표현으로 보완합니다.",
            "현지 독자가 민감하게 받아들일 수 있는 성별 고정관념, 외모 기준, 권력 불균형 로맨스는 미화되지 않게 조정합니다.",
        ]
        if request.country_code == "CN":
            warnings.append("중국 대상 리포트는 검열·정치·종교·폭력·성적 표현의 민감도를 별도 점검 대상으로 둡니다.")
        if request.country_code == "JP":
            warnings.append("일본 대상 리포트는 라노벨/Web小説 문법과 한국식 드라마 문법의 차이를 구분해 설명합니다.")
        if request.country_code == "TH":
            warnings.append("태국 대상 리포트는 BL/로맨스 독자층과 현지 플랫폼 문화를 분리해 확인합니다.")
        if has_any(corpus, "consent", "diversity", "lgbtq"):
            warnings.append("동의, 다양성, 정체성 표현 관련 키워드가 검색 근거에 보이면 문화 검수 체크리스트에 포함합니다.")
        return warnings

    def _platform_signals(self, corpus: str, request: ReportRequest, country: dict[str, str]) -> list[str]:
        platforms = []
        for key, label in [
            ("wattpad", "Wattpad"),
            ("tapas", "Tapas"),
            ("radish", "Radish"),
            ("kindle", "Kindle/Vella"),
            ("kakao", "Kakao 계열"),
            ("naver", "Naver/Webtoon 계열"),
            ("syosetu", "小説家になろう"),
            ("kakuyomu", "カクヨム"),
            ("readawrite", "readAwrite"),
            ("dek-d", "Dek-D"),
        ]:
            if key in corpus:
                platforms.append(label)
        if platforms:
            return [
                f"검색 근거에 노출된 플랫폼/채널: {', '.join(dict.fromkeys(platforms))}.",
                "각 플랫폼의 최신 업로드 규정, 성인물 정책, 태그 체계를 업로드 직전에 별도 확인합니다.",
                "플랫폼명은 추천 채널 후보이지, 해당 플랫폼 내부 데이터 분석 결과로 표현하지 않습니다.",
            ]
        return [
            f"{country['ko']} {request.genre} 리포트에서는 플랫폼별 직접 API 없이 공개 웹 검색 결과에 나타난 채널만 후보로 제시합니다.",
            "플랫폼 추천은 ‘우선 검토 채널’로 표현하고, 최종 업로드 전 정책 재확인을 요구합니다.",
        ]


class GptInsightSynthesizerAgent:
    """Uses GPT-4.1 mini to synthesize localization guidance from Tavily evidence."""

    SECTION_KEYS = ("작성 방향", "시장/독자 신호", "문화 주의사항", "플랫폼/마케팅")

    def __init__(self, client: OpenAI, fallback: InsightSynthesizerAgent | None = None):
        self.client = client
        self.fallback = fallback or InsightSynthesizerAgent()

    def run(self, request: ReportRequest, evidence: list[Evidence]) -> tuple[dict[str, list[str]], list[str], list[str]]:
        country = COUNTRY_ALIASES[request.country_code]
        fallback_insights, fallback_warnings, fallback_recommendations = self.fallback.run(request, evidence)
        evidence_payload = [
            {
                "lane": item.lane,
                "title": item.title,
                "url": item.url,
                "snippet": compact(item.content, 700),
                "score": round(item.score, 4),
            }
            for item in evidence[:18]
        ]
        prompt = {
            "대상_국가": country["ko"],
            "대상_국가_영문": country["en"],
            "웹소설_장르": request.genre,
            "출처_사용_정책": (
                "아래 근거는 Tavily 공개 웹 검색 결과입니다. 플랫폼 내부 통계, 전체 독자 대표값, "
                "공식 랭킹, 전체 시장 점유율처럼 단정하지 마세요. 반드시 근거 URL과 스니펫에서 "
                "확인 가능한 내용만 보수적으로 해석하세요. 근거가 약하면 '근거 부족'이라고 표현하세요."
            ),
            "작성_품질_요구사항": [
                "한국어 웹사이트/PDF 리포트에 바로 들어갈 수 있는 문장으로 작성하세요.",
                "일반론을 피하고 대상 국가와 장르에 맞춘 실행 가능한 조언을 우선하세요.",
                "각 문장은 짧지만 구체적으로 쓰고, '트렌드를 반영하세요' 같은 빈 문장은 피하세요.",
                "Tavily 근거와 무관한 플랫폼명, 수치, 규칙을 새로 지어내지 마세요.",
            ],
            "필수_JSON_형식": {
                "insights": {key: ["한국어 bullet 문자열 3~5개"] for key in self.SECTION_KEYS},
                "warnings": ["한국어 주의사항 문자열 2~4개"],
                "recommendations": ["한국어 실행 체크리스트 문자열 3~5개"],
            },
            "Tavily_근거_목록": evidence_payload,
            "규칙기반_초안_힌트": fallback_insights,
        }
        system = (
            "너는 웹소설 현지화 리서치 에이전트다. "
            "사용자가 입력한 국가와 장르를 기준으로, 제공된 Tavily 공개 웹 근거만 사용해 "
            "한국어 현지화 리포트 문안을 만든다. "
            "근거가 약한 내용은 단정하지 말고, 플랫폼 내부 데이터처럼 과장하지 않는다. "
            "반드시 유효한 JSON 객체만 반환한다. 마크다운, 설명문, 코드블록은 절대 쓰지 않는다."
        )
        response = self.client.responses.create(
            model=request.model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_output_tokens=2400,
        )
        data = parse_json_object(get_response_text(response))
        insights = normalize_insights(data.get("insights"), fallback_insights, self.SECTION_KEYS)
        warnings = normalize_string_list(data.get("warnings"), fallback_warnings)
        recommendations = normalize_string_list(data.get("recommendations"), fallback_recommendations)
        return insights, warnings, recommendations


class HtmlReportRendererAgent:
    """Renders an HTML report close to the provided example's style."""

    def run(self, model: ReportModel, out_path: Path | None = None) -> Path:
        out_path = out_path or default_output_path(model.request)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.render(model), encoding="utf-8-sig")
        return out_path

    def render(self, model: ReportModel) -> str:
        country_ko = model.country["ko"]
        genre = model.request.genre
        title = f"{country_ko} 웹소설 현지화 가이드 — {genre}"
        css = load_example_css() + EXTRA_CSS

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
{css}
</style>
</head>
<body>

<div class="cover">
  <p class="cover-label">Localization Guide · Korean Web Novel → {esc(model.country["en"])} Market</p>
  <h1>{esc(country_ko)} 웹소설<br><em>현지화 가이드</em></h1>
  <div class="cover-sub">
    <span>장르: {esc(genre)}</span>
    <span>근거: Tavily 공개 웹 검색</span>
    <span>합성: {esc(model.request.model)}</span>
    <span>생성: {esc(model.generated_at)}</span>
  </div>
  <div class="cover-deco">♡</div>
</div>

{self._section("01", "작성 방향", self._cards(model.insights.get("작성 방향", []), columns=2))}
{self._section("02", "시장/독자 신호", self._cards(model.insights.get("시장/독자 신호", []), columns=2))}
{self._section("03", "문화 주의사항", self._warning_block(model))}
{self._section("04", "플랫폼 & 마케팅", self._platform_block(model))}
{self._section("05", "Tavily 검색 근거", self._evidence_block(model))}
{self._section("06", "실행 체크리스트", self._checklist(model.recommendations))}

<footer>
  <span>{esc(country_ko)} 웹소설 현지화 가이드 · {esc(genre)}</span>
  <span>Tavily evidence · {esc(model.request.model)} synthesis</span>
</footer>

</body>
</html>
"""

    def _section(self, num: str, title: str, body: str) -> str:
        return f"""
<div class="section">
  <div class="section-header">
    <span class="section-num">{esc(num)}</span>
    <span class="section-title">{esc(title)}</span>
  </div>
  {body}
</div>
"""

    def _cards(self, items: list[str], *, columns: int) -> str:
        grid = "grid-3" if columns == 3 else "grid-2"
        cards = []
        for idx, item in enumerate(items, 1):
            cards.append(
                f"""
    <div class="card">
      <p class="card-title">포인트 {idx}</p>
      <p>{esc(item)}</p>
    </div>"""
            )
        return f'<div class="{grid}">\n' + "\n".join(cards) + "\n  </div>"

    def _warning_block(self, model: ReportModel) -> str:
        warnings = model.insights.get("문화 주의사항", []) + model.warnings
        return f"""
  <div class="alert alert-warn">
    <span class="alert-icon">⚠</span>
    <div>
      <strong>해석 주의</strong><br>
      Tavily 결과는 공개 웹 검색 근거입니다. 플랫폼 전체 통계나 내부 랭킹으로 단정하지 않습니다.
    </div>
  </div>
  {self._checklist(warnings, icon="warn")}
"""

    def _platform_block(self, model: ReportModel) -> str:
        platform_items = model.insights.get("플랫폼/마케팅", [])
        tags = infer_tags(model)
        return f"""
  {self._cards(platform_items, columns=2)}
  <div class="tags">
    {''.join(f'<span class="tag tag-purple">{esc(tag)}</span>' for tag in tags)}
  </div>
"""

    def _evidence_block(self, model: ReportModel) -> str:
        rows = model.evidence[:16]
        if not rows:
            return '<div class="alert alert-danger"><span class="alert-icon">✕</span><div>검색 근거가 없습니다.</div></div>'
        items = []
        for idx, ev in enumerate(rows, 1):
            snippet = compact(ev.content, 260)
            items.append(
                f"""
    <li>
      <strong>{idx}. {esc(ev.title or "Untitled")}</strong>
      <span class="source-meta">lane={esc(ev.lane)} · score={ev.score:.3f}</span>
      <a href="{esc(ev.url)}">{esc(ev.url)}</a>
      <p>{esc(snippet)}</p>
    </li>"""
            )
        query_items = "".join(f"<li><code>{esc(task.query)}</code></li>" for task in model.queries)
        return f"""
  <div class="alert alert-info">
    <span class="alert-icon">ℹ</span>
    <div>아래 근거는 Tavily 검색 결과의 URL/title/snippet 기반입니다. PDF 변환 시에도 출처 URL을 유지하세요.</div>
  </div>
  <p class="card-title">검색 쿼리</p>
  <ul class="query-list">{query_items}</ul>
  <p class="card-title evidence-title">상위 근거</p>
  <ol class="source-list">{''.join(items)}
  </ol>
"""

    def _checklist(self, items: list[str], icon: str = "do") -> str:
        mark = {"do": "✓", "warn": "!"}.get(icon, "✓")
        return '<ul class="check-list wide">\n' + "\n".join(
            f'    <li><span class="icon {icon}">{mark}</span> {esc(item)}</li>' for item in items
        ) + "\n  </ul>"


class LocalizationReportOrchestrator:
    """Coordinates all agents and owns the end-to-end report run."""

    def __init__(self, *, refresh: bool = False):
        env = EnvAgent()
        self.client = env.run()
        self.openai_client = env.openai()
        self.planner = QueryPlannerAgent()
        self.researcher = TavilyResearchAgent(self.client, refresh=refresh)
        self.curator = EvidenceCuratorAgent()
        self.synthesizer = GptInsightSynthesizerAgent(self.openai_client)
        self.renderer = HtmlReportRendererAgent()

    def run(
        self,
        request: ReportRequest,
        *,
        out_path: Path | None = None,
        save_json: bool = False,
    ) -> tuple[ReportModel, Path]:
        queries = self.planner.run(request)
        evidence: list[Evidence] = []
        with ThreadPoolExecutor(max_workers=min(6, len(queries))) as pool:
            future_map = {
                pool.submit(self.researcher.run_one, task, request.max_results): task
                for task in queries
            }
            for future in as_completed(future_map):
                evidence.extend(future.result())

        curated = self.curator.run(evidence)
        insights, warnings, recommendations = self.synthesizer.run(request, curated)
        model = ReportModel(
            request=request,
            country=COUNTRY_ALIASES[request.country_code],
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            queries=queries,
            evidence=curated,
            insights=insights,
            warnings=warnings,
            recommendations=recommendations,
        )
        html_path = self.renderer.run(model, out_path)
        if save_json:
            json_path = html_path.with_suffix(".json")
            json_path.write_text(model_to_json(model), encoding="utf-8")
        return model, html_path


def normalize_country(value: str) -> str:
    key = value.strip().lower()
    if key not in COUNTRY_LOOKUP:
        supported = ", ".join(sorted(set(COUNTRY_LOOKUP)))
        raise ValueError(f"지원하지 않는 국가입니다: {value}. 지원 예: {supported}")
    return COUNTRY_LOOKUP[key]


def detect_genre_key(genre: str) -> str:
    text = genre.lower()
    for key, data in GENRE_HINTS.items():
        if any(token.lower() in text for token in data["match"]):
            return key
    return "romance" if "로맨" in text else "fantasy"


def stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_example_css() -> str:
    if not EXAMPLE_HTML.exists():
        return FALLBACK_CSS
    text = EXAMPLE_HTML.read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", text, flags=re.S | re.I)
    return match.group(1).strip() if match else FALLBACK_CSS


def default_output_path(request: ReportRequest) -> Path:
    country = COUNTRY_ALIASES[request.country_code]["en"].lower().replace(" ", "_")
    genre = slugify(request.genre)
    return REPORT_DIR / f"{country}_{genre}_localization_report.html"


def slugify(value: str) -> str:
    text = re.sub(r"\s+", "_", value.strip().lower())
    text = re.sub(r"[^\w가-힣ぁ-んァ-ン一-龥_+-]+", "", text)
    return text[:60] or "genre"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def compact(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def has_any(text: str, *needles: str) -> bool:
    return any(needle.lower() in text for needle in needles)


def infer_tags(model: ReportModel) -> list[str]:
    corpus = " ".join([e.title + " " + e.content for e in model.evidence]).lower()
    tags = ["Tavily 근거 기반", model.country["ko"], model.request.genre]
    for needle, label in [
        ("booktok", "BookTok"),
        ("wattpad", "Wattpad"),
        ("romance", "Romance"),
        ("fantasy", "Fantasy"),
        ("bl", "BL"),
        ("isekai", "Isekai"),
        ("consent", "Consent"),
        ("diversity", "Diversity"),
    ]:
        if needle in corpus:
            tags.append(label)
    return list(dict.fromkeys(tags))[:10]


def model_to_json(model: ReportModel) -> str:
    return json.dumps(
        {
            **asdict(model),
            "queries": [asdict(task) for task in model.queries],
            "evidence": [asdict(item) for item in model.evidence],
        },
        ensure_ascii=False,
        indent=2,
    )


def get_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                chunks.append(value)
    return "\n".join(chunks)


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_insights(value: Any, fallback: dict[str, list[str]], keys: Iterable[str]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return fallback
    normalized: dict[str, list[str]] = {}
    for key in keys:
        normalized[key] = normalize_string_list(value.get(key), fallback.get(key, []))
    return normalized


def normalize_string_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Tavily + GPT webnovel localization HTML report.")
    parser.add_argument("--country", required=True, help="Target country: 미국/일본/중국/태국 or US/JP/CN/TH")
    parser.add_argument("--genre", required=True, help="Webnovel genre, e.g. 현대 로맨스, 이세계 판타지, BL")
    parser.add_argument("--max-results", type=int, default=5, help="Tavily results per query. Recommended: 3-8.")
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI synthesis model.")
    parser.add_argument("--out", type=Path, default=None, help="Output HTML path. Defaults under raw/localization_reports.")
    parser.add_argument("--save-json", action="store_true", help="Also save raw evidence/model JSON next to HTML.")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache and call Tavily again.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.max_results <= 20:
        raise ValueError("--max-results는 1~20 사이여야 합니다.")
    request = ReportRequest(
        country_code=normalize_country(args.country),
        genre=args.genre,
        max_results=args.max_results,
        model=args.model,
    )
    model, html_path = LocalizationReportOrchestrator(refresh=args.refresh).run(
        request,
        out_path=args.out,
        save_json=args.save_json,
    )
    print(f"HTML report: {html_path}")
    if args.save_json:
        print(f"JSON evidence: {html_path.with_suffix('.json')}")
    print(f"queries: {len(model.queries)}")
    print(f"evidence: {len(model.evidence)}")


FALLBACK_CSS = """
body { font-family: system-ui, sans-serif; color: #1C1B18; background: #FAFAF8; line-height: 1.7; padding: 48px 32px; max-width: 820px; margin: 0 auto; }
.cover, .section, .card { border: 1px solid #E2E0DA; padding: 24px; margin-bottom: 24px; background: white; }
.section-header { display: flex; gap: 12px; margin-bottom: 16px; font-weight: 700; }
.section-num { color: #5B4FCF; }
.grid-2, .grid-3 { display: grid; gap: 16px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.check-list { list-style: none; padding: 0; }
.check-list li { margin-bottom: 8px; }
.icon { display: inline-block; width: 20px; color: #0F8A6A; }
.alert { padding: 16px; margin-bottom: 16px; background: #EBE9FB; display: flex; gap: 12px; }
"""


EXTRA_CSS = """

  .query-list, .source-list { margin: 10px 0 22px 18px; color: var(--text); }
  .query-list li, .source-list li { margin-bottom: 12px; }
  .source-list a { display: block; color: var(--purple); word-break: break-all; font-size: 12px; margin: 4px 0; }
  .source-list p { color: var(--text-muted); font-size: 13px; line-height: 1.6; }
  .source-meta { display: block; color: var(--text-light); font-size: 11px; margin-top: 2px; }
  .evidence-title { margin-top: 18px; }
  .wide li { margin-bottom: 10px; }
  @media print {
    body { padding: 24px; background: #fff; }
    .section { break-inside: avoid; }
    a { color: #1C1B18; text-decoration: none; }
  }
"""


if __name__ == "__main__":
    main()
