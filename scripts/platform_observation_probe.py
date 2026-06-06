from __future__ import annotations

import json
import re
import sys
import urllib.request
from html import unescape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "localization_guide" / "platform_observation"


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 platform-observation-poc/0.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", "ignore")


def textify(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def probe_tapas() -> dict:
    url = "https://tapas.io/collection/novels"
    html = fetch(url)
    sort_match = re.search(r"pandaWeb\.browseSlim\(\{(?P<body>.*?)\}\);", html, flags=re.S)
    sort_blob = sort_match.group("body") if sort_match else ""
    genre_counts = {}
    for genre in re.findall(r"Novel\s*•\s*([A-Za-z+/ ]+?)\s+(?:RF|BL|AF|GL|Drama|Romance|LGBTQ\+|Thrller/Hrr)", textify(html)):
        genre = genre.strip()
        if genre:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
    return {
        "platform": "Tapas",
        "url": url,
        "http_accessible": True,
        "html_bytes": len(html),
        "observed_total_results": int(re.search(r"(\d+)\s+results", html).group(1)) if re.search(r"(\d+)\s+results", html) else None,
        "observed_sort": re.search(r"sort:\s*'([^']+)'", sort_blob).group(1) if re.search(r"sort:\s*'([^']+)'", sort_blob) else None,
        "has_sort_ui": "hasSortBy: false" not in sort_blob,
        "has_filter_ui": "hasFilterBy: false" not in sort_blob,
        "observable_fields": ["genre/category labels", "collection result count", "series links via browser-rendered/ajax data"],
        "missing_without_js_api": ["title", "views", "likes", "tags"],
        "genre_counts_from_static_html": genre_counts,
        "ranking_confidence": "low",
        "collection_claim": "Static HTML exposes a collection with 129 results and server-selected SUBSCRIBE sort; it should not be treated as view ranking.",
    }


def probe_royalroad() -> dict:
    url = "https://www.royalroad.com/fictions/best-rated"
    html = fetch(url)
    text = textify(html)
    title_links = re.findall(
        r'href="(/fiction/\d+/[^"]+)"[^>]*>\s*<h2[^>]*>(.*?)</h2>',
        html,
        flags=re.I | re.S,
    )
    if not title_links:
        title_links = [
            (path, title)
            for path, title in re.findall(
                r'href="(/fiction/\d+/[^"]+)"[^>]*>(.*?)</a>',
                html,
                flags=re.I | re.S,
            )
            if len(textify(title)) > 2
        ]
    stats = {
        "followers_mentions": len(re.findall(r"\bFollowers\b", text)),
        "views_mentions": len(re.findall(r"\bViews\b", text)),
        "chapters_mentions": len(re.findall(r"\bChapters\b", text)),
    }
    return {
        "platform": "Royal Road",
        "url": url,
        "http_accessible": True,
        "html_bytes": len(html),
        "page_type": "Best Rated",
        "sample_titles": [textify(t).strip()[:120] for _, t in title_links[:5]],
        "sample_urls": [f"https://www.royalroad.com{p}" for p, _ in title_links[:5]],
        "observable_fields": ["ranked listing page type", "title", "origin/status", "tags", "followers", "pages", "views", "chapters", "updated date", "description"],
        "stats_mentions": stats,
        "ranking_confidence": "high",
        "collection_claim": "Direct listing exposes a named ranking page and per-work stats in static HTML.",
    }


def probe_wattpad() -> dict:
    url = "https://www.wattpad.com/stories/romance"
    try:
        html = fetch(url)
        text = textify(html)
        return {
            "platform": "Wattpad",
            "url": url,
            "http_accessible": True,
            "html_bytes": len(html),
            "observable_fields": ["category landing text"] if "wattpad" in text.lower() else [],
            "missing_without_js_api": ["reliable title/rank/stats extraction"],
            "ranking_confidence": "low",
            "collection_claim": "Direct static extraction is not reliable enough for model-grade ranking/tag evidence without an approved API/search layer.",
        }
    except Exception as exc:
        return {
            "platform": "Wattpad",
            "url": url,
            "http_accessible": False,
            "error": str(exc),
            "observable_fields": [],
            "ranking_confidence": "low",
            "collection_claim": "Direct crawl failed in this environment.",
        }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "generated_at": "2026-06-04",
        "purpose": "POC for localization guide platform ranking/genre/tag observation data collection.",
        "probes": [probe_tapas(), probe_royalroad(), probe_wattpad()],
        "decision": {
            "usable_now": ["Royal Road static ranking pages", "Tapas collection genre/category observation"],
            "needs_extra_work": ["Tapas browser-rendered/ajax item details", "Wattpad via search/API/manual sampling"],
            "not_safe_to_claim": ["Tapas Popular equals view ranking", "Wattpad category page equals official ranking"],
        },
    }
    out = OUT_DIR / "platform_observation_poc.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(result["decision"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
