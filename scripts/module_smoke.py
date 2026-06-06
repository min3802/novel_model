from __future__ import annotations

"""Run w.LiGHTER model modules directly without starting the web UI/API server.

Default mode is mock/offline so this is safe for quick local checks:

    python scripts/module_smoke.py --case all
    python scripts/module_smoke.py --case translate --locale ko_en_us
    python scripts/module_smoke.py --case terminology

Use --live only when you intentionally want configured external model/API calls.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.services.guide_service import guide
from backend.services.translation_service import COUNTRY_TO_LOCALE, translate
from ko_locale_pipeline.annotation_retriever import AnnotationRetriever
from ko_locale_pipeline.config import PipelineConfig
from ko_locale_pipeline.consistency_checker import check_translation_consistency
from ko_locale_pipeline.retriever import DenseRetriever
from ko_locale_pipeline.terminology import (
    extract_noun_terminology_candidates,
    render_terminology_context,
)


def ko(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


DEFAULT_SOURCE = ko(
    "\\uae40\\ucca8\\uc9c0\\ub294 \\uc0ac\\ub791 \\uc57d\\uad6d \\uc55e\\uc5d0\\uc11c "
    "\\ub3d9\\uc18c\\ubb38 \\uc2dc\\uc7a5\\uc744 \\ubc14\\ub77c\\ubd24\\ub2e4. "
    "\\ube68\\uac1b\\uace0 \\ubd89\\uc740 \\ud45c\\uc815\\uc740 \\uc790\\uc5f0\\uc2a4\\ub7fd\\uac8c "
    "\\ub2e4\\ub974\\uac8c \\ubc88\\uc5ed\\ub418\\uc5b4\\ub3c4 \\ub418\\uc9c0\\ub9cc, "
    "\\uc0ac\\ub791 \\uc57d\\uad6d\\uc740 \\ud55c \\uac00\\uc9c0 \\uc774\\ub984\\uc73c\\ub85c \\uc720\\uc9c0\\ub418\\uc5b4\\uc57c \\ud55c\\ub2e4."
)


def _country_for_locale(locale: str) -> str:
    for country, mapped_locale in COUNTRY_TO_LOCALE.items():
        if mapped_locale == locale:
            return country
    raise ValueError(f"unsupported locale: {locale}")


def _sample_terms() -> list[dict[str, Any]]:
    return [
        {
            "source": ko("\\uae40\\ucca8\\uc9c0"),
            "target": "Kim Cheomji",
            "policy": "locked",
            "type": "person_name",
            "status": "confirmed",
        },
        {
            "source": ko("\\uc0ac\\ub791 \\uc57d\\uad6d"),
            "target": "Sarang Pharmacy",
            "policy": "locked",
            "type": "business_name",
            "status": "confirmed",
        },
        {
            "source": ko("\\uc57d\\uad6d"),
            "target": "pharmacy",
            "allowedTranslations": ["pharmacy", "drugstore"],
            "policy": "preferred",
            "type": "common_noun",
            "status": "confirmed",
        },
    ]


def run_terminology(source: str, locale: str) -> dict[str, Any]:
    candidates = extract_noun_terminology_candidates(source)
    terms = _sample_terms()
    return {
        "candidateCount": len(candidates),
        "candidates": candidates[:10],
        "context": render_terminology_context(terms, locale, source_text=source),
    }


def run_consistency(source: str, locale: str) -> dict[str, Any]:
    return {
        "passExample": check_translation_consistency(
            source_text=source,
            translated_text="Kim Cheomji looked toward Dongsomun Market in front of Sarang Pharmacy.",
            locale=locale,
            terminology=_sample_terms(),
        ),
        "warningExample": check_translation_consistency(
            source_text=source,
            translated_text="Kim Cheomji looked toward Dongsomun Market in front of Sarang Drugstore.",
            locale=locale,
            terminology=_sample_terms(),
        ),
    }


def run_translate(source: str, locale: str) -> dict[str, Any]:
    result = translate(
        {
            "sourceText": source,
            "targetCountry": _country_for_locale(locale),
            "terminology": _sample_terms(),
        }
    )
    workflow = result.get("workflow") or {}
    return {
        "locale": result.get("locale"),
        "finalTranslation": result.get("finalTranslation"),
        "retrievalCount": result.get("retrievalCount"),
        "terminologyCandidates": result.get("terminologyCandidates", [])[:10],
        "terminologyContext": workflow.get("terminology_context", ""),
        "consistency": workflow.get("consistency"),
        "inspectionAction": (workflow.get("inspection") or {}).get("recommended_action"),
    }


def run_retrieval(source: str, locale: str) -> dict[str, Any]:
    config = PipelineConfig(locale=locale, mock=True, score_threshold=0.0, annotation_score_threshold=0.0)
    dense = DenseRetriever(config)
    annotation = AnnotationRetriever(config)
    return {
        "dense": [
            {
                "score": round(row.score, 4),
                "id": row.item.get("id"),
                "anchor": row.item.get("ko_anchor_expression") or row.item.get("term_ko"),
                "text": row.item.get("text") or row.item.get("explanation") or row.item.get("target_text"),
            }
            for row in dense.retrieve(source, top_k=3)
        ],
        "annotation": [
            {
                "score": round(row.score, 4),
                "id": row.item.get("id"),
                "keyword": (row.item.get("metadata") or {}).get("keyword_ko"),
                "context": row.item.get("context_text"),
            }
            for row in annotation.retrieve(source, top_k=3)
        ],
    }


def run_guide(locale: str) -> dict[str, Any]:
    country = _country_for_locale(locale)
    result = guide(
        {
            "targetCountry": country,
            "genre": ko("\\ud604\\ub300\\ubb38\\ud559"),
            "synopsis": ko("\\uc6b4\\uc218 \\uc88b\\uc740 \\ub0a0\\uc758 \\uae40\\ucca8\\uc9c0\\uac00 \\ub3c4\\uc2dc\\uc758 \\uc2dc\\uc7a5\\uacfc \\uc57d\\uad6d\\uc744 \\uc9c0\\ub098\\uba70 \\uc120\\ud0dd\\uc758 \\uae30\\ub85c\\uc5d0 \\uc120\\ub2e4."),
        }
    )
    return {
        "title": result.get("title"),
        "sectionCount": len(result.get("sections", [])),
        "sections": (
            result.get("sections", [])[:3]
            if isinstance(result.get("sections"), list)
            else list((result.get("sections") or {}).items())[:3]
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run model modules without web frontend.")
    parser.add_argument("--case", choices=["all", "terminology", "consistency", "translate", "retrieval", "guide"], default="all")
    parser.add_argument("--locale", default="ko_en_us", choices=sorted(set(COUNTRY_TO_LOCALE.values())))
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--live", action="store_true", help="Use live external model/API calls instead of mock mode.")
    args = parser.parse_args()

    os.environ["WLIGHTER_MOCK_MODE"] = "false" if args.live else "true"

    runners = {
        "terminology": lambda: run_terminology(args.source, args.locale),
        "consistency": lambda: run_consistency(args.source, args.locale),
        "translate": lambda: run_translate(args.source, args.locale),
        "retrieval": lambda: run_retrieval(args.source, args.locale),
        "guide": lambda: run_guide(args.locale),
    }
    selected = runners.keys() if args.case == "all" else [args.case]
    output = {
        "mode": "live" if args.live else "mock",
        "locale": args.locale,
        "results": {name: runners[name]() for name in selected},
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
