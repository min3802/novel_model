from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.guide.context_pack_analysis import WorkInput, build_context_pack_overlap_report


DEFAULT_OUTPUT_STEM = ROOT / "docs" / "context_pack_overlap_report_sample"

DEFAULT_WORK: dict[str, Any] = {
    "title": "계약 결혼을 거부한 악역영애는 몰락한 영지를 다시 세운다",
    "target_market": "japan",
    "genre": "로맨스 판타지",
    "synopsis": (
        "전생의 기억을 되찾은 공작가 영애가 원치 않는 계약 결혼을 거절하고 "
        "몰락한 영지에서 재건과 마법 계약을 시도하는 이야기. "
        "복수보다 성장과 해피엔딩에 초점을 둔다."
    ),
    "title_elements": ["계약 결혼", "악역영애", "몰락한 영지", "재건"],
    "comparable_signals": ["로맨스 판타지", "이세계 전생", "귀족", "마법", "해피엔딩"],
}


def _load_work(path: Path | None, market_override: str | None) -> WorkInput:
    payload = json.loads(path.read_text(encoding="utf-8")) if path else dict(DEFAULT_WORK)
    if market_override:
        payload["target_market"] = market_override
    return WorkInput.from_dict(payload)


def _write_outputs(report: dict[str, Any], output_stem: Path) -> list[Path]:
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_stem.with_suffix(".json")
    ui_path = output_stem.with_suffix(".ui.json")
    md_path = output_stem.with_suffix(".md")
    html_path = output_stem.with_suffix(".html")

    json_payload = {
        "evidence": report["evidence"],
        "ui_briefing_payload": report["ui_briefing_payload"],
        "markdown": report["markdown"],
    }
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ui_path.write_text(json.dumps(report["ui_briefing_payload"], ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report["markdown"], encoding="utf-8-sig")
    html_path.write_text(report["html"], encoding="utf-8-sig")
    return [json_path, ui_path, md_path, html_path]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate deterministic context-pack observation outputs for later LLM guide generation. "
            "This script does not call an LLM."
        )
    )
    parser.add_argument("--work-json", type=Path, help="작품 입력 JSON 경로. 없으면 샘플 작품을 사용합니다.")
    parser.add_argument("--market", help="target_market override. 예: japan, english, china, thailand")
    parser.add_argument(
        "--output-stem",
        type=Path,
        default=DEFAULT_OUTPUT_STEM,
        help="확장자를 제외한 출력 경로. 기본: docs/context_pack_overlap_report_sample",
    )
    args = parser.parse_args()

    work = _load_work(args.work_json, args.market)
    report = build_context_pack_overlap_report(work)
    paths = _write_outputs(report, args.output_stem)

    evidence = report["evidence"]
    print("Generated context-pack observation report")
    print(f"- market: {evidence['target_market']} / {evidence['target_market_ko']}")
    print(f"- context_records: {evidence['context_record_count']}")
    print(
        "- observed_work_elements: "
        f"{evidence['summary']['observed_signal_count']} / {evidence['summary']['declared_signal_count']}"
    )
    for path in paths:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

