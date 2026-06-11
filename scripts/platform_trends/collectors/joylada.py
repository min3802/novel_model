from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget

_STORY_RE = re.compile(r"(?:^|\s)([\d,]{3,})\s+(.+)$")


def _request_soup(url: str, *, session: requests.Session) -> BeautifulSoup:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    # Joylada declares UTF-8; forcing it avoids mojibake when apparent_encoding guesses incorrectly.
    response.encoding = "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def _page_url(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page > 1:
        query["page"] = str(page)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _parse_story_text(text: str) -> tuple[int | None, str]:
    text = normalize_space(text)
    # Homepage text can be "1 33,786,425 title"; list pages can be "?? 33,786,425 title".
    parts = text.split(" ", 1)
    if parts and parts[0].isdigit() and len(parts) > 1:
        text = parts[1]
    match = _STORY_RE.search(text)
    if not match:
        return None, text
    return parse_int(match.group(1)), normalize_space(match.group(2))


def _heading(box, fallback: str) -> str:
    # The visible heading is not reliably marked up; .morelabel often means "view all".
    # Use stable box labels instead of accidentally storing navigation text as a market label.
    return fallback


def _append_story(records: list[MarketRawRecord], target: MarketTrendTarget, *, title: str, reads: int | None, label: str, category_rank: int | None, box_index: int, seen: set[str], href: str) -> None:
    key = href or title
    if not title or key in seen:
        return
    seen.add(key)
    records.append(
        MarketRawRecord(
            market=target.market,
            language_market=target.language_market,
            raw_language=target.raw_language,
            platform=target.platform,
            signal_type=target.signal_type,
            rank=len(records) + 1,
            title=title,
            labels=unique_labels(label),
            synopsis="",
            public_metrics=compact_metrics({"reads_or_views": reads, "category_rank": category_rank, "ranking_box": box_index}),
        )
    )


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    soup = _request_soup(target.url, session=session)
    records: list[MarketRawRecord] = []
    seen: set[str] = set()

    category_links: list[tuple[str, str, int]] = []
    for box_index, box in enumerate(soup.select(".ranking-box"), start=1):
        label = _heading(box, f"joylada_ranking_box_{box_index}")
        more = next((a for a in box.select("a[href]") if a.get("href") and not re.match(r"^/story/[0-9a-f]", a.get("href", ""))), None)
        if more and more.get("href"):
            category_links.append((urljoin(target.url, more["href"]), label, box_index))
        for link in [a for a in box.select("a[href^='/story/']") if re.match(r"^/story/[0-9a-f]", a.get("href", ""))]:
            reads, title = _parse_story_text(link.get_text(" ", strip=True))
            category_rank = parse_int(link.get_text(" ", strip=True).split(" ", 1)[0])
            _append_story(records, target, title=title, reads=reads, label=label, category_rank=category_rank, box_index=box_index, seen=seen, href=link.get("href") or "")
            if len(records) >= target.limit:
                return records

    for base_url, label, box_index in category_links:
        category_rank = 0
        for page in range(1, 20):
            page_soup = _request_soup(_page_url(base_url, page), session=session)
            links = [a for a in page_soup.select("a[href^='/story/']") if re.match(r"^/story/[0-9a-f]", a.get("href", ""))]
            if not links:
                break
            before = len(records)
            for link in links:
                reads, title = _parse_story_text(link.get_text(" ", strip=True))
                category_rank += 1
                _append_story(records, target, title=title, reads=reads, label=label, category_rank=category_rank, box_index=box_index, seen=seen, href=link.get("href") or "")
                if len(records) >= target.limit:
                    return records
            if len(records) == before:
                break
    return records
