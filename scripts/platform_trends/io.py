from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget, coerce_record

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "localization_guide" / "platform_observation"
RAW_DIR = OUT_DIR / "raw"
ANALYSIS_DIR = OUT_DIR / "analysis"
RAG_DIR = OUT_DIR / "rag"
SUMMARY_PATH = ANALYSIS_DIR / "market_observation_summary.json"
RAG_PATH = RAG_DIR / "market_observation_rag.json"


def raw_path(target: MarketTrendTarget) -> Path:
    return RAW_DIR / target.output_group / f"{target.key}.json"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_raw(target: MarketTrendTarget, rows: Iterable[MarketRawRecord | dict[str, Any]]) -> Path:
    path = raw_path(target)
    payload = {
        "market": target.market,
        "language_market": target.language_market,
        "raw_language": target.raw_language,
        "platform": target.platform,
        "signal_type": target.signal_type,
        "target_limit": target.limit,
        "records": [coerce_record(row) for row in rows],
    }
    write_json(path, payload)
    return path


def iter_raw_files() -> list[Path]:
    if not RAW_DIR.exists():
        return []
    return sorted(RAW_DIR.glob("*/*.json"))


def load_raw_payloads(paths: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    return [read_json(path) for path in (paths or iter_raw_files())]
