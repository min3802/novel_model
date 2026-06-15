from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.translation import PipelineConfig, TranslationMode, TranslationPipeline  # noqa: E402
from app.translation.infra.runtime import is_mock_mode  # noqa: E402


DEFAULT_PIPELINE = TranslationMode.V2_DUAL_DRAFT_REVIEW.value
BLOCKED_STATUS = "blocked_translation_safety"


def _snake_to_camel(value: str) -> str:
    return re.sub(r"_([a-zA-Z])", lambda match: match.group(1).upper(), value)


def _to_public_json(value: Any) -> Any:
    if is_dataclass(value):
        return _to_public_json(asdict(value))
    if isinstance(value, dict):
        return {_snake_to_camel(str(key)): _to_public_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_public_json(item) for item in value]
    return value


def _message_for_status(delivery_status: str) -> str:
    if delivery_status == "qa_warning":
        return "Translation completed with review cards."
    if delivery_status == BLOCKED_STATUS:
        return "Translation blocked by safety contract."
    return ""


def _build_payload(
    *,
    result: Any,
    work_id: str,
    episode_id: str,
    source_locale: str,
    target_locale: str,
    pipeline: str,
    input_path: Path,
    mock: bool,
) -> dict[str, Any]:
    result_data = _to_public_json(result)
    delivery_status = result_data.get("deliveryStatus", "deliverable")
    return {
        "workId": work_id,
        "episodeId": episode_id,
        "sourceLocale": source_locale,
        "targetLocale": target_locale,
        "pipeline": pipeline,
        "inputPath": str(input_path),
        "mock": mock,
        "deliveryStatus": delivery_status,
        "userVisibleErrorCode": result_data.get("userVisibleErrorCode"),
        "message": _message_for_status(delivery_status),
        "finalTranslation": result_data.get("finalTranslation", ""),
        "meaningDraft": result_data.get("meaningDraft", {}),
        "ragEvidence": result_data.get("ragEvidence", []),
        "translationDecisions": result_data.get("translationDecisions", []),
        "authorReviewCards": result_data.get("authorReviewCards", []),
    }


def _validate_blocked_safety_contract(payload: dict[str, Any]) -> None:
    if payload.get("deliveryStatus") != BLOCKED_STATUS:
        return

    expected_empty_fields = ("ragEvidence", "translationDecisions", "authorReviewCards")
    violations: list[str] = []
    if payload.get("finalTranslation") != "":
        violations.append("finalTranslation must be empty for blocked_translation_safety")
    for field in expected_empty_fields:
        if payload.get(field) != []:
            violations.append(f"{field} must be [] for blocked_translation_safety")
    if violations:
        raise RuntimeError("; ".join(violations))


def _run_v2_dual_draft_review(
    *,
    source_text: str,
    target_locale: str,
    mock: bool,
) -> Any:
    config = PipelineConfig(
        locale=target_locale,
        mode=TranslationMode.V2_DUAL_DRAFT_REVIEW,
        mock=mock,
    )
    pipeline = TranslationPipeline(config)
    return pipeline.run_v2_dual_draft_review(source_text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a long-source smoke translation through the internal v2_dual_draft_review pipeline."
    )
    parser.add_argument("--input", required=True, help="Path to a UTF-8 Korean source text file.")
    parser.add_argument("--target-locale", default="ko_ja", help="Target locale, for example ko_ja.")
    parser.add_argument("--source-locale", default="ko", help="Source locale. Defaults to ko.")
    parser.add_argument("--work-id", default="work_smoke", help="Smoke test work id.")
    parser.add_argument("--episode-id", default="ep_smoke", help="Smoke test episode id.")
    parser.add_argument(
        "--output",
        help="Output JSON path. Defaults to outputs/long_translation_smoke_<target-locale>.json.",
    )
    parser.add_argument(
        "--pipeline",
        default=DEFAULT_PIPELINE,
        choices=[DEFAULT_PIPELINE],
        help="Internal/test pipeline selector. This is not a public API request field.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock mode for import-level or offline smoke checks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else Path("outputs") / f"long_translation_smoke_{args.target_locale}.json"
    source_text = input_path.read_text(encoding="utf-8")
    mock = bool(args.mock or is_mock_mode() or os.getenv("WLIGHTER_MOCK_MODE", "").strip().lower() == "true")

    result = _run_v2_dual_draft_review(
        source_text=source_text,
        target_locale=args.target_locale,
        mock=mock,
    )
    payload = _build_payload(
        result=result,
        work_id=args.work_id,
        episode_id=args.episode_id,
        source_locale=args.source_locale,
        target_locale=args.target_locale,
        pipeline=args.pipeline,
        input_path=input_path,
        mock=mock,
    )
    _validate_blocked_safety_contract(payload)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    print(f"deliveryStatus={payload['deliveryStatus']}")
    print(f"authorReviewCards={len(payload['authorReviewCards'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
