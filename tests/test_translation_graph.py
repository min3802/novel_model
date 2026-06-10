from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.translation import PipelineConfig, TranslationGraph
from app.translation.infra.country_locale import COUNTRY_TO_LOCALE
from app.translation.translation_graph import _format_support_context


class TranslationGraphTests(unittest.TestCase):
    def _config(self) -> tuple[PipelineConfig, str]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)

        idiom_dataset = base / "idiom_dataset.json"
        idiom_dataset.write_text(
            json.dumps(
                [
                    {
                        "id": "idiom_001",
                        "embedding_text": "tense and suspenseful scene",
                        "context_text": "A tense idiom example with strong emotional pressure",
                        "ko_anchor_expression": ["손에 땀"],
                        "ko_expression": ["손에 땀을 쥐다"],
                        "expression": "tense",
                        "meaning": "tense and suspenseful",
                        "usage": "use for anxious, gripping scenes",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        annotation_dataset = base / "annotation_dataset.json"
        annotation_dataset.write_text(
            json.dumps(
                [
                    {
                        "id": "anno_001",
                        "keyword_ko": "한복",
                        "context_text": "A Korean traditional clothing note candidate",
                        "embedding_text": "hanbok korean traditional clothing cultural note candidate",
                        "category": ["culture", "clothing"],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return (
            PipelineConfig(
                locale="ko_en_us",
                rag_dataset_path=idiom_dataset,
                annotation_dataset_path=annotation_dataset,
                score_threshold=0.0,
                annotation_score_threshold=0.0,
                mock=True,
                embedding_cache_dir=base / "cache",
            ),
            next(country for country, locale in COUNTRY_TO_LOCALE.items() if locale == "ko_en_us"),
        )

    def test_translation_graph_builds_profile_analysis_and_support_state(self) -> None:
        config, country = self._config()
        graph = TranslationGraph(config)
        source_text = "김첨지는 손에 땀을 쥐며 한복 차림의 오빠를 바라봤다."
        result = graph.run_with_inspection(
            source_text,
            request_payload={
                "targetCountry": country,
                "sourceText": source_text,
                "genre": "현대 로맨스",
                "synopsis": "감정의 긴장과 문화적 맥락이 함께 드러나는 장면.",
            },
        )

        self.assertFalse(result.blocked)
        self.assertTrue(result.translation_profile)
        self.assertTrue(result.source_analysis)
        self.assertIn("TRANSLATION_PROFILE", result.memory_context)
        self.assertIn("SOURCE_ANALYSIS", result.memory_context)
        self.assertTrue(result.terminology_candidates)
        self.assertTrue(result.active_terminology)
        self.assertTrue(result.annotation_candidates)
        self.assertIn("note_needed", result.annotation_candidates[0])
        self.assertIn("can_inline", result.annotation_candidates[0])
        self.assertIn("no_note_needed", result.annotation_candidates[0])
        self.assertEqual(result.draft_translation, result.draft["translation"])
        self.assertEqual(result.reviewed_translation, result.draft["translation"])
        self.assertEqual(result.inspection_issues, result.inspection["issues"])
        self.assertIn("translationProfile", result.context_extraction or {})
        self.assertIn("sourceAnalysis", result.context_extraction or {})
        self.assertIn("supportContext", result.context_extraction or {})

    def test_translation_memory_context_excludes_annotation_context(self) -> None:
        state = {
            "base_memory_context": "base memory",
            "translation_profile": {"tone": "balanced", "do_not": []},
            "source_analysis": {"summary": "analysis"},
            "terminology_context": "terminology context",
            "support_context": {
                "idiom_context": "idiom context",
                "annotation_context": "annotation context should stay out",
            },
        }

        memory_context = _format_support_context(state)  # type: ignore[arg-type]

        self.assertIn("base memory", memory_context)
        self.assertIn("idiom context", memory_context)
        self.assertIn("terminology context", memory_context)
        self.assertNotIn("annotation context should stay out", memory_context)


if __name__ == "__main__":
    unittest.main()
