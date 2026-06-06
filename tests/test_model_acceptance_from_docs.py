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
                "sourceText": "그러다가 소녀가 물 속에서 무엇을 하나 집어 낸다. 하얀 조약돌이었다.",
                "targetCountry": "일본",
            }
        )

        self.assertEqual(result["locale"], "ko_ja")
        self.assertTrue(result["finalTranslation"])
        self.assertIn("workflow", result)
        self.assertIn("draft", result["workflow"])
        self.assertIn("inspection", result["workflow"])

    def test_tst_trans_001_exception_rejects_non_korean_source(self) -> None:
        result = api_server.translate(
            {
                "sourceText": "To Sherlock Holmes she is always the woman.",
                "targetCountry": "중국",
            }
        )

        self.assertIn("현재 한국어 원문만 지원", result["finalTranslation"])
        self.assertEqual(result["retrievalCount"], 0)
        self.assertEqual(result["workflow"]["inspection"]["recommended_action"], "BLOCK")

    def test_tst_chat_001_revision_request_suggests_japanese_natural_expression(self) -> None:
        result = api_server.inspect_chat(
            {
                "targetCountry": "일본",
                "question": "2번째 문장의 ‘사랑해’라는 표현이 너무 직역된 것 같아. 일본 문화에 적합하게 수정해줘.",
                "sourceText": "그는 조용히 사랑한다고 말했다.",
                "currentTranslation": "彼は静かに『愛してる』と言った。",
                "workflow": {
                    "draft": {"translation": "彼は静かに『愛してる』と言った。"},
                    "translation_review": {},
                    "inspection": {},
                    "retrievals": [],
                },
            }
        )

        self.assertIn("好きです", result["answer"])
        self.assertIn("好きです", result["proposedTranslation"])
        self.assertTrue(result["needsUserConfirmation"])

    def test_tst_chat_002_vague_and_unrelated_requests_are_handled(self) -> None:
        vague = api_server.inspect_chat(
            {
                "targetCountry": "일본",
                "question": "번역이 뭔가 이상한 것 같아요.",
                "sourceText": "그는 조용히 말했다.",
                "currentTranslation": "彼は静かに言った。",
            }
        )
        unrelated = api_server.inspect_chat(
            {
                "targetCountry": "일본",
                "question": "저녁 메뉴 추천해줘.",
                "sourceText": "그는 조용히 말했다.",
                "currentTranslation": "彼は静かに言った。",
            }
        )

        self.assertIn("어떤 부분", vague["answer"])
        self.assertIn("번역 검수 및 현지화 지원", unrelated["answer"])

    def test_tst_img_001_cover_image_mock_and_safety_refusal(self) -> None:
        ok = api_server.cover_image(
            {
                "workTitle": "소나기",
                "targetCountry": "일본",
                "genre": "근대 문학 / 첫사랑",
                "protagonist": "소년",
                "protagonistTraits": "소녀에게 설렘을 느끼는 순수한 인물",
                "appearance": "얼굴이 검게 탔고 무명 겹저고리를 입고 있다.",
                "episodeSummaries": [
                    "소년과 소녀가 징검다리에서 마주치며 첫사랑의 긴장을 만든다.",
                    "소나기 속에서 두 인물의 감정선이 가까워진다.",
                ],
                "symbols": ["징검다리", "소나기", "하얀 조약돌"],
                "mood": ["서정적", "아련함"],
                "extraPrompt": "웹소설 표지처럼 제목 공간을 확보",
            }
        )
        refused = api_server.cover_image(
            {
                "workTitle": "소나기",
                "targetCountry": "일본",
                "protagonist": "무명",
                "extraPrompt": "나체로 서 있음",
            }
        )

        self.assertEqual(ok["type"], "mock_image")
        self.assertIn("AI 생성 이미지입니다", ok["notice"])
        self.assertIn("vertical commercial web novel cover", ok["prompt"])
        self.assertIn("title-safe negative space", ok["prompt"])
        self.assertEqual(refused["type"], "refusal")
        self.assertIn("생성해드릴 수 없습니다", refused["message"])

    def test_tst_img_002_relation_image_mock_is_testable(self) -> None:
        result = api_server.relation_image(
            {
                "workTitle": "소나기",
                "characters": [
                    {"name": "소년", "description": "소녀에게 설렘을 느낌"},
                    {"name": "소녀", "description": "소년에게 장난스럽게 관심을 보임"},
                ],
                "relations": [
                    {"from": "소년", "to": "소녀", "relation": "설렘/호감"},
                    {"from": "소녀", "to": "소년", "relation": "장난/관심"},
                ],
            }
        )

        self.assertEqual(result["type"], "mock_image")
        self.assertIn("relationship map", result["prompt"])

    def test_tst_gde_001_guide_contains_required_localization_sections(self) -> None:
        result = api_server.guide(
            {
                "targetCountry": "미국",
                "genre": "현대 로맨스",
                "synopsis": "상처를 감춘 여자와 뒤늦게 진실을 알아가는 남자의 정략결혼 로맨스.",
            }
        )

        self.assertIn("작성 방향", result["htmlReport"])
        self.assertIn("문화 주의사항", result["htmlReport"])
        self.assertIn("플랫폼 규정", result["htmlReport"])
        self.assertGreaterEqual(len(result["sections"]), 3)


if __name__ == "__main__":
    unittest.main()
