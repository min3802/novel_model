from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from scripts.platform_trends.schema import legacy_row

FORBIDDEN_USE = [
    "개별 작품 추천 금지",
    "개별 작품 시놉시스 재사용 금지",
    "인기작과의 유사도 비교 금지",
    "창작 방향 직접 제시 금지",
]

STOPWORDS = {
    "with", "from", "that", "this", "their", "there", "into", "only", "have", "after", "before",
    "when", "where", "what", "will", "been", "being", "they", "them", "than", "then", "story",
    "novel", "series", "world", "must", "life", "find", "more", "about", "would", "could", "should",
}

MOTIF_PATTERNS: dict[str, list[str]] = {
    "성장/레벨업/시스템": ["system", "level", "skill", "rank", "quest", "litrpg", "progression", "스킬", "레벨", "システム", "スキル"],
    "이세계/전생/빙의": ["isekai", "reincarn", "transmigr", "another world", "portal", "전생", "빙의", "회귀", "異世界", "転生", "転移"],
    "로맨스/관계 중심": ["romance", "love", "marriage", "duke", "prince", "villainess", "contract", "연애", "결혼", "公爵", "婚約", "恋愛"],
    "액션/생존/전쟁": ["battle", "war", "fight", "survival", "apocalypse", "dungeon", "전투", "전쟁", "생존", "ダンジョン"],
    "무협/수련/동양 판타지": ["cultivation", "martial", "wuxia", "xianxia", "dao", "qi", "무협", "수련"],
}


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in payload.get("records") or []]


def _counter(records: Iterable[dict[str, Any]], field: str, *, limit: int = 30) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in records:
        values = row.get(field)
        if isinstance(values, list):
            for value in values:
                if value:
                    counter[str(value)] += 1
        elif values:
            counter[str(values)] += 1
    return [{"label": label, "count": count} for label, count in counter.most_common(limit)]


def _metric_coverage(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    coverage: Counter[str] = Counter()
    for row in records:
        for key, value in (row.get("public_metrics") or {}).items():
            if value is not None:
                coverage[key] += 1
    return dict(coverage.most_common())


def _motif_distribution(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in records:
        text = " ".join([row.get("title") or "", row.get("synopsis") or "", " ".join(row.get("labels") or [])]).lower()
        for motif, needles in MOTIF_PATTERNS.items():
            if any(needle.lower() in text for needle in needles):
                counter[motif] += 1
    return [{"motif": motif, "count": count} for motif, count in counter.most_common()]


def _synopsis_terms(records: Iterable[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in records:
        text = " ".join([row.get("title") or "", row.get("synopsis") or ""])
        for token in re.findall(r"[A-Za-z][A-Za-z'-]{3,}|[가-힣]{2,}|[一-龥ぁ-んァ-ンー]{2,}|[\u0E00-\u0E7F]{2,}", text.lower()):
            token = token.strip("'-")
            if token and token not in STOPWORDS:
                counter[token] += 1
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    records = _records(payload)
    first = records[0] if records else payload
    sample_size = len(records)
    target_limit = int(payload.get("target_limit") or sample_size or 0)
    if payload.get("collection_error"):
        collection_status = "error"
    elif sample_size == 0:
        collection_status = "empty"
    elif target_limit and sample_size < target_limit:
        collection_status = "partial"
    else:
        collection_status = "ok"
    return {
        "market": payload.get("market") or first.get("market") or "unknown",
        "language_market": payload.get("language_market") or first.get("language_market") or "unknown",
        "raw_language": payload.get("raw_language") or first.get("raw_language") or "unknown",
        "analysis_language": "ko",
        "platform": payload.get("platform") or first.get("platform") or "unknown",
        "signal_type": payload.get("signal_type") or first.get("signal_type") or "unknown",
        "sample_size": sample_size,
        "target_limit": target_limit,
        "collection_status": collection_status,
        "collection_error": payload.get("collection_error"),
        "top_labels": _counter(records, "labels", limit=30),
        "motif_distribution": _motif_distribution(records),
        "metric_coverage": _metric_coverage(records),
        "synopsis_terms": _synopsis_terms(records),
        "market_observations": [
            f"{sample_size}건의 공개 목록 표본에서 라벨·시놉시스·공개 지표만 집계함.",
            "개별 작품명/시놉시스는 RAG 입력으로 직접 사용하지 않고 시장 신호 요약에만 사용함.",
        ],
        "analysis_scope": "market_observation_only",
    }


def build_summary(raw_payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    summaries = [summarize_payload(payload) for payload in raw_payloads]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_language": "ko",
        "analysis_scope": "market_observation_only",
        "forbidden_use": FORBIDDEN_USE,
        "summaries": summaries,
    }


def build_rag(summary: dict[str, Any]) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    for item in summary.get("summaries") or []:
        if int(item.get("sample_size") or 0) <= 0:
            continue
        top_labels = ", ".join(f"{x['label']}({x['count']})" for x in item.get("top_labels", [])[:12])
        motifs = ", ".join(f"{x['motif']}({x['count']})" for x in item.get("motif_distribution", [])[:8])
        terms = ", ".join(f"{x['term']}({x['count']})" for x in item.get("synopsis_terms", [])[:12])
        text = (
            f"시장 관측 요약: {item.get('market')} / {item.get('language_market')} / "
            f"{item.get('platform')} / {item.get('signal_type')}. "
            f"표본 {item.get('sample_size')}건. 상위 라벨: {top_labels or '없음'}. "
            f"추상 모티프: {motifs or '없음'}. 반복 표현 신호: {terms or '없음'}. "
            "용도는 현지화 시장 관측이며 개별 작품 추천, 유사작 비교, 창작 방향 직접 제시는 금지."
        )
        documents.append(
            {
                "id": f"market-signal::{item.get('platform')}::{item.get('signal_type')}",
                "embedding_text": text,
                "context_text": text,
                "metadata": {
                    "market": item.get("market"),
                    "language_market": item.get("language_market"),
                    "raw_language": item.get("raw_language"),
                    "platform": item.get("platform"),
                    "signal_type": item.get("signal_type"),
                    "sample_size": item.get("sample_size"),
                    "analysis_scope": item.get("analysis_scope"),
                },
            }
        )
    return {"generated_at": summary.get("generated_at"), "documents": documents, "forbidden_use": summary.get("forbidden_use") or FORBIDDEN_USE}


def legacy_dataset(raw_payloads: Iterable[dict[str, Any]], summary: dict[str, Any], rag: dict[str, Any]) -> dict[str, Any]:
    collections: dict[str, list[dict[str, Any]]] = {}
    sources: list[dict[str, Any]] = []
    for payload in raw_payloads:
        key = f"{payload.get('platform', 'unknown').lower().replace(' ', '_')}_{payload.get('signal_type', 'unknown')}"
        rows = [legacy_row(row) for row in payload.get("records") or []]
        collections[key] = rows
        sources.append({k: payload.get(k) for k in ["market", "language_market", "raw_language", "platform", "signal_type", "target_limit"]})
    return {
        "generated_at": summary.get("generated_at"),
        "purpose": "Market observation for localization guide generation; RAG should use aggregate summaries rather than individual works.",
        "collection_policy": {
            "include": ["rank", "title", "labels/genres", "public metrics", "public synopsis/description"],
            "exclude": ["authors", "source URLs", "episode/story body text", "paid/locked content", "login-only data", "images"],
        },
        "sources": sources,
        "collections": collections,
        "market_observation_summary": summary,
        "rag_documents": rag.get("documents") or [],
    }

