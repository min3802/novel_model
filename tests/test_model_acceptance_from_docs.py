from __future__ import annotations

import os
import unittest

import api_server


class ModelAcceptanceFromDocsTests(unittest.TestCase):
    """Executable checks for the model-facing scenarios in the final test report."""

    def setUp(self) -> None:
        os.environ["WLIGHTER_MOCK_MODE"] = "true"

    def test_tst_trans_001_basic_korean_chapter_translation_is_structured(self) -> None:
        result = api_server.translate(
            {
                "sourceText": "그녀가 문을 열자 방 안은 조용했다. 그는 한참을 망설인 뒤 고개를 들었다.",
                "targetCountry": "일본",
            }
        )

        self.assertEqual(result["locale"], "ko_ja")
        self.assertTrue(result["finalTranslation"])

    def test_tst_gde_001_guide_contains_required_localization_sections(self) -> None:
        result = api_server.guide(
            {
                "legacyGuide": True,
                "targetCountry": "미국",
                "genre": "로맨스 판타지",
                "synopsis": "가문에서 버림받은 공녀가 돌아와 자신의 자리를 되찾는 이야기.",
            }
        )

        self.assertIn("번역 전 현지화 기준서", result["htmlReport"])
        self.assertIn("번역 방향", result["htmlReport"])
        self.assertIn("플랫폼 검토 항목", result["htmlReport"])
        self.assertGreaterEqual(len(result["sections"]), 3)


if __name__ == "__main__":
    unittest.main()
