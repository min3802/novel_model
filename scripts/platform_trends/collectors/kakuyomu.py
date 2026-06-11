from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def _split_title(value: str) -> str:
    return normalize_space(value.split("\uff0f", 1)[0])


def _metric_text(card) -> str:
    return normalize_space(" ".join(node.get_text(" ", strip=True) for node in card.select(".widget-workCard-meta, .widget-workCard-stat, .widget-workCard-reviewPoints, .widget-workCard-rating")))


def _match_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)
    return parse_int(match.group(1)) if match else None


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    html = request_text(target.url, session=session)
    soup = BeautifulSoup(html, "html.parser")
    records: list[MarketRawRecord] = []
    for title_node in soup.select(".widget-workCard-title"):
        card = title_node.find_parent(class_=re.compile("widget-workCard")) or title_node.find_parent("div")
        if not card:
            continue
        rank = len(records) + 1
        labels = [node.get_text(" ", strip=True) for node in card.select(".widget-workCard-tags a, .widget-workCard-genre, a[href*='/genres/']")]
        synopsis = ""
        synopsis_node = card.select_one(".widget-workCard-introduction, .widget-workCard-description, .widget-workCard-lead")
        if synopsis_node:
            synopsis = normalize_space(synopsis_node.get_text(" ", strip=True))
        text = _metric_text(card)
        records.append(
            MarketRawRecord(
                market=target.market,
                language_market=target.language_market,
                raw_language=target.raw_language,
                platform=target.platform,
                signal_type=target.signal_type,
                rank=rank,
                title=_split_title(title_node.get_text(" ", strip=True)),
                labels=unique_labels(labels),
                synopsis=synopsis,
                public_metrics=compact_metrics(
                    {
                        "stars": _match_int(r"\u2605\s*([\d,]+)", text),
                        "comments": _match_int(r"\u30b3\u30e1\u30f3\u30c8\s*([\d,]+)", text),
                        "platform_rank": rank,
                    }
                ),
            )
        )
        if len(records) >= target.limit:
            break
    return records
