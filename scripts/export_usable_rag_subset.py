from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from normalize_rag_references import DEFAULT_INPUTS, ROOT, normalize_files


DEFAULT_OUTPUT = ROOT / "data" / "legacy_idiom_rag" / "usable_candidates"


def is_usable(row: dict, *, min_confidence: float) -> bool:
    return (
        row.get("review_status") == "legacy_import"
        and float(row.get("confidence") or 0) >= min_confidence
        and not row.get("quality_flags")
    )


def write_grouped(rows: list[dict], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["locale"]].append(row)

    for locale, locale_rows in sorted(grouped.items()):
        path = output_dir / f"{locale}_usable_references.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(locale_rows, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"wrote {path.relative_to(ROOT)} rows={len(locale_rows)}")


def write_report(all_rows: list[dict], usable_rows: list[dict], output_dir: Path, *, min_confidence: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_by_status = Counter(row.get("review_status", "") for row in all_rows)
    usable_by_locale = Counter(row.get("locale", "") for row in usable_rows)
    blocked_flags = Counter()
    for row in all_rows:
        for flag in row.get("quality_flags") or []:
            blocked_flags[flag] += 1

    report = {
        "min_confidence": min_confidence,
        "total_normalized": len(all_rows),
        "usable_total": len(usable_rows),
        "status_counts": dict(all_by_status),
        "usable_by_locale": dict(usable_by_locale),
        "quality_flag_counts": dict(blocked_flags),
        "selection_rule": "review_status == legacy_import AND confidence >= min_confidence AND quality_flags is empty",
    }
    path = output_dir / "_usable_report.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export high-confidence legacy RAG rows for MVP use.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-confidence", type=float, default=0.75)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    rows = normalize_files(DEFAULT_INPUTS)
    usable = [row for row in rows if is_usable(row, min_confidence=args.min_confidence)]
    write_grouped(usable, output_dir)
    write_report(rows, usable, output_dir, min_confidence=args.min_confidence)


if __name__ == "__main__":
    main()
