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
        url = target.url if page == 1 else f"{target.url}?page={page}"
        if page > 1:
            time.sleep(0.3)
        soup = BeautifulSoup(request_text(url, session=session), "html.parser")
        items = soup.select(".fiction-list-item")
        if not items:
            break
        for item in items:
            title_link = item.select_one("h2.fiction-title a[href]") or item.select_one('a[href^="/fiction/"]')
            if not title_link:
                continue
            rank = len(records) + 1
            labels = [normalize_space(x.get_text(" ")) for x in item.select(".label.bg-blue-hoki")]
            tags = [normalize_space(x.get_text(" ")) for x in item.select("a.fiction-tag")]
            stats_text = " ".join(normalize_space(x.get_text(" ")) for x in item.select(".stats span"))
            rating_node = item.select_one('[aria-label^="Rating:"]')
            rating = None
            if rating_node and rating_node.get("aria-label"):
                rating_match = re.search(r"Rating:\s*([\d.]+)", rating_node["aria-label"])
                rating = float(rating_match.group(1)) if rating_match else None
            description_root = item.select_one('[id^="description-"]') or item
            description_node = description_root.select_one("p")
            records.append(
                MarketRawRecord(
                    market=target.market,
                    language_market=target.language_market,
                    raw_language=target.raw_language,
                    platform=target.platform,
                    signal_type=target.signal_type,
                    rank=rank,
                    title=normalize_space(title_link.get_text(" ")),
                    labels=unique_labels(labels, tags),
                    synopsis=normalize_space(description_node.get_text(" ") if description_node else ""),
                    public_metrics=compact_metrics(
                        {
                            "followers": parse_int(re.search(r"([\d,]+) Followers", stats_text).group(1)) if re.search(r"([\d,]+) Followers", stats_text) else None,
                            "pages": parse_int(re.search(r"([\d,]+) Pages", stats_text).group(1)) if re.search(r"([\d,]+) Pages", stats_text) else None,
                            "views": parse_int(re.search(r"([\d,]+) Views", stats_text).group(1)) if re.search(r"([\d,]+) Views", stats_text) else None,
                            "chapters": parse_int(re.search(r"([\d,]+) Chapters", stats_text).group(1)) if re.search(r"([\d,]+) Chapters", stats_text) else None,
                            "rating": rating,
                        }
                    ),
                )
            )
            if len(records) >= target.limit:
                return records
        page += 1
    return records
