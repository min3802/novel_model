from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def _metric(card, selector: str) -> int | None:
    node = card.select_one(selector)
    return parse_int(node.get_text(" ", strip=True)) if node else None


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    html = request_text(target.url, session=session)
    soup = BeautifulSoup(html, "html.parser")
    records: list[MarketRawRecord] = []
    for card in soup.select("section.p-content.is-novel"):
        title_node = card.select_one(".p-content__title a, .p-content__title")
        if not title_node:
            continue
        labels = [node.get_text(" ", strip=True) for node in card.select(".c-attribute-tag, .c-tag")]
        synopsis_node = card.select_one(".p-content__abstract")
        rank_node = card.select_one(".p-content__rank")
        rank = parse_int(rank_node.get_text(" ", strip=True)) if rank_node else len(records) + 1
        records.append(
            MarketRawRecord(
                market=target.market,
                language_market=target.language_market,
                raw_language=target.raw_language,
                platform=target.platform,
                signal_type=target.signal_type,
                rank=rank or len(records) + 1,
                title=normalize_space(title_node.get_text(" ", strip=True)),
                labels=unique_labels(labels),
                synopsis=normalize_space(synopsis_node.get_text(" ", strip=True) if synopsis_node else ""),
                public_metrics=compact_metrics(
                    {
                        "points_24h": _metric(card, ".c-point"),
                        "comments": _metric(card, ".p-content__attribute-comment"),
                        "characters": _metric(card, ".p-content__attribute-unit"),
                        "platform_rank": rank or len(records) + 1,
                    }
                ),
            )
        )
        if len(records) >= target.limit:
            break
    return records
