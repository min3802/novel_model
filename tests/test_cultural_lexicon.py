from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ko_locale_pipeline import CulturalLexicon, PipelineConfig


class CulturalLexiconTests(unittest.TestCase):
    def _config(self) -> PipelineConfig:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        cultural_terms_path = base / "ko_cultural_terms.json"
        cultural_terms_path.write_text(
            json.dumps(
                [
                    {
                        "id": "ko_wedding_cash_gift",
                        "term_ko": "축의금",
                        "terms": ["축의금", "축의금 봉투"],
                        "aliases": ["결혼식 축의금"],
                        "category": ["wedding", "money"],
                        "core_explanation": "한국 결혼식에서 하객이 현금으로 전달하는 축하금.",
                        "annotation_points": ["봉투에 이름을 적어 전달하는 경우가 많다."],
                        "source_type": "curated",
                        "review_status": "draft",
                        "confidence": "medium",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return PipelineConfig(cultural_terms_path=cultural_terms_path, mock=True)

    def test_lookup_matches_term_or_alias(self) -> None:
        lexicon = CulturalLexicon(self._config())

        matches = lexicon.lookup("친구 결혼식이라 축의금 봉투를 챙겼다.")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "ko_wedding_cash_gift")
        self.assertEqual(matches[0].canonical_term, "축의금")
        self.assertIn("wedding", matches[0].category)

    def test_build_context_includes_curated_facts(self) -> None:
        lexicon = CulturalLexicon(self._config())
        matches = lexicon.lookup("결혼식 축의금을 얼마나 해야 할지 고민했다.")

        context = CulturalLexicon.build_context(matches)

        self.assertIn("[CULTURAL_LEXICON]", context)
        self.assertIn("ko_wedding_cash_gift", context)
        self.assertIn("한국 결혼식", context)


if __name__ == "__main__":
    unittest.main()
