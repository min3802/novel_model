from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platform_trends.analysis import build_rag, build_summary, legacy_dataset
from scripts.platform_trends.common import make_session
from scripts.platform_trends.io import RAG_PATH, SUMMARY_PATH, OUT_DIR, load_raw_payloads, write_json, write_raw
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget
from scripts.platform_trends.targets import TARGETS

COLLECTOR_MODULES = {
    "Wattpad": "scripts.platform_trends.collectors.wattpad",
    "Tapas": "scripts.platform_trends.collectors.tapas",
    "Royal Road": "scripts.platform_trends.collectors.royalroad",
    "Scribble Hub": "scripts.platform_trends.collectors.scribblehub",
    "WebNovel": "scripts.platform_trends.collectors.webnovel",
    "Syosetu": "scripts.platform_trends.collectors.syosetu",
    "Kakuyomu": "scripts.platform_trends.collectors.kakuyomu",
    "Alphapolis": "scripts.platform_trends.collectors.alphapolis",
    "Honeyfeed": "scripts.platform_trends.collectors.honeyfeed",
    "ReadAWrite": "scripts.platform_trends.collectors.readawrite",
    "JJWXC": "scripts.platform_trends.collectors.jjwxc",
    "Zongheng": "scripts.platform_trends.collectors.zongheng",
    "Dek-D": "scripts.platform_trends.collectors.dekd",
    "Joylada": "scripts.platform_trends.collectors.joylada",
    "Fictionlog": "scripts.platform_trends.collectors.fictionlog",
}


def collect_target(target: MarketTrendTarget) -> list[MarketRawRecord]:
    module_name = COLLECTOR_MODULES[target.platform]
    module = importlib.import_module(module_name)
    session = make_session()
    return module.collect(target, session=session)


def collect_targets(targets: list[MarketTrendTarget]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for target in targets:
        try:
            rows = collect_target(target)
            error = None
        except Exception as exc:  # keep other platform signals collectible
            rows = []
            error = f"{type(exc).__name__}: {exc}"
        path = write_raw(target, rows)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if error:
            payload["collection_error"] = error
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"wrote {path} (0 records, error: {error})")
        else:
            print(f"wrote {path} ({len(rows)} records)")
        payloads.append(payload)
    return payloads


def build_outputs(raw_payloads: list[dict[str, Any]], *, legacy_output: Path | None = None) -> dict[str, Any]:
    summary = build_summary(raw_payloads)
    rag = build_rag(summary)
    write_json(SUMMARY_PATH, summary)
    write_json(RAG_PATH, rag)
    if legacy_output:
        write_json(legacy_output, legacy_dataset(raw_payloads, summary, rag))
    return {"summary": summary, "rag": rag}


def selected_targets(keys: list[str] | None) -> list[MarketTrendTarget]:
    if not keys:
        return TARGETS
    wanted = set(keys)
    return [target for target in TARGETS if target.key in wanted or target.platform in wanted or target.output_group in wanted]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect and summarize market-observation platform trend signals.")
    parser.add_argument("--target", action="append", dest="targets", help="Target key/platform/group. Repeatable. Defaults to all targets.")
    parser.add_argument("--from-raw", action="store_true", help="Skip network collection and rebuild summary/RAG from raw files.")
    parser.add_argument("--legacy-output", type=Path, default=OUT_DIR / "platform_trends_current.json", help="Compatibility dataset path for existing guide code.")
    args = parser.parse_args()

    if args.from_raw:
        raw_payloads = load_raw_payloads()
    else:
        collect_targets(selected_targets(args.targets))
        raw_payloads = load_raw_payloads()
    outputs = build_outputs(raw_payloads, legacy_output=args.legacy_output)
    print(json.dumps({"summary_path": str(SUMMARY_PATH), "rag_path": str(RAG_PATH), "summary_count": len(outputs["summary"].get("summaries") or [])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


