from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api_server
from scripts.check_idiom_rag_long_text import LONG_TEXT


OUTPUT_JSON = Path("outputs/live_translation_result_ko_ja.json")
OUTPUT_TEXT = Path("outputs/live_translation_text_ko_ja.txt")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _serialize(result: dict[str, Any]) -> dict[str, Any]:
    workflow = result.get("workflow") or {}
    support_context = workflow.get("support_context") or {}
    payload = {
        "request": {
            "sourceText": LONG_TEXT.strip(),
            "targetCountry": "일본",
        },
        "response": result,
        "workflow": workflow,
        "support_context": support_context,
        "rag_context": support_context.get("idiom_context", ""),
        "retrieval_results": workflow.get("retrievals", []),
        "annotation_results": workflow.get("annotation_matches", []),
        "final_translation": result.get("finalTranslation", ""),
        "review_summary": result.get("reviewSummary", ""),
    }
    return payload


def main() -> int:
    source_text = LONG_TEXT.strip()
    if not source_text:
        raise SystemExit("LONG_TEXT is empty in scripts/check_idiom_rag_long_text.py")

    result = api_server.translate({"sourceText": source_text, "targetCountry": "일본"})
    payload = _serialize(result)

    _ensure_parent(OUTPUT_JSON)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_TEXT.write_text(payload["final_translation"], encoding="utf-8")

    print(f"saved_json: {OUTPUT_JSON}")
    print(f"saved_text: {OUTPUT_TEXT}")
    print(f"retrieval_count: {result.get('retrievalCount', 0)}")
    print(f"rag_context_present: {bool(payload['rag_context'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
