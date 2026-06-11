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
        url = target.url if page == 1 else f"{target.url}?p={page}"
        if page > 1:
            time.sleep(0.3)
        soup = BeautifulSoup(request_text(url, session=session), "html.parser")
        items = soup.select(".p-ranklist-item")
        if not items:
            break
        for item in items:
            rank_node = item.select_one(".c-rank-place__num") or item.select_one(".p-ranklist-item__place")
            title_link = item.select_one(".p-ranklist-item__title a[href]")
            if not title_link:
                continue
            info = normalize_space((item.select_one(".p-ranklist-item__infomation") or item).get_text(" "))
            genre_match = re.search(r"\d+[\d,]*\u6587\u5b57\s+(.+?)\s+\u6700\u7d42\u66f4\u65b0\u65e5", info)
            keyword_node = item.select_one(".p-ranklist-item__keyword")
            keywords = normalize_space(keyword_node.get_text(" ")).split() if keyword_node else []
            status_match = re.search(r"(\u9023\u8f09\u4e2d|\u5b8c\u7d50\u6e08)\(\u5168(\d+)\u30a8\u30d4\u30bd\u30fc\u30c9\)", info)
            chars_match = re.search(r"([\d,]+)\u6587\u5b57", info)
            metric_name = "monthly_points" if target.signal_type == "monthly_ranking" else "weekly_points"
            records.append(
                MarketRawRecord(
                    market=target.market,
                    language_market=target.language_market,
                    raw_language=target.raw_language,
                    platform=target.platform,
                    signal_type=target.signal_type,
                    rank=parse_int(rank_node.get_text(" ") if rank_node else None) or len(records) + 1,
                    title=normalize_space(title_link.get_text(" ")),
                    labels=unique_labels(normalize_space(genre_match.group(1)) if genre_match else None, keywords),
                    synopsis=normalize_space((item.select_one(".p-ranklist-item__synopsis") or item).get_text(" ")),
                    public_metrics=compact_metrics(
                        {
                            metric_name: parse_int((item.select_one(".p-ranklist-item__points") or item).get_text(" ")),
                            "episodes": int(status_match.group(2)) if status_match else None,
                            "characters": parse_int(chars_match.group(1)) if chars_match else None,
                        }
                    ),
                )
            )
            if len(records) >= target.limit:
                return records
        page += 1
    return records
