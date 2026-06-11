from __future__ import annotations

import unittest

from backend.services.guide_service import guide
from app.guide.regulation_policy_analysis import (
    build_policy_attention_report,
    load_policy_rules,
    normalize_country_code,
)


class RegulationPolicyAnalysisTests(unittest.TestCase):
    def test_country_aliases_and_sample_rules_load(self) -> None:
        self.assertEqual(normalize_country_code("Japan"), "JP")
        self.assertEqual(normalize_country_code("일본"), "JP")

        rules = load_policy_rules("Japan")

        self.assertGreaterEqual(len(rules), 40)
        self.assertTrue(any(rule.rule_id == "JP_ALPHAPOLIS_0010" for rule in rules))
        self.assertTrue(all(rule.country == "JP" for rule in rules))

    def test_direct_inputs_generate_policy_attention_cards(self) -> None:
        report = build_policy_attention_report(
            {
                "targetCountry": "Japan",
                "titleElements": ["R15 기준", "악역영애"],
                "comparableSignals": ["잔혹 묘사", "성적 묘사", "이세계 전생"],
                "synopsis": "연령 제한 설정을 확인해야 하는 복수극.",
            }
        )

        cards = report["policy_attention_cards"]
        self.assertGreaterEqual(len(cards), 2)
        self.assertTrue(any("JP_KAKUYOMU_0004" in card["matched_rule_ids"] for card in cards))
        self.assertTrue(any("JP_SYOSETU_0002" in card["matched_rule_ids"] for card in cards))
        self.assertTrue(any("R15 기준" in card["matched_elements"] for card in cards))
        self.assertTrue(any(card["match_source"] == "direct_input" for card in cards))
        self.assertIn("법적 판단", " ".join(report["policy_limitations"]))

    def test_synopsis_only_match_is_marked_inferred(self) -> None:
        report = build_policy_attention_report(
            {
                "targetCountry": "Japan",
                "titleElements": ["카페 운영자"],
                "synopsis": "성적 묘사와 지나치게 상세한 잔혹 묘사가 포함되어 R18 표시가 필요할 수 있다.",
            }
        )

        cards = report["policy_attention_cards"]
        self.assertTrue(cards)
        self.assertTrue(
            all(card["match_source"] == "synopsis_inferred" for card in cards),
            msg=str([(card["matched_rule_ids"], card["match_source"], card["matched_elements"]) for card in cards]),
        )

    def test_no_match_returns_empty_cards_with_limitations(self) -> None:
        report = build_policy_attention_report(
            {
                "targetCountry": "Japan",
                "titleElements": ["카페", "요리"],
                "synopsis": "작은 마을에서 빵집을 운영하는 일상물.",
            }
        )

        self.assertEqual(report["policy_attention_cards"], [])
        self.assertIn("규정 확인 후보", report["policy_limitations"][0])

    def test_api_guide_attaches_policy_cards_without_mixing_with_context_pack(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": "R15 기준 악역영애는 피의 복수를 시작한다",
                "genre": "로맨스 판타지",
                "titleElements": ["R15 기준", "피의 복수"],
                "comparableSignals": ["잔혹 묘사", "성적 묘사", "이세계 전생"],
                "synopsis": "연령제한 설정을 확인해야 하는 복수극.",
            }
        )

        self.assertIn("contextPackBriefing", result)
        self.assertIn("contextPackEvidence", result)
        self.assertIn("policyAttentionCards", result)
        self.assertIn("policyLimitations", result)
        self.assertTrue(result["policyAttentionCards"])
        self.assertNotIn("policy_attention_cards", result["contextPackBriefing"])
        self.assertFalse(any("안전" in card["display_sentence"] for card in result["policyAttentionCards"]))
        self.assertNotIn("???", str(result["policyAttentionCards"]))
        self.assertNotIn("\ufffd", str(result["policyAttentionCards"]))


if __name__ == "__main__":
    unittest.main()

