from __future__ import annotations

import unittest

from app.guide.context_pack_analysis import build_context_pack_overlap_report


class ContextPackAnalysisTest(unittest.TestCase):
    def test_sample_japan_report_separates_explicit_and_comparable_elements(self) -> None:
        report = build_context_pack_overlap_report(
            {
                "title": "계약 결혼을 거부한 악역영애는 몰락한 영지를 다시 세운다",
                "target_market": "japan",
                "genre": "로맨스 판타지",
                "title_elements": ["계약 결혼", "악역영애", "몰락한 영지", "재건"],
                "comparable_signals": ["로맨스 판타지", "이세계 전생", "귀족", "마법", "해피엔딩"],
            }
        )

        evidence = report["evidence"]
        rows = {row["work_signal"]: row for row in evidence["direct_signal_rows"]}

        self.assertEqual(evidence["target_market_ko"], "일본")
        self.assertEqual(evidence["summary"]["title_element_count"], 4)
        self.assertEqual(rows["계약 결혼"]["match_status"], "near")
        self.assertEqual(rows["로맨스 판타지"]["match_status"], "decomposed")
        self.assertEqual(rows["이세계 전생"]["match_status"], "direct")
        self.assertEqual(rows["악역영애"]["direct_observation"], "not_observed")

        ui = report["ui_briefing_payload"]
        self.assertEqual(ui["title"], "일본 플랫폼 분위기 스냅샷")
        self.assertEqual(ui["writer_copy"]["input_elements_title"], "작품에서 먼저 읽히는 요소")
        self.assertEqual(ui["writer_copy"]["comparable_elements_title"], "장르상 함께 확인해볼 수 있는 요소")
        self.assertEqual(ui["input_summary"]["title_elements"], ["계약 결혼", "악역영애", "몰락한 영지", "재건"])
        self.assertIn("로맨스 판타지", ui["input_summary"]["comparable_elements"])

        romance_card = next(card for card in ui["overlap_cards"] if card["card_title"] == "로맨스 판타지")
        self.assertEqual(romance_card["status_label"], "나뉘어 보임")
        self.assertIn("연애/로맨스", romance_card["display_sentence"])
        isekai_card = next(card for card in ui["overlap_cards"] if card["card_title"] == "이세계 전생")
        self.assertIn("요소가 있다면", isekai_card["display_sentence"])
        self.assertNotIn("이세계 전생 요소는 겹쳐 보입니다", isekai_card["display_sentence"])

        self.assertIn("작품에서 먼저 읽히는 요소", report["html"])
        self.assertIn("장르상 함께 확인해볼 수 있는 요소", report["html"])
        self.assertNotIn("signal_type", report["html"])
        self.assertNotIn("context pack", report["html"])

    def test_cooccurrence_sentences_avoid_korean_particle_templates(self) -> None:
        report = build_context_pack_overlap_report(
            {
                "title": "샘플",
                "target_market": "japan",
                "genre": "판타지",
                "comparable_signals": ["이세계 전생", "해피엔딩"],
            }
        )
        sentences = [card["display_sentence"] for card in report["ui_briefing_payload"]["cooccurrence_cards"]]
        self.assertTrue(sentences)
        self.assertTrue(all("와 " not in sentence and "는 같은" not in sentence for sentence in sentences))


if __name__ == "__main__":
    unittest.main()

