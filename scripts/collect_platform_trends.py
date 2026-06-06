
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "localization_guide" / "platform_observation"
DEFAULT_LIMIT = 100
USER_AGENT = "Mozilla/5.0 platform-trend-collector/0.1 (+localization-guide research)"


@dataclass(frozen=True)
class PlatformTarget:
    country: str
    platform: str
    collection: str
    url: str
    ranking_basis: str


ROYALROAD_TRENDING = PlatformTarget(
    country="US/global English",
    platform="Royal Road",
    collection="Trending",
    url="https://www.royalroad.com/fictions/trending",
    ranking_basis="platform_trending_order",
)
ROYALROAD_WEEKLY = PlatformTarget(
    country="US/global English",
    platform="Royal Road",
    collection="Popular this week",
    url="https://www.royalroad.com/fictions/weekly-popular",
    ranking_basis="platform_weekly_popular_order",
)
TAPAS_POPULAR_NOVELS = PlatformTarget(
    country="US/global English",
    platform="Tapas",
    collection="Novels popular menu subtab 24",
    url="https://tapas.io/menu/3/subtab/24",
    ranking_basis="platform_popular_novel_order",
)
SYOSSETU_WEEKLY = PlatformTarget(
    country="Japan",
    platform="Shosetsuka ni Naro / Yomou",
    collection="Weekly ranking",
    url="https://yomou.syosetu.com/rank/list/type/weekly_r/",
    ranking_basis="weekly_ranking_order",
)


def normalize_space(value: str | None) -> str:
    if not value:
        return ""
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"[\d,]+", value)
    if not m:
        return None
    return int(m.group(0).replace(",", ""))


def request_text(url: str, *, session: requests.Session, sleep_seconds: float = 0.0) -> str:
    if sleep_seconds:
        time.sleep(sleep_seconds)
    response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.encoding or response.apparent_encoding
    return response.text


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json",
        }
    )
    return session


def base_record(target: PlatformTarget, rank: int, source_url: str) -> dict[str, Any]:
    return {
        "country": target.country,
        "platform": target.platform,
        "collection": target.collection,
        "ranking_basis": target.ranking_basis,
        "rank": rank,
        "source_url": source_url,
    }


def collect_royalroad(target: PlatformTarget, *, limit: int, session: requests.Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    while len(records) < limit:
        url = target.url if page == 1 else f"{target.url}?page={page}"
        soup = BeautifulSoup(request_text(url, session=session, sleep_seconds=0.3 if page > 1 else 0), "html.parser")
        items = soup.select(".fiction-list-item")
        if not items:
            break
        for item in items:
            rank = len(records) + 1
            title_link = item.select_one("h2.fiction-title a[href]") or item.select_one('a[href^="/fiction/"]')
            if not title_link:
                continue
            labels = [normalize_space(x.get_text(" ")) for x in item.select(".label.bg-blue-hoki")]
            tags = [normalize_space(x.get_text(" ")) for x in item.select("a.fiction-tag")]
            stats_text = " ".join(normalize_space(x.get_text(" ")) for x in item.select(".stats span"))
            rating_node = item.select_one('[aria-label^="Rating:"]')
            rating = None
            if rating_node and rating_node.get("aria-label"):
                rating_match = re.search(r"Rating:\s*([\d.]+)", rating_node["aria-label"])
                rating = float(rating_match.group(1)) if rating_match else None
            time_node = item.select_one("time")
            description = normalize_space(
                (item.select_one('[id^="description-"]') or item).select_one("p").get_text(" ")
                if (item.select_one('[id^="description-"]') or item).select_one("p")
                else ""
            )
            record = base_record(target, rank, urljoin("https://www.royalroad.com", title_link["href"]))
            record.update(
                {
                    "title": normalize_space(title_link.get_text(" ")),
                    "authors": [],
                    "genre": labels[0] if labels else None,
                    "genres": labels[:1],
                    "status": labels[1] if len(labels) > 1 else None,
                    "tags": tags,
                    "synopsis": description,
                    "public_metrics": {
                        "followers": parse_int(re.search(r"([\d,]+) Followers", stats_text).group(1)) if re.search(r"([\d,]+) Followers", stats_text) else None,
                        "pages": parse_int(re.search(r"([\d,]+) Pages", stats_text).group(1)) if re.search(r"([\d,]+) Pages", stats_text) else None,
                        "views": parse_int(re.search(r"([\d,]+) Views", stats_text).group(1)) if re.search(r"([\d,]+) Views", stats_text) else None,
                        "chapters": parse_int(re.search(r"([\d,]+) Chapters", stats_text).group(1)) if re.search(r"([\d,]+) Chapters", stats_text) else None,
                        "rating": rating,
                    },
                    "updated_at_platform": time_node.get("datetime") if time_node else None,
                }
            )
            records.append(record)
            if len(records) >= limit:
                return records
        page += 1
    return records


def tapas_api_url(page: int, size: int) -> str:
    return (
        "https://story-api.tapas.io/cosmos/api/v1/landing/ranking"
        f"?category_type=NOVEL&subtab_id=24&page={page}&size={size}"
    )


def collect_tapas(target: PlatformTarget, *, limit: int, session: requests.Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 0
    page_size = min(25, limit)
    headers = {"Referer": target.url}
    while len(records) < limit:
        url = tapas_api_url(page, page_size)
        if page:
            time.sleep(0.3)
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json().get("data", {})
        items = data.get("items") or []
        if not items:
            break
        for item in items:
            rank = len(records) + 1
            service = item.get("serviceProperty") or {}
            main_genre = item.get("mainGenre") or {}
            genres = [g.get("value") for g in item.get("genreList") or [] if g.get("value")]
            series_id = item.get("seriesId")
            record = base_record(target, rank, f"https://tapas.io/series/{series_id}")
            record.update(
                {
                    "platform_item_id": series_id,
                    "title": item.get("title"),
                    "authors": item.get("authorList") or [],
                    "publisher": item.get("publisher"),
                    "genre": main_genre.get("value"),
                    "genres": genres,
                    "status": item.get("issueStatus"),
                    "tags": [],
                    "synopsis": normalize_space(item.get("description")),
                    "bm_type": item.get("bmType"),
                    "language_code": item.get("languageCode"),
                    "public_metrics": {
                        "views": service.get("viewCount"),
                        "subscribers": service.get("subscriberCount"),
                        "likes": service.get("likeCount"),
                        "platform_rank": service.get("rank"),
                    },
                    "updated_at_platform": item.get("lastEpisodeAddedDt") or item.get("updatedDt"),
                    "source_api_url": url,
                }
            )
            records.append(record)
            if len(records) >= limit:
                return records
        page += 1
    return records


def collect_syosetu(target: PlatformTarget, *, limit: int, session: requests.Session) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    while len(records) < limit:
        url = target.url if page == 1 else f"{target.url}?p={page}"
        soup = BeautifulSoup(request_text(url, session=session, sleep_seconds=0.3 if page > 1 else 0), "html.parser")
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
            tags = normalize_space(keyword_node.get_text(" ")).split() if keyword_node else []
            points = parse_int((item.select_one(".p-ranklist-item__points") or item).get_text(" "))
            author = normalize_space((item.select_one(".p-ranklist-item__author") or item).get_text(" "))
            status_match = re.search(r"(\u9023\u8f09\u4e2d|\u5b8c\u7d50\u6e08)\(\u5168(\d+)\u30a8\u30d4\u30bd\u30fc\u30c9\)", info)
            chars_match = re.search(r"([\d,]+)\u6587\u5b57", info)
            updated_match = re.search(r"\u6700\u7d42\u66f4\u65b0\u65e5\uff1a([\d/]+\s+[\d:]+)", info)
            record = base_record(target, parse_int(rank_node.get_text(" ")) or len(records) + 1, urljoin("https://ncode.syosetu.com", title_link["href"]))
            record.update(
                {
                    "title": normalize_space(title_link.get_text(" ")),
                    "authors": [author] if author else [],
                    "genre": normalize_space(genre_match.group(1)) if genre_match else None,
                    "genres": [normalize_space(genre_match.group(1))] if genre_match else [],
                    "status": status_match.group(1) if status_match else None,
                    "tags": tags,
                    "synopsis": normalize_space((item.select_one(".p-ranklist-item__synopsis") or item).get_text(" ")),
                    "public_metrics": {
                        "weekly_points": points,
                        "episodes": int(status_match.group(2)) if status_match else None,
                        "characters": parse_int(chars_match.group(1)) if chars_match else None,
                    },
                    "updated_at_platform": updated_match.group(1) if updated_match else None,
                }
            )
            records.append(record)
            if len(records) >= limit:
                return records
        page += 1
    return records


def summarize(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    genre_counter = Counter()
    tag_counter = Counter()
    status_counter = Counter()
    for row in rows:
        for genre in row.get("genres") or ([row.get("genre")] if row.get("genre") else []):
            if genre:
                genre_counter[genre] += 1
        for tag in row.get("tags") or []:
            if tag:
                tag_counter[tag] += 1
        if row.get("status"):
            status_counter[row["status"]] += 1
    return {
        "item_count": len(rows),
        "top_genres": genre_counter.most_common(20),
        "top_tags": tag_counter.most_common(30),
        "status_counts": status_counter.most_common(),
        "top_titles": [row.get("title") for row in rows[:10]],
    }


def build_rag_documents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs = []
    for row in records:
        title = row.get("title") or ""
        genres = ", ".join(row.get("genres") or [])
        tags = ", ".join((row.get("tags") or [])[:20])
        metrics = row.get("public_metrics") or {}
        metric_text = ", ".join(f"{k}: {v}" for k, v in metrics.items() if v is not None)
        embedding_text = normalize_space(
            f"{row.get('country')} {row.get('platform')} {row.get('collection')} rank {row.get('rank')} "
            f"{title} genre {genres} tags {tags} synopsis {row.get('synopsis') or ''}"
        )
        context_text = normalize_space(
            f"[{row.get('country')} / {row.get('platform')} / {row.get('collection')}] "
            f"Rank {row.get('rank')}: {title}. Genre: {genres or 'unknown'}. "
            f"Tags: {tags or 'none observed'}. Public metrics: {metric_text or 'not exposed'}. "
            f"Synopsis: {row.get('synopsis') or 'not exposed'}."
        )
        docs.append(
            {
                "id": f"platform-trend::{row.get('platform')}::{row.get('collection')}::{row.get('rank')}",
                "embedding_text": embedding_text,
                "context_text": context_text,
                "metadata": {
                    "country": row.get("country"),
                    "platform": row.get("platform"),
                    "collection": row.get("collection"),
                    "ranking_basis": row.get("ranking_basis"),
                    "rank": row.get("rank"),
                    "title": title,
                    "genre": row.get("genre"),
                    "genres": row.get("genres") or [],
                    "tags": row.get("tags") or [],
                    "source_url": row.get("source_url"),
                },
            }
        )
    return docs


def collect_all(limit: int) -> dict[str, Any]:
    session = make_session()
    target_records = {
        "royalroad_trending": collect_royalroad(ROYALROAD_TRENDING, limit=limit, session=session),
        "royalroad_weekly_popular": collect_royalroad(ROYALROAD_WEEKLY, limit=limit, session=session),
        "tapas_popular_novels": collect_tapas(TAPAS_POPULAR_NOVELS, limit=limit, session=session),
        "syosetu_weekly": collect_syosetu(SYOSSETU_WEEKLY, limit=limit, session=session),
    }
    all_records = [row for records in target_records.values() for row in records]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Current platform trend observation for localization guide generation; excludes story body text and stores public listing/detail metadata only.",
        "collection_policy": {
            "target_items_per_collection": limit,
            "include": ["rank/exposure order", "title", "author", "genre", "tags", "public metrics", "public synopsis/description", "status/update metadata"],
            "exclude": ["episode/story body text", "paid/locked content", "login-only data", "cover image downloads"],
        },
        "sources": [ROYALROAD_TRENDING.__dict__, ROYALROAD_WEEKLY.__dict__, TAPAS_POPULAR_NOVELS.__dict__, SYOSSETU_WEEKLY.__dict__],
        "collections": target_records,
        "summary_by_collection": {name: summarize(records) for name, records in target_records.items()},
        "summary_all": summarize(all_records),
        "rag_documents": build_rag_documents(all_records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect public platform trend metadata for localization guide analysis.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="items per collection")
    parser.add_argument("--output", type=Path, default=OUT_DIR / "platform_trends_current.json")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = collect_all(args.limit)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    print(json.dumps({"summary_by_collection": result["summary_by_collection"], "summary_all": result["summary_all"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
