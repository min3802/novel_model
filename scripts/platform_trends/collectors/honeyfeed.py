from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    soup = BeautifulSoup(request_text(target.url, session=session), "html.parser")
    records: list[MarketRawRecord] = []
    selectors = ".novel-card, .series-card, .ranking-list-item, article, .book-item"
    for item in soup.select(selectors):
        title_node = item.select_one("h1, h2, h3, .title, a[href*='/novels/']")
        if not title_node:
            continue
        labels = [normalize_space(x.get_text(" ")) for x in item.select(".genre, .tag, a[href*='/genres/'], a[href*='/tags/']")]
        synopsis_node = item.select_one(".description, .synopsis, p")
        text = normalize_space(item.get_text(" "))
        records.append(
            MarketRawRecord(
                market=target.market,
                language_market=target.language_market,
                raw_language=target.raw_language,
                platform=target.platform,
                signal_type=target.signal_type,
                rank=len(records) + 1,
                title=normalize_space(title_node.get_text(" ")),
                labels=unique_labels(labels),
                synopsis=normalize_space(synopsis_node.get_text(" ") if synopsis_node else ""),
                public_metrics=compact_metrics(
                    {
                        "views": parse_int(re.search(r"([\d,]+)\s*views", text, re.I).group(1)) if re.search(r"([\d,]+)\s*views", text, re.I) else None,
                        "likes": parse_int(re.search(r"([\d,]+)\s*likes", text, re.I).group(1)) if re.search(r"([\d,]+)\s*likes", text, re.I) else None,
                    }
                ),
            )
        )
        if len(records) >= target.limit:
            return records

    # Plain-text fallback for ranking pages rendered without stable card classes.
    text = soup.get_text("\n")
    chunks = re.split(r"\n\s*#?\d{1,3}\s*\n", text)
    for chunk in chunks[1:]:
        lines = [normalize_space(x) for x in chunk.splitlines() if normalize_space(x)]
        if not lines:
            continue
        records.append(
            MarketRawRecord(
                market=target.market,
                language_market=target.language_market,
                raw_language=target.raw_language,
                platform=target.platform,
                signal_type=target.signal_type,
                rank=len(records) + 1,
                title=lines[0],
                labels=[],
                synopsis=" ".join(lines[1:6]),
                public_metrics={},
            )
        )
        if len(records) >= target.limit:
            break
    return records
