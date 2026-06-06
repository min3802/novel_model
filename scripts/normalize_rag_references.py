from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
LEGACY_IDIOM_RAG_DIR = ROOT / "data" / "legacy_idiom_rag"
DEFAULT_INPUTS = [
    LEGACY_IDIOM_RAG_DIR / "raw_enriched" / "jp_idiom_references_enriched.json",
    LEGACY_IDIOM_RAG_DIR / "raw_enriched" / "th_idiom_references_enriched.json",
    LEGACY_IDIOM_RAG_DIR / "raw_enriched" / "us_idiom_references_enriched.json",
    LEGACY_IDIOM_RAG_DIR / "raw_enriched" / "zh_idiom_references_enriched.json",
    ROOT / "ko_anchored_idiom_results_final" / "cn_idiom_references_ko_anchored.json",
    ROOT / "ko_anchored_idiom_results_final" / "jp_idiom_references_ko_anchored.json",
    ROOT / "ko_anchored_idiom_results_final" / "th_idiom_references_ko_anchored.json",
    ROOT / "ko_anchored_idiom_results_final" / "us_idiom_references_ko_anchored.json",
]

COUNTRY_LANGUAGE_TO_LOCALE = {
    ("US", "en"): "ko_en_us",
    ("United States", "en"): "ko_en_us",
    ("Japan", "ja"): "ko_ja",
    ("JP", "ja"): "ko_ja",
    ("CN", "zh"): "ko_zh_cn",
    ("China", "zh"): "ko_zh_cn",
    ("TH", "th"): "ko_th_th",
    ("Thailand", "th"): "ko_th_th",
}

FILE_HINT_TO_LOCALE = {
    "us_": "ko_en_us",
    "jp_": "ko_ja",
    "cn_": "ko_zh_cn",
    "zh_": "ko_zh_cn",
    "th_": "ko_th_th",
}


def ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_list(value: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in ensure_list(value):
        text = clean_text(item)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def slug(value: str) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-zA-Z가-힣一-龥ぁ-ゟ゠-ヿ]+", "_", text).strip("_")
    return text[:64] or "unknown"


def infer_locale(row: dict[str, Any], source_path: Path) -> str:
    country = clean_text(row.get("country"))
    language = clean_text(row.get("language"))
    if (country, language) in COUNTRY_LANGUAGE_TO_LOCALE:
        return COUNTRY_LANGUAGE_TO_LOCALE[(country, language)]
    lower_name = source_path.name.lower()
    for prefix, locale in FILE_HINT_TO_LOCALE.items():
        if lower_name.startswith(prefix):
            return locale
    raise ValueError(f"Cannot infer locale for row {row.get('id')} from {source_path}")


def pick_source_expressions(row: dict[str, Any]) -> tuple[str, list[str]]:
    anchors = clean_list(row.get("ko_anchor_expression"))
    korean_candidates = clean_list(row.get("ko_expression"))
    ordered = anchors + [item for item in korean_candidates if item not in anchors]
    source_expression = ordered[0] if ordered else ""
    aliases = [item for item in ordered[1:] if item != source_expression]
    return source_expression, aliases


def infer_strategy(row: dict[str, Any]) -> str:
    strategy = clean_text(row.get("translation_strategy"))
    if strategy:
        return strategy
    return "paraphrase"


def infer_confidence(row: dict[str, Any]) -> float:
    fit_score = row.get("fit_score")
    if isinstance(fit_score, (int, float)):
        return max(0.0, min(1.0, float(fit_score) / 100.0))
    return 0.5


def has_ko_anchor(row: dict[str, Any]) -> bool:
    return bool(clean_list(row.get("ko_anchor_expression")))


def looks_machine_translated_korean(value: str) -> bool:
    """Heuristic only: flags awkward Korean candidate phrases for human review."""
    text = clean_text(value)
    if not text:
        return True
    # Very short numeric/measure-description candidates are often generated labels, not natural source expressions.
    if re.search(r"\d", text) and any(token in text for token in ["주기", "단위", "배수", "완성"]):
        return True
    awkward_suffixes = (
        "해",
        "년",
        "것",
        "상태",
        "상황",
        "느낌",
        "개념",
    )
    awkward_markers = [
        "단위의",
        "주기적인",
        "완성된",
        "완성년",
        "기반의",
        "관련된",
    ]
    if any(marker in text for marker in awkward_markers) and text.endswith(awkward_suffixes):
        return True
    # Long noun-stack labels without particles are often glossary descriptions rather than expressions.
    if len(text) >= 14 and not re.search(r"[은는이가을를의에로와과도만]", text):
        return True
    return False


def quality_flags(row: dict[str, Any], source_expression: str, confidence: float) -> list[str]:
    flags: list[str] = []
    if not has_ko_anchor(row):
        flags.append("missing_ko_anchor")
    if confidence < 0.7:
        flags.append("low_confidence")
    if looks_machine_translated_korean(source_expression):
        flags.append("source_expression_may_be_machine_translated")
    if not clean_text(row.get("translation_strategy")):
        flags.append("missing_translation_strategy")
    if not pick_example(row):
        flags.append("missing_example")
    return flags


def review_status_for(flags: list[str]) -> str:
    # Legacy rows with structural quality risks should be searchable only as review candidates,
    # not strong translation-decision cards.
    blocking_flags = {
        "missing_ko_anchor",
        "source_expression_may_be_machine_translated",
    }
    if any(flag in blocking_flags for flag in flags):
        return "needs_review"
    return "legacy_import"


def build_tags(row: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for field in ["scene", "tone"]:
        for item in clean_list(row.get(field)):
            if item not in tags:
                tags.append(item)
    return tags


def pick_example(row: dict[str, Any]) -> str:
    examples = clean_list(row.get("examples"))
    if not examples:
        examples = clean_list(row.get("examples_original"))
    return examples[0] if examples else ""


def normalize_row(row: dict[str, Any], source_path: Path) -> dict[str, Any] | None:
    source_expression, source_aliases = pick_source_expressions(row)
    target_expression = clean_text(row.get("expression"))
    if not source_expression or not target_expression:
        return None

    locale = infer_locale(row, source_path)
    legacy_id = clean_text(row.get("id")) or slug(target_expression)
    normalized_id = f"{locale}_{legacy_id}_{slug(source_expression)}"
    warning = clean_text(row.get("caution"))
    confidence = infer_confidence(row)
    flags = quality_flags(row, source_expression, confidence)
    return {
        "id": normalized_id,
        "locale": locale,
        "category": "idiom",
        "source_expression": source_expression,
        "source_aliases": source_aliases,
        "target_expression": target_expression,
        "target_explanation": clean_text(row.get("meaning")),
        "strategy": infer_strategy(row),
        "reason": clean_text(row.get("usage") or row.get("original_meaning")),
        "example_source": "",
        "example_translation": pick_example(row),
        "warnings": [warning] if warning else [],
        "tags": build_tags(row),
        "confidence": confidence,
        "source_type": "legacy_import",
        "review_status": review_status_for(flags),
        "quality_flags": flags,
        "legacy": {
            "source_file": str(source_path.relative_to(ROOT)),
            "legacy_id": legacy_id,
            "country": clean_text(row.get("country")),
            "language": clean_text(row.get("language")),
        },
    }


def row_rank(row: dict[str, Any]) -> tuple[int, float, int]:
    has_anchor = 1 if "ko_anchor" in row["legacy"]["source_file"] else 0
    return (has_anchor, float(row.get("confidence") or 0), len(row.get("source_aliases") or []))


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["locale"], row["source_expression"], row["target_expression"])
        if key not in buckets or row_rank(row) > row_rank(buckets[key]):
            buckets[key] = row
        else:
            existing = buckets[key]
            aliases = list(existing.get("source_aliases") or [])
            for alias in row.get("source_aliases") or []:
                if alias not in aliases and alias != existing["source_expression"]:
                    aliases.append(alias)
            existing["source_aliases"] = aliases
    return sorted(buckets.values(), key=lambda item: (item["locale"], item["source_expression"], item["target_expression"]))


def load_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def normalize_files(input_paths: list[Path]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    skipped = 0
    for path in input_paths:
        if not path.exists():
            continue
        for row in load_rows(path):
            item = normalize_row(row, path)
            if item is None:
                skipped += 1
                continue
            normalized.append(item)
    result = dedupe(normalized)
    print(f"normalized={len(result)} raw={len(normalized)} skipped={skipped}")
    return result


def write_by_locale(rows: list[dict[str, Any]], output_dir: Path, *, sample: int | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["locale"]].append(row)
    for locale, locale_rows in sorted(grouped.items()):
        if sample is not None:
            locale_rows = locale_rows[:sample]
        path = output_dir / f"{locale}_references.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(locale_rows, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"wrote {path.relative_to(ROOT)} rows={len(locale_rows)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize legacy idiom RAG references into translation-decision cards.")
    parser.add_argument("--output-dir", type=Path, default=LEGACY_IDIOM_RAG_DIR / "normalized")
    parser.add_argument("--sample", type=int, default=None, help="Write only N rows per locale for inspection.")
    parser.add_argument("--input", type=Path, action="append", dest="inputs", help="Optional input JSON path; can be repeated.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inputs = args.inputs or DEFAULT_INPUTS
    rows = normalize_files([path if path.is_absolute() else ROOT / path for path in inputs])
    write_by_locale(rows, args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir, sample=args.sample)


if __name__ == "__main__":
    main()
