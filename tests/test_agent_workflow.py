from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ko_locale_pipeline import ChatbotAgent, InspectionAgent, KoLocalePipeline, PipelineConfig
from ko_locale_pipeline.prompt_loader import load_locale_constraints


class AgentWorkflowTests(unittest.TestCase):
    def _config(self) -> PipelineConfig:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        dataset_path = base / "dataset.json"
        dataset_path.write_text(
            json.dumps(
                [
                    {
                        "id": "US_001",
                        "expression": "have it both ways",
                        "meaning": "gain two benefits at once",
                        "usage": "used when one action brings two gains",
                        "translation_strategy": "idiom",
                        "ko_anchor_expression": ["꿩 먹고 알 먹기"],
                        "ko_expression": ["양쪽 다 챙기다"],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cultural_terms_path = base / "ko_cultural_terms.json"
        cultural_terms_path.write_text(
            json.dumps(
                [
                    {
                        "id": "ko_wedding_cash_gift",
                        "term_ko": "축의금",
                        "terms": ["축의금", "축의금 봉투"],
                        "aliases": [],
                        "category": ["wedding", "money", "etiquette"],
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
        return PipelineConfig(
            locale="ko_en_us",
            rag_dataset_path=dataset_path,
            cultural_terms_path=cultural_terms_path,
            mock=True,
            embedding_cache_dir=base / "cache",
        )

    def test_locale_constraints_load_for_supported_locale(self) -> None:
        constraints = load_locale_constraints("ko_ja")
        self.assertIn("Japanese Cultural Constraints", constraints)
        self.assertIn("JP08", constraints)

    def test_inspection_agent_mock_returns_structured_result(self) -> None:
        agent = InspectionAgent(self._config())
        result = agent.inspect(
            source_text="이건 꿩 먹고 알 먹기야.",
            draft_translation="[MOCK English (US)] 이건 꿩 먹고 알 먹기야.",
            translation_rationale="Mock translator bypassed the model call.",
        )

        self.assertEqual(result.locale, "ko_en_us")
        self.assertEqual(result.recommended_action, "NOTE")
        self.assertEqual(result.problematic_spans, [])
        self.assertIn("mock inspection", result.review_note)

    def test_chatbot_agent_mock_returns_revision_context(self) -> None:
        agent = ChatbotAgent(self._config())
        reply = agent.reply(
            user_message="왜 이렇게 번역했어?",
            source_text="이건 꿩 먹고 알 먹기야.",
            draft_translation="[MOCK English (US)] 이건 꿩 먹고 알 먹기야.",
            reviewed_translation="[MOCK English (US)] 이건 꿩 먹고 알 먹기야.",
        )

        self.assertIn("Mock chatbot", reply.answer)
        self.assertFalse(reply.needs_user_confirmation)

    def test_pipeline_run_with_inspection_returns_agent_workflow(self) -> None:
        pipeline = KoLocalePipeline(self._config())
        result = pipeline.run_with_inspection("이건 꿩 먹고 알 먹기야.")

        self.assertEqual(result.source_text, "이건 꿩 먹고 알 먹기야.")
        self.assertEqual(result.inspection["recommended_action"], "NOTE")
        self.assertIn("translation", result.draft)
        self.assertTrue(result.reviewed_translation)

    def test_pipeline_run_with_inspection_returns_cultural_matches(self) -> None:
        pipeline = KoLocalePipeline(self._config())
        result = pipeline.run_with_inspection("친구 결혼식이라 축의금 봉투를 챙겼다.")

        self.assertEqual(result.cultural_matches[0]["id"], "ko_wedding_cash_gift")
        self.assertIn("한국 결혼식", result.cultural_matches[0]["core_explanation"])


if __name__ == "__main__":
    unittest.main()
