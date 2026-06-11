from __future__ import annotations

import json
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def _page_url(target: MarketTrendTarget, page: int) -> str:
    if page <= 1:
        return target.url
    separator = "&" if "?" in target.url else "?"
    return f"{target.url}{separator}page={page}"


def _decode_embedded_json(value: str) -> Any:
    return json.loads(value.encode("utf-8").decode("unicode_escape"))


def _readawrite_cache_urls(html: str) -> list[tuple[str, str]]:
    match = re.search(r"cache_popular_new:\s*'(.*?)',\s*\n\s*translate_list", html, re.S)
    if not match:
        return []
    groups = _decode_embedded_json(match.group(1))
    urls: list[tuple[str, str]] = []
    for group in groups:
        group_name = normalize_space(group.get("category_group_name"))
        for article_group in group.get("list_article") or []:
            cache_path = article_group.get("cache_path")
            if cache_path:
                urls.append((group_name, cache_path.replace("\\/", "/")))
    return urls


def _collect_readawrite_cache(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    html = request_text(target.url, session=session)
    records: list[MarketRawRecord] = []
    seen_titles: set[str] = set()
    for group_name, cache_url in _readawrite_cache_urls(html):
        response = session.get(cache_url, timeout=30, headers={"Accept": "application/json"})
        response.raise_for_status()
        categories = response.json()
        for category in categories if isinstance(categories, list) else []:
            category_name = normalize_space(category.get("category_name") or category.get("category_name_2"))
            for article in category.get("article_list") or []:
                title = normalize_space(article.get("article_name"))
                if not title or title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())
                tags = [normalize_space(tag.get("tag_name")) for tag in article.get("tag_list") or [] if tag.get("tag_name")]
                records.append(
                    MarketRawRecord(
                        market=target.market,
                        language_market=target.language_market,
                        raw_language=target.raw_language,
                        platform=target.platform,
                        signal_type=target.signal_type,
                        rank=len(records) + 1,
                        title=title,
                        labels=unique_labels(group_name, category_name, tags),
                        synopsis=normalize_space(article.get("article_synopsis")),
                        public_metrics=compact_metrics(
                            {
                                "views": article.get("view_count"),
                                "comments": article.get("comment_count"),
                                "rating_count": article.get("rating_count"),
                                "chapters": article.get("chapter_count"),
                            }
                        ),
                    )
                )
                if len(records) >= target.limit:
                    return records
    return records


def _collect_generic_cards(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    records: list[MarketRawRecord] = []
    seen_titles: set[str] = set()
    page = 1
    while len(records) < target.limit:
        if page > 1:
            time.sleep(0.25)
        soup = BeautifulSoup(request_text(_page_url(target, page), session=session), "html.parser")
        before = len(records)
        selectors = "article, .book, .novel, .story, .ranking-item, .card"
        for item in soup.select(selectors):
            title_node = None
            for candidate in item.select("h1, h2, h3, .title, a[href]"):
                if normalize_space(candidate.get_text(" ")):
                    title_node = candidate
                    break
            if not title_node:
                continue
            labels = [normalize_space(x.get_text(" ")) for x in item.select(".category, .tag, .genre, a[href*='category'], a[href*='tag']")]
            synopsis_node = item.select_one(".description, .synopsis, p")
            text = normalize_space(item.get_text(" "))
            title = normalize_space(title_node.get_text(" "))
            if len(title) < 2 or title.lower() in seen_titles:
                continue
            seen_titles.add(title.lower())
            records.append(
                MarketRawRecord(
                    market=target.market,
                    language_market=target.language_market,
                    raw_language=target.raw_language,
                    platform=target.platform,
                    signal_type=target.signal_type,
                    rank=len(records) + 1,
                    title=title,
                    labels=unique_labels(labels),
                    synopsis=normalize_space(synopsis_node.get_text(" ") if synopsis_node else ""),
                    public_metrics=compact_metrics(
                        {
                            "views": parse_int(re.search(r"([\d,.]+[kKmM]?)\s*(?:views|reads|\u0e27\u0e34\u0e27)", text, re.I).group(1)) if re.search(r"([\d,.]+[kKmM]?)\s*(?:views|reads|\u0e27\u0e34\u0e27)", text, re.I) else None,
                            "likes": parse_int(re.search(r"([\d,.]+[kKmM]?)\s*(?:likes|\u0e16\u0e39\u0e01\u0e43\u0e08)", text, re.I).group(1)) if re.search(r"([\d,.]+[kKmM]?)\s*(?:likes|\u0e16\u0e39\u0e01\u0e43\u0e08)", text, re.I) else None,
                        }
                    ),
                )
            )
            if len(records) >= target.limit:
                return records
        if len(records) == before:
            break
        page += 1
    return records


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    if target.platform == "ReadAWrite":
        rows = _collect_readawrite_cache(target, session=session)
        if rows:
            return rows
    return _collect_generic_cards(target, session=session)
