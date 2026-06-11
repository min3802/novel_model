from __future__ import annotations

import time
from typing import Any

import requests

from scripts.platform_trends.common import compact_metrics, normalize_space, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def _api_url(page: int, size: int) -> str:
    return (
        "https://story-api.tapas.io/cosmos/api/v1/landing/ranking"
        f"?category_type=NOVEL&subtab_id=24&page={page}&size={size}"
    )


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    records: list[MarketRawRecord] = []
    page = 0
    page_size = min(25, target.limit)
    headers = {"Referer": target.url, "Accept": "application/json"}
    while len(records) < target.limit:
        if page:
            time.sleep(0.25)
        response = session.get(_api_url(page, page_size), headers=headers, timeout=30)
        response.raise_for_status()
        items = (response.json().get("data") or {}).get("items") or []
        if not items:
            break
        for item in items:
            rank = len(records) + 1
            main_genre = (item.get("mainGenre") or {}).get("value")
            genres = [g.get("value") for g in item.get("genreList") or [] if g.get("value")]
            service = item.get("serviceProperty") or {}
            records.append(
                MarketRawRecord(
                    market=target.market,
                    language_market=target.language_market,
                    raw_language=target.raw_language,
                    platform=target.platform,
                    signal_type=target.signal_type,
                    rank=rank,
                    title=normalize_space(item.get("title")),
                    labels=unique_labels(main_genre, genres, item.get("issueStatus"), item.get("bmType")),
                    synopsis=normalize_space(item.get("description")),
                    public_metrics=compact_metrics(
                        {
                            "views": service.get("viewCount"),
                            "subscribers": service.get("subscriberCount"),
                            "likes": service.get("likeCount"),
                            "platform_rank": service.get("rank") or rank,
                        }
                    ),
                )
            )
            if len(records) >= target.limit:
                break
        page += 1
    return records
