from __future__ import annotations

import unittest

from backend.services.guide_service import guide


class GuideContextPackBriefingTest(unittest.TestCase):
    def test_guide_attaches_writer_facing_context_pack_briefing(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": "계약 결혼을 거부한 악역영애는 몰락한 영지를 다시 세운다",
                "genre": "로맨스 판타지",
                "titleElements": ["계약 결혼", "악역영애", "몰락한 영지", "재건"],
                "comparableSignals": ["로맨스 판타지", "귀족", "마법", "해피엔딩"],
            }
        )

        briefing = result["contextPackBriefing"]
        self.assertEqual(briefing["title"], "일본 플랫폼 분위기 스냅샷")
        self.assertIn("살펴본 작품 340편", briefing["scope_badges"])
        self.assertEqual(briefing["writer_copy"]["overlap_title"], "내 작품과 겹쳐 보이는 지점")
        self.assertEqual(briefing["input_summary"]["title_elements"], ["계약 결혼", "악역영애", "몰락한 영지", "재건"])
        self.assertIn("로맨스 판타지", briefing["input_summary"]["comparable_elements"])
        self.assertTrue(any(card["status_label"] == "나뉘어 보임" for card in briefing["overlap_cards"]))
        self.assertNotIn("signal_type", str(briefing))
        self.assertNotIn("context pack", str(briefing))


if __name__ == "__main__":
    unittest.main()
