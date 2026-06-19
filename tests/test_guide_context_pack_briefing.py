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

    def test_context_pack_can_be_disabled_without_public_briefing_payload(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": "계약 결혼을 거부한 악역영애",
                "genre": "로맨스 판타지",
                "titleElements": ["계약 결혼", "악역영애"],
                "includeContextPack": False,
                "includeInternal": True,
            }
        )

        self.assertFalse(result["contextPackUsed"])
        self.assertEqual(result["targetMarket"], "japan")
        self.assertEqual(result["contextRecordCount"], 0)
        self.assertEqual(result["observedSignalCount"], 0)
        self.assertEqual(result["matchedSignals"], [])
        self.assertNotIn("contextPackBriefing", result)
        self.assertNotIn("contextPackEvidence", result)

    def test_context_pack_diagnostics_are_internal_only(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": "계약 결혼을 거부한 악역영애",
                "genre": "로맨스 판타지",
                "titleElements": ["계약 결혼", "악역영애"],
            }
        )

        self.assertIn("contextPackBriefing", result)
        self.assertNotIn("contextPackUsed", result)
        self.assertNotIn("matchedSignals", result)

    def test_reunion_synopsis_does_not_infer_reincarnation_axis_from_again(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": "다시 만난 너에게",
                "genre": "현대 로맨스",
                "synopsis": "헤어진 두 사람이 고향으로 돌아와 다시 만나 사랑을 확인한다.",
                "includeInternal": True,
            }
        )

        briefing = result["contextPackBriefing"]
        inferred = briefing["input_summary"]["synopsis_inferred_elements"]
        self.assertNotIn("회귀·전생·이세계 축", inferred)
        self.assertNotIn("회귀·전생·이세계 축", result["matchedSignals"])


if __name__ == "__main__":
    unittest.main()
