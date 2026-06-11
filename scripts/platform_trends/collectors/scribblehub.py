from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    records: list[MarketRawRecord] = []
    page = 1
    while len(records) < target.limit:
        separator = "&" if "?" in target.url else "?"
        url = target.url if page == 1 else f"{target.url}{separator}page={page}"
        if page > 1:
            time.sleep(0.3)
        soup = BeautifulSoup(request_text(url, session=session), "html.parser")
        items = soup.select(".search_main_box, .fic_item, .series_ranking, .listupd > div")
        if not items:
            text = soup.get_text("\n")
            # Search-index HTML often flattens ranking rows; keep a conservative parser.
            chunks = re.split(r"\n\s*#?\d{1,3}\s*", text)
            items = []
            for chunk in chunks[1:]:
                if len(records) >= target.limit:
                    break
                lines = [normalize_space(x) for x in chunk.splitlines() if normalize_space(x)]
                if not lines:
                    continue
                title = lines[0]
                records.append(
                    MarketRawRecord(
                        market=target.market,
                        language_market=target.language_market,
                        raw_language=target.raw_language,
                        platform=target.platform,
                        signal_type=target.signal_type,
                        rank=len(records) + 1,
                        title=title,
                        labels=[],
                        synopsis=" ".join(lines[1:6]),
                        public_metrics={},
                    )
                )
            break
        for item in items:
            title_node = item.select_one(".search_title a, .fic_title a, h3 a, h2 a, a[href*='/series/']")
            if not title_node:
                continue
            labels = [normalize_space(x.get_text(" ")) for x in item.select(".wi_fic_genre a, .genre, a[href*='/genre/'], a[href*='/tags/']")]
            text = normalize_space(item.get_text(" "))
            synopsis_node = item.select_one(".search_body_summery, .fic_desc, .description, p")
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
                            "views": parse_int(re.search(r"([\d,.]+[kKmM]?)\s*Views", text).group(1)) if re.search(r"([\d,.]+[kKmM]?)\s*Views", text) else None,
                            "favorites": parse_int(re.search(r"([\d,]+)\s*Favorites", text).group(1)) if re.search(r"([\d,]+)\s*Favorites", text) else None,
                            "readers": parse_int(re.search(r"([\d,]+)\s*Readers", text).group(1)) if re.search(r"([\d,]+)\s*Readers", text) else None,
                            "chapters": parse_int(re.search(r"([\d,]+)\s*Chapters", text).group(1)) if re.search(r"([\d,]+)\s*Chapters", text) else None,
                        }
                    ),
                )
            )
            if len(records) >= target.limit:
                return records
        page += 1
    return records
