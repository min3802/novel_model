from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from scripts.platform_trends.common import compact_metrics, normalize_space, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget

_REMIX_RE = re.compile(r"window\.__remixContext\s*=\s*(\{.*?\});</script>", re.S)


def _story_records(stories: list[dict[str, Any]], target: MarketTrendTarget, start_rank: int) -> list[MarketRawRecord]:
    rows: list[MarketRawRecord] = []
    for offset, story in enumerate(stories):
        rankings = story.get("rankings") or []
        ranking_labels = []
        if isinstance(rankings, list):
            for ranking in rankings[:5]:
                if isinstance(ranking, dict):
                    tag = ranking.get("tag") or ranking.get("name")
                    rank = ranking.get("rank")
                    if tag and rank:
                        ranking_labels.append(f"#{rank} in {tag}")
        rows.append(
            MarketRawRecord(
                market=target.market,
                language_market=target.language_market,
                raw_language=target.raw_language,
                platform=target.platform,
                signal_type=target.signal_type,
                rank=start_rank + offset,
                title=normalize_space(story.get("title")),
                labels=unique_labels(story.get("tags") or [], ranking_labels, "completed" if story.get("completed") else "ongoing", "mature" if story.get("mature") else None),
                synopsis=normalize_space(story.get("description")),
                public_metrics=compact_metrics(
                    {
                        "reads": story.get("readCount"),
                        "votes": story.get("voteCount"),
                        "parts": story.get("numParts"),
                        "category": story.get("category"),
                    }
                ),
            )
        )
    return rows


def _extract_initial(text: str) -> tuple[list[dict[str, Any]], str | None]:
    match = _REMIX_RE.search(text)
    if not match:
        return [], None
    data = json.loads(match.group(1))
    loader = ((data.get("state") or {}).get("loaderData") or {}).get("filter") or {}
    items = (((loader.get("storiesForFilterType") or {}).get("data") or {}).get("items") or {})
    stories = items.get("stories") or []
    return stories, items.get("nextUrl")


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    text = request_text(target.url, session=session)
    stories, next_url = _extract_initial(text)
    records = _story_records(stories, target, 1)
    while next_url and len(records) < target.limit:
        time.sleep(0.25)
        response = session.get(next_url, headers={"Accept": "application/json", "Referer": target.url}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        page_stories = payload.get("stories") or []
        if not page_stories:
            break
        records.extend(_story_records(page_stories, target, len(records) + 1))
        next_url = payload.get("nextUrl")
    return records[: target.limit]
