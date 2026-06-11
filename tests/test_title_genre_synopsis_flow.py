from __future__ import annotations

import unittest

from backend.services.guide_service import guide
from app.guide.regulation_policy_analysis import build_policy_attention_report


class TitleGenreSynopsisFlowTests(unittest.TestCase):
    def test_sparse_title_genre_synopsis_keeps_context_briefing_soft(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": "\ubc84\ub9bc\ubc1b\uc740 \uacf5\ub140\ub294 \ub2e4\uc2dc \uc6c3\uc9c0 \uc54a\ub294\ub2e4",
                "genre": "\ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0",
                "synopsis": "\uac00\ubb38\uc5d0\uc11c \ubc84\ub9bc\ubc1b\uc740 \uacf5\ub140\uac00 \ub3cc\uc544\uc640 \uc790\uc2e0\uc758 \uc790\ub9ac\ub97c \ub418\ucc3e\ub294\ub2e4.",
            }
        )

        briefing = result["contextPackBriefing"]
        self.assertEqual(result["mode"], "country_genre_guide")
        self.assertIn(result["generationMode"], {"recommended_country_selected", "manual_country_after_recommendation"})
        self.assertEqual(result["title"], "\uc77c\ubcf8 \ud604\uc9c0\ud654 \uae30\uc900\uc11c")
        self.assertEqual(briefing["input_summary"]["work_title"], "\ubc84\ub9bc\ubc1b\uc740 \uacf5\ub140\ub294 \ub2e4\uc2dc \uc6c3\uc9c0 \uc54a\ub294\ub2e4")
        self.assertEqual(briefing["input_summary"]["genre"], "\ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0")
        self.assertEqual(briefing["input_summary"]["title_elements"], [])
        self.assertEqual(briefing["input_summary"]["comparable_elements"], ["\ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0"])
        self.assertTrue(briefing["writer_copy"]["input_elements_title"])
        self.assertTrue(briefing["writer_copy"]["comparable_elements_title"])
        self.assertIn("\uacf5\ub140\uac00 \ub3cc\uc544\uc640", result["synopsis"])
        self.assertIn("contextPackBriefing", result)
        self.assertIn("policyAttentionCards", result)

    def test_synopsis_inferred_policy_cards_remain_marked_inferred(self) -> None:
        report = build_policy_attention_report(
            {
                "targetCountry": "Japan",
                "title": "\ud3c9\ubc94\ud55c \uacf5\ub140",
                "genre": "\ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0",
                "synopsis": "\uc131\uc801 \ubb18\uc0ac\uc640 \uc794\ud639 \ubb18\uc0ac\uac00 \uc9d9\uc5b4 R18 \ud45c\uc2dc\ub97c \uac80\ud1a0\ud574\uc57c \ud55c\ub2e4.",
            }
        )

        cards = report["policy_attention_cards"]
        self.assertGreaterEqual(len(cards), 2)
        self.assertTrue(all(card["match_source"] == "synopsis_inferred" for card in cards))
        self.assertTrue(any("JP_SYOSETU_0002" in card["matched_rule_ids"] for card in cards))
        self.assertTrue(any("JP_SYOSETU_0005" in card["matched_rule_ids"] for card in cards))
        self.assertIn("R18", str(cards))

    def test_title_genre_synopsis_can_still_trigger_direct_policy_cards(self) -> None:
        report = build_policy_attention_report(
            {
                "targetCountry": "Japan",
                "title": "R15 \uc545\uc5ed\uc601\uc560\ub294 \ud53c\uc758 \ubcf5\uc218\ub97c \uc2dc\uc791\ud55c\ub2e4",
                "genre": "\ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0",
                "synopsis": "\uc131\uc801 \ubb18\uc0ac\uc640 \uc794\ud639\ud55c \ubcf5\uc218 \uc7a5\uba74\uc774 \uc774\uc5b4\uc9c0\ub294 \uc791\ud488\uc774\ub2e4.",
            }
        )

        cards = report["policy_attention_cards"]
        self.assertGreaterEqual(len(cards), 1)
        self.assertTrue(any(card["match_source"] == "title_or_genre" for card in cards))
        self.assertTrue(any("JP_KAKUYOMU_0004" in card["matched_rule_ids"] for card in cards))
        self.assertNotIn("??", str(report))

    def test_synopsis_presence_changes_guide_reading_contract(self) -> None:
        base_payload = {
            "targetCountry": "Japan",
            "title": "\ubc84\ub9bc\ubc1b\uc740 \uacf5\ub140\ub294 \ub2e4\uc2dc \uc6c3\uc9c0 \uc54a\ub294\ub2e4",
            "genre": "\ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0",
        }

        without_synopsis = guide({**base_payload, "legacyGuide": True})
        with_synopsis = guide(
            {
                **base_payload,
                "legacyGuide": True,
                "synopsis": "\uac00\ubb38\uc5d0\uc11c \ubc84\ub9bc\ubc1b\uc740 \uacf5\ub140\uac00 \ud68c\uadc0\ud574 \uc794\ud639\ud55c \ubcf5\uc218\ub97c \uc900\ube44\ud55c\ub2e4.",
            }
        )

        self.assertEqual(without_synopsis["mode"], "country_genre_guide")
        self.assertEqual(with_synopsis["mode"], "country_genre_guide")
        self.assertIn(with_synopsis["generationMode"], {"recommended_country_selected", "manual_country_after_recommendation"})
        self.assertFalse(without_synopsis["contextPackBriefing"]["input_summary"]["synopsis_present"])
        self.assertTrue(with_synopsis["contextPackBriefing"]["input_summary"]["synopsis_present"])
        self.assertEqual(without_synopsis["contextPackBriefing"]["input_summary"]["synopsis_inferred_elements"], [])
        self.assertIn(
            "\ud68c\uadc0\u00b7\uc804\uc0dd\u00b7\uc774\uc138\uacc4 \ucd95",
            with_synopsis["contextPackBriefing"]["input_summary"]["synopsis_inferred_elements"],
        )
        self.assertIn(
            "\uc804\ud22c\u00b7\uc0dd\uc874 \ucd95",
            with_synopsis["contextPackBriefing"]["input_summary"]["synopsis_inferred_elements"],
        )
        self.assertTrue(
            any("\uc2dc\ub189\uc2dc\uc2a4\uac00 \uc5c6\uc5b4" in item for item in without_synopsis["sections"]["market_trend_fit"]["items"])
        )
        self.assertTrue(
            any("\ud655\uc815 \ud0dc\uadf8\uac00 \uc544\ub2c8\ub77c" in item for item in with_synopsis["sections"]["title_synopsis_localization"]["items"])
        )


if __name__ == "__main__":
    unittest.main()

