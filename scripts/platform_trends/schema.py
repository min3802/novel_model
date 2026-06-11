from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MarketTrendTarget:
    market: str
    language_market: str
    raw_language: str
    platform: str
    signal_type: str
    url: str
    limit: int
    output_group: str

    @property
    def key(self) -> str:
        platform_key = self.platform.lower().replace(" ", "_").replace("/", "_")
        return f"{platform_key}_{self.signal_type}"


@dataclass
class MarketRawRecord:
    market: str
    language_market: str
    raw_language: str
    platform: str
    signal_type: str
    rank: int
    title: str
    labels: list[str] = field(default_factory=list)
    synopsis: str = ""
    public_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coerce_record(row: MarketRawRecord | dict[str, Any]) -> dict[str, Any]:
    if isinstance(row, MarketRawRecord):
        return row.to_dict()
    return dict(row)


def _legacy_country(value: str | None) -> str:
    if value == "US":
        return "US/global English"
    return value or "unknown"


def legacy_row(record: MarketRawRecord | dict[str, Any]) -> dict[str, Any]:
    """Return a compatibility row for older guide/advisor code.

    The new collector intentionally avoids URL/author/status fields. Older code
    expects country/collection/ranking_basis/genres/tags; map them from the
    market-observation schema without reintroducing provenance-heavy fields.
    """
    row = coerce_record(record)
    labels = [str(x) for x in row.get("labels") or [] if x]
    return {
        "country": _legacy_country(row.get("market")),
        "language_market": row.get("language_market"),
        "raw_language": row.get("raw_language"),
        "platform": row.get("platform") or "unknown",
        "collection": row.get("signal_type") or "unknown",
        "ranking_basis": row.get("signal_type") or "unknown",
        "rank": row.get("rank") or 0,
        "title": row.get("title") or "",
        "genre": labels[0] if labels else None,
        "genres": labels,
        "tags": labels,
        "synopsis": row.get("synopsis") or "",
        "public_metrics": row.get("public_metrics") or {},
    }
