from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def _api_params_for(target: MarketTrendTarget) -> dict[str, str] | None:
    if target.signal_type != "power_ranking":
        return None
    return {
        "rankId": "power_rank",
        "listType": "2",
        "type": "1",
        "rankName": "Power",
        "timeType": "3",
        "sourceType": "2",
        "sex": "1",
        "signStatus": "1",
    }


def _labels_from_api_item(item: dict) -> list[str]:
    labels = []
    for key in ["categoryName", "categoryNameEn", "genre", "subGenre"]:
        if item.get(key):
            labels.append(item[key])
    for tag in item.get("tagInfo") or []:
        if isinstance(tag, dict):
            labels.append(tag.get("tagName") or tag.get("enTagName") or tag.get("name"))
        else:
            labels.append(tag)
    return unique_labels(labels)


def _collect_api(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    params_base = _api_params_for(target)
    if not params_base:
        return []
    session.headers.update({"Referer": target.url, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/javascript, */*; q=0.01"})
    session.get(target.url, timeout=30)
    csrf = session.cookies.get("_csrfToken")
    if not csrf:
        return []
    records: list[MarketRawRecord] = []
    page = 1
    while len(records) < target.limit:
        params = {"pageIndex": str(page), **params_base, "_csrfToken": csrf}
        response = session.get("https://www.webnovel.com/go/pcm/category/getRankList", params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            break
        data = payload.get("data") or {}
        items = data.get("bookItems") or []
        if not items:
            break
        for item in items:
            title = normalize_space(item.get("bookName"))
            if not title:
                continue
            records.append(
                MarketRawRecord(
                    market=target.market,
                    language_market=target.language_market,
                    raw_language=target.raw_language,
                    platform=target.platform,
                    signal_type=target.signal_type,
                    rank=int(item.get("rankNo") or len(records) + 1),
                    title=title,
                    labels=_labels_from_api_item(item),
                    synopsis=normalize_space(item.get("description")),
                    public_metrics=compact_metrics(
                        {
                            "ranking_score": item.get("rankScore") or item.get("score"),
                            "power": item.get("power"),
                            "collections": item.get("collections"),
                            "views": item.get("views"),
                        }
                    ),
                )
            )
            if len(records) >= target.limit:
                return records
        if data.get("last"):
            break
        page += 1
    return records


def _collect_html_fallback(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    soup = BeautifulSoup(request_text(target.url, session=session), "html.parser")
    records: list[MarketRawRecord] = []
    text = soup.get_text("\n")
    chunks = re.split(r"\n\s*0*(\d{1,3})\s*\n", text)
    for idx in range(1, len(chunks), 2):
        if len(records) >= target.limit:
            break
        rank = parse_int(chunks[idx]) or len(records) + 1
        body = chunks[idx + 1]
        lines = [normalize_space(x) for x in body.splitlines() if normalize_space(x)]
        labels = [line.lstrip("# ") for line in lines if line.startswith("#")]
        title = ""
        for line in lines:
            if line.startswith("#") or line.lower() in {"add in library", "read"}:
                continue
            if len(line) > 2:
                title = line
                break
        if not title:
            continue
        synopsis_parts = [line for line in lines if line != title and not line.startswith("#")][:6]
        score_match = re.search(r"\n\s*([\d,]+)\|", body)
        records.append(
            MarketRawRecord(
                market=target.market,
                language_market=target.language_market,
                raw_language=target.raw_language,
                platform=target.platform,
                signal_type=target.signal_type,
                rank=rank,
                title=title,
                labels=unique_labels(labels),
                synopsis=normalize_space(" ".join(synopsis_parts)),
                public_metrics=compact_metrics({"ranking_score": parse_int(score_match.group(1)) if score_match else None}),
            )
        )
    if records:
        return records

    for item in soup.select(".j_book, .book-item, li"):
        title_node = item.select_one("h3, h2, a[href*='/book/']")
        if not title_node:
            continue
        labels = [normalize_space(x.get_text(" ")).lstrip("#") for x in item.select("a[href*='/tags/'], a[href*='/stories/']")]
        synopsis = normalize_space((item.select_one("p") or item).get_text(" "))
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
                synopsis=synopsis,
                public_metrics={},
            )
        )
        if len(records) >= target.limit:
            break
    return records


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    api_rows = _collect_api(target, session=session)
    if api_rows:
        return api_rows
    return _collect_html_fallback(target, session=session)
