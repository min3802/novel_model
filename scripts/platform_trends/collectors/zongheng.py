from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from scripts.platform_trends.common import compact_metrics, normalize_space, parse_int, request_text, unique_labels
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


def _rank_links(html: str) -> list[tuple[str, str, int | None]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str, int | None]] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/detail/"]'):
        title = normalize_space(a.get_text(" "))
        href = a.get("href") or ""
        if not title or href in seen or len(title) < 2:
            continue
        seen.add(href)
        links.append((title, urljoin("https://www.zongheng.com", href), None))
    return links


def _detail(url: str, *, session: requests.Session, target: MarketTrendTarget, rank: int, fallback_title: str) -> MarketRawRecord:
    soup = BeautifulSoup(request_text(url, session=session), "html.parser")
    text = soup.get_text("\n", strip=True)
    title = fallback_title
    title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
    if "(" in title_text:
        title = normalize_space(title_text.split("(", 1)[0])
    labels: list[str] = []
    for item in ["玄幻奇幻", "都市娱乐", "武侠仙侠", "历史军事", "科幻游戏", "悬疑灵异", "现代言情", "古代言情", "东方玄幻", "传统玄幻", "热血", "剑道", "爽文", "少年", "家族崛起"]:
        if item in text:
            labels.append(item)
    metrics = compact_metrics(
        {
            "total_clicks_wan": float(re.search(r"([\d.]+)\s*万总点击", text).group(1)) if re.search(r"([\d.]+)\s*万总点击", text) else None,
            "total_recommend_wan": float(re.search(r"([\d.]+)\s*万总推荐", text).group(1)) if re.search(r"([\d.]+)\s*万总推荐", text) else None,
            "weekly_recommend": parse_int(re.search(r"([\d,]+)\s*周推荐", text).group(1)) if re.search(r"([\d,]+)\s*周推荐", text) else None,
            "words_wan": float(re.search(r"([\d.]+)\s*万字数", text).group(1)) if re.search(r"([\d.]+)\s*万字数", text) else None,
        }
    )
    return MarketRawRecord(target.market, target.language_market, target.raw_language, target.platform, target.signal_type, rank, title, unique_labels(labels), "", metrics)


def collect(target: MarketTrendTarget, *, session: requests.Session) -> list[MarketRawRecord]:
    html = request_text(target.url, session=session)
    links = _rank_links(html)
    records: list[MarketRawRecord] = []
    for rank, (title, url, _) in enumerate(links[: target.limit], start=1):
        try:
            records.append(_detail(url, session=session, target=target, rank=rank, fallback_title=title))
        except Exception:
            records.append(MarketRawRecord(target.market, target.language_market, target.raw_language, target.platform, target.signal_type, rank, title, [], "", {}))
        time.sleep(0.05)
    return records
