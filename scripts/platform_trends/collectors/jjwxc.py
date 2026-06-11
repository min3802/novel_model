from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def _rank_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.select('a[href^="/book2/"]'):
        title = normalize_space(a.get_text(" "))
        href = a.get("href") or ""
        if not title or href in seen:
            continue
        seen.add(href)
        links.append((title, urljoin(base_url, href)))
    return links


def _between(text: str, start: str, end_options: list[str]) -> str:
    idx = text.find(start)
    if idx < 0:
        return ""
    idx += len(start)
    ends = [text.find(end, idx) for end in end_options if text.find(end, idx) >= 0]
    end = min(ends) if ends else min(len(text), idx + 1000)
    return normalize_space(text[idx:end])


def _detail(url: str, *, session: requests.Session, target: MarketTrendTarget, rank: int, fallback_title: str) -> MarketRawRecord | None:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = "gb18030"
    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    title = fallback_title
    title_match = re.search(r"《(.+?)》", soup.title.get_text(" ", strip=True) if soup.title else "")
    if title_match:
        title = normalize_space(title_match.group(1))
    type_line = _between(text, "类型：", ["标签：", "主角：", "一句话简介："])
    tags_text = _between(text, "标签：", ["主角：", "配角：", "一句话简介："])
    intro_short = _between(text, "一句话简介：", ["立意：", "状态：", "简介："])
    synopsis = _between(text, "简介：", ["收藏", "霸王票", "章节列表："])
    labels = unique_labels(type_line.split("-") if type_line else [], tags_text.split() if tags_text else [])
    metrics = compact_metrics(
        {
            "favorites": parse_int(re.search(r"收藏\s*\(\s*([\d,]+)\s*\)", text).group(1)) if re.search(r"收藏\s*\(\s*([\d,]+)\s*\)", text) else None,
            "comments": parse_int(re.search(r"看书评\s*\(\s*([\d,]+)\s*\)", text).group(1)) if re.search(r"看书评\s*\(\s*([\d,]+)\s*\)", text) else None,
            "words": parse_int(re.search(r"状态：.*?([\d,]+)字", text, re.S).group(1)) if re.search(r"状态：.*?([\d,]+)字", text, re.S) else None,
        }
    )
    return MarketRawRecord(
        market=target.market,
        language_market=target.language_market,
        raw_language=target.raw_language,
        platform=target.platform,
        signal_type=target.signal_type,
        rank=rank,
        title=title,
        labels=labels,
        synopsis=normalize_space(f"{intro_short} {synopsis}"),
        public_metrics=metrics,
    )


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    response = session.get(target.url, timeout=30)
    response.raise_for_status()
    response.encoding = "gb18030"
    links = _rank_links(response.text, target.url)
    records: list[MarketRawRecord] = []
    for rank, (title, url) in enumerate(links[: target.limit], start=1):
        try:
            row = _detail(url, session=session, target=target, rank=rank, fallback_title=title)
        except Exception:
            row = MarketRawRecord(target.market, target.language_market, target.raw_language, target.platform, target.signal_type, rank, title, [], "", {})
        if row:
            records.append(row)
        time.sleep(0.08)
    return records
