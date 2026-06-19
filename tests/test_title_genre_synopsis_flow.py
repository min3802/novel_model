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
                "title": '버림받은 공녀는 다시 웃지 않는다',
                "genre": '로맨스 판타지',
                "synopsis": '가문에서 버림받은 공녀가 돌아와 자신의 자리를 되찾는다.',
            }
        )

        briefing = result["contextPackBriefing"]
        self.assertEqual(result["mode"], "country_genre_guide")
        self.assertIn(result["generationMode"], {"recommended_country_selected", "manual_country_after_recommendation"})
        self.assertEqual(result["title"], '일본 현지화 기준서')
        self.assertEqual(briefing["input_summary"]["work_title"], '버림받은 공녀는 다시 웃지 않는다')
        self.assertEqual(briefing["input_summary"]["genre"], '로맨스 판타지')
        self.assertEqual(briefing["input_summary"]["title_elements"], [])
        self.assertEqual(briefing["input_summary"]["comparable_elements"], ['로맨스 판타지'])
        self.assertTrue(briefing["writer_copy"]["input_elements_title"])
        self.assertTrue(briefing["writer_copy"]["comparable_elements_title"])
        self.assertIn('공녀가 돌아와', result["synopsis"])
        self.assertIn("contextPackBriefing", result)
        self.assertIn("policyAttentionCards", result)

    def test_synopsis_inferred_policy_cards_remain_marked_inferred(self) -> None:
        report = build_policy_attention_report(
            {
                "targetCountry": "Japan",
                "title": '평범한 공녀',
                "genre": '로맨스 판타지',
                "synopsis": '성적 묘사와 잔혹 묘사가 짙어 R18 표시를 검토해야 한다.',
            }
        )

        cards = report["policy_attention_cards"]
        self.assertEqual(len(cards), 3)
        self.assertTrue(all(card["match_source"] == "synopsis_inferred" for card in cards))
        self.assertCountEqual(
            [card["matched_rule_ids"][0] for card in cards],
            ["JP_ALPHAPOLIS_0001", "JP_ALPHAPOLIS_0002", "JP_ALPHAPOLIS_0009"],
        )
        self.assertIn("R18", str(cards))

    def test_title_genre_synopsis_can_still_trigger_direct_policy_cards(self) -> None:
        report = build_policy_attention_report(
            {
                "targetCountry": "Japan",
                "title": 'R15 악역영애는 피의 복수를 시작한다',
                "genre": '로맨스 판타지',
                "synopsis": '성적 묘사와 잔혹한 복수 장면이 이어지는 작품이다.',
            }
        )

        cards = report["policy_attention_cards"]
        self.assertEqual(len(cards), 3)
        self.assertTrue(any(card["match_source"] == "title_or_genre" for card in cards))
        self.assertCountEqual(
            [card["matched_rule_ids"][0] for card in cards],
            ["JP_ALPHAPOLIS_0001", "JP_ALPHAPOLIS_0002", "JP_ALPHAPOLIS_0009"],
        )
        self.assertNotIn("??", str(report))

    def test_synopsis_presence_changes_guide_reading_contract(self) -> None:
        base_payload = {
            "targetCountry": "Japan",
            "title": '버림받은 공녀는 다시 웃지 않는다',
            "genre": '로맨스 판타지',
        }

        without_synopsis = guide({**base_payload, "legacyGuide": True})
        with_synopsis = guide(
            {
                **base_payload,
                "legacyGuide": True,
                "synopsis": '가문에서 버림받은 공녀가 회귀해 잔혹한 복수를 준비한다.',
            }
        )

        self.assertEqual(without_synopsis["mode"], "country_genre_guide")
        self.assertEqual(with_synopsis["mode"], "country_genre_guide")
        self.assertIn(with_synopsis["generationMode"], {"recommended_country_selected", "manual_country_after_recommendation"})
        self.assertFalse(without_synopsis["contextPackBriefing"]["input_summary"]["synopsis_present"])
        self.assertTrue(with_synopsis["contextPackBriefing"]["input_summary"]["synopsis_present"])
        self.assertEqual(without_synopsis["contextPackBriefing"]["input_summary"]["synopsis_inferred_elements"], [])
        self.assertIn(
            '회귀·전생·이세계 축',
            with_synopsis["contextPackBriefing"]["input_summary"]["synopsis_inferred_elements"],
        )
        self.assertIn(
            '전투·생존 축',
            with_synopsis["contextPackBriefing"]["input_summary"]["synopsis_inferred_elements"],
        )
        self.assertTrue(
            any('시놉시스가 없어' in item for item in without_synopsis["sections"]["market_trend_fit"]["items"])
        )
        self.assertTrue(
            any('확정 태그가 아니라' in item for item in with_synopsis["sections"]["title_synopsis_localization"]["items"])
        )


if __name__ == "__main__":
    unittest.main()

