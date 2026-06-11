from __future__ import annotations

import re
from html import unescape
from typing import Any

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"


def normalize_space(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", unescape(value)).strip()


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    m = re.search(r"[\d,]+", str(value))
    if not m:
        return None
    return int(m.group(0).replace(",", ""))


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json",
        }
    )
    return session


def request_text(url: str, *, session: requests.Session) -> str:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.encoding or response.apparent_encoding
    return response.text


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metrics.items() if value is not None}


def unique_labels(*groups: Any) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for group in groups:
        values = group if isinstance(group, list) else [group]
        for value in values:
            text = normalize_space(str(value)) if value is not None else ""
            if text and text.lower() not in seen:
                seen.add(text.lower())
                labels.append(text)
    return labels


