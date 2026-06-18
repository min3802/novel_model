from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.translation import ChatbotAgent, InspectionAgent, PipelineConfig, TranslationMode, TranslationPipeline
from app.translation.agents.translator import Translator
from app.translation.infra.prompt_loader import load_locale_constraints
from backend.services import translation_service


class AgentWorkflowTests(unittest.TestCase):
    def _config(self, locale: str = "ko_en_us", *, quality_mode: str = "standard") -> PipelineConfig:
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
            locale=locale,
            mode=TranslationMode.LEGACY_FULL,
            rag_dataset_path=dataset_path,
            cultural_terms_path=cultural_terms_path,
            quality_mode=quality_mode,
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

        self.assertEqual(result.issues, [])
        self.assertIn("MOCK 검수", result.summary)

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

    def test_chatbot_prompt_includes_work_episode_and_reader_endnotes(self) -> None:
        agent = ChatbotAgent(self._config(locale="ko_ja"))
        prompt = agent._build_prompt(
            user_message="왜 이렇게 번역했어?",
            source_text="문은 기다려 주지 않는다.",
            draft_translation="",
            reviewed_translation="扉は待ってくれない。",
            translation_rationale=json.dumps({"items": [{"reason": "tone"}]}, ensure_ascii=False),
            used_references=[{"source": "문", "target": "扉"}],
            inspection_report={"reviewFindings": [{"code": "webnovel_style"}]},
            reader_endnotes=[{"sourceSpan": "문", "note": "상징적 표현"}],
            work_title="Batch Eval Novel",
            episode_id="17",
            translation_memory=[],
            chat_history=[],
        )

        self.assertIn("Work / Episode:", prompt)
        self.assertIn("Batch Eval Novel", prompt)
        self.assertIn("episodeId: 17", prompt)
        self.assertIn("Reader endnotes (cultural):", prompt)
        self.assertIn("상징적 표현", prompt)
        self.assertIn("webnovel_style", prompt)

    def test_inspect_chat_maps_v3_graph_workflow_context_to_chatbot(self) -> None:
        captured: dict[str, object] = {}

        class FakeChatbot:
            def reply(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    answer="ok",
                    proposed_translation="",
                    change_summary="",
                    needs_user_confirmation=False,
                )

        fake_pipeline = SimpleNamespace(chatbot=FakeChatbot())
        workflow = {
            "title": "17화. 문은 기다려 주지 않는다",
            "episodeId": 163,
            "finalTranslation": "扉は待ってくれない。",
            "translationRationale": {"items": [{"reason": "door metaphor preserved"}]},
            "readerEndnotes": [{"sourceSpan": "문", "note": "상징"}],
            "qaIssues": [{"code": "webnovel_style", "priority": "P2"}],
            "internal": {
                "reviewFindings": [{"code": "webnovel_style", "message": "ok"}],
                "aggregateReview": {"repairRequired": False},
                "idiomNotes": [{"sourceSpan": "문은 기다려 주지 않는다", "targetSpan": "扉は待ってくれない"}],
            },
        }

        with patch.object(translation_service, "_pipeline", return_value=fake_pipeline):
            response = translation_service.inspect_chat(
                {
                    "targetCountry": "JP",
                    "question": "왜 이렇게 번역했어?",
                    "sourceText": "문은 기다려 주지 않는다.",
                    "workflow": workflow,
                    "episodeId": "payload-episode",
                }
            )

        self.assertEqual(response["answer"], "ok")
        self.assertEqual(captured["reviewed_translation"], "扉は待ってくれない。")
        self.assertIn("door metaphor preserved", captured["translation_rationale"])
        self.assertEqual(captured["inspection_report"]["reviewFindings"][0]["code"], "webnovel_style")
        self.assertEqual(captured["inspection_report"]["qaIssues"][0]["code"], "webnovel_style")
        self.assertEqual(captured["used_references"][0]["source"], "문은 기다려 주지 않는다")
        self.assertEqual(captured["reader_endnotes"][0]["note"], "상징")
        self.assertEqual(captured["work_title"], "17화. 문은 기다려 주지 않는다")
        self.assertEqual(captured["episode_id"], "payload-episode")

    def test_inspect_chat_keeps_legacy_workflow_fallback(self) -> None:
        captured: dict[str, object] = {}

        class FakeChatbot:
            def reply(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    answer="legacy",
                    proposed_translation="",
                    change_summary="",
                    needs_user_confirmation=False,
                )

        fake_pipeline = SimpleNamespace(chatbot=FakeChatbot())
        workflow = {
            "source_text": "이건 꿩 먹고 알 먹기야.",
            "draft": {"translation": "have it both ways", "rationale": "idiom equivalent"},
            "inspection": {"summary": "ok", "issues": []},
            "retrievals": [{"item": {"id": "US_001", "ko_anchor_expression": ["꿩 먹고 알 먹기"], "expression": "have it both ways"}, "score": 0.9}],
        }

        with patch.object(translation_service, "_pipeline", return_value=fake_pipeline):
            response = translation_service.inspect_chat(
                {
                    "targetCountry": "US",
                    "question": "왜?",
                    "workflow": workflow,
                    "title": "legacy work",
                    "episodeId": 7,
                }
            )

        self.assertEqual(response["answer"], "legacy")
        self.assertEqual(captured["source_text"], "이건 꿩 먹고 알 먹기야.")
        self.assertEqual(captured["reviewed_translation"], "have it both ways")
        self.assertEqual(captured["translation_rationale"], "idiom equivalent")
        self.assertEqual(captured["inspection_report"], {"summary": "ok", "issues": []})
        self.assertEqual(captured["used_references"][0]["id"], "US_001")
        self.assertEqual(captured["work_title"], "legacy work")
        self.assertEqual(captured["episode_id"], "7")

    def test_pipeline_run_with_inspection_returns_agent_workflow(self) -> None:
        pipeline = TranslationPipeline(self._config())
        result = pipeline.run_with_inspection("이건 꿩 먹고 알 먹기야.")

        self.assertEqual(result.source_text, "이건 꿩 먹고 알 먹기야.")
        self.assertIn("summary", result.inspection)
        self.assertEqual(result.inspection["issues"], [])
        self.assertIn("translation", result.draft)
        self.assertTrue(result.reviewed_translation)
        self.assertEqual(result.metadata["mode"], "legacy_full")
        self.assertEqual(result.metadata["quality_mode"], "standard")
        self.assertEqual(result.metadata["translation_model"], "gpt-5.4-mini")
        self.assertEqual(result.metadata["review_model"], "gpt-5.4-mini")

    def test_quality_mode_env_overrides_flow_into_pipeline_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "WLIGHTER_QUALITY_TRANSLATION_MODEL": "gpt-5.5",
                "WLIGHTER_QUALITY_REVIEW_MODEL": "gpt-5.5",
            },
            clear=False,
        ):
            config = self._config(quality_mode="quality")

        self.assertEqual(config.quality_mode, "quality")
        self.assertEqual(config.translation_model, "gpt-5.5")
        self.assertEqual(config.review_model, "gpt-5.5")


    def test_translator_prompt_includes_profile_and_analysis(self) -> None:
        agent = Translator(self._config())
        prompt = agent._build_prompt(
            source_text="??",
            rag_context="[RAG]",
            translation_profile={"tone": "literary", "do_not": ["flatten voice"]},
            source_analysis={"summary": "scene summary", "scene_functions": ["dialogue"]},
        )

        self.assertIn("[TRANSLATION_PROFILE]", prompt)
        self.assertIn("literary", prompt)
        self.assertIn("[SOURCE_ANALYSIS]", prompt)
        self.assertIn("scene summary", prompt)
        self.assertIn("Japanese translation locale policy", prompt)
        self.assertIn("마른세수", prompt)
        self.assertIn("발등에 불", prompt)
        self.assertIn("팀장", prompt)

        ja_agent = Translator(self._config(locale="ko_ja"))
        self.assertIn("dry face-washing", ja_agent.resources.translator_system_prompt)
        self.assertIn("feet on fire", ja_agent.resources.translator_system_prompt)
        self.assertIn("チーム長", ja_agent.resources.translator_system_prompt)

    def test_inspector_prompt_includes_profile_and_analysis(self) -> None:
        agent = InspectionAgent(self._config())
        prompt = agent._build_prompt(
            source_text="??",
            draft_translation="???",
            translation_rationale="reason",
            translation_memory=[],
            translation_profile={"tone": "literary", "do_not": ["sanitize"]},
            source_analysis={"summary": "scene summary", "emotions": ["anger"]},
        )

        self.assertIn("[TRANSLATION_PROFILE]", prompt)
        self.assertIn("literary", prompt)
        self.assertIn("[SOURCE_ANALYSIS]", prompt)
        self.assertIn("anger", prompt)


    def test_inspection_schema_requires_optional_fields_for_strict_json(self) -> None:
        from app.translation.agents.inspector import INSPECTION_SCHEMA

        issue_schema = INSPECTION_SCHEMA["properties"]["issues"]["items"]
        self.assertIn("review_label", issue_schema["required"])
        self.assertIn("keep_intent", issue_schema["required"])
        self.assertIn("review_label", issue_schema["properties"])
        self.assertIn("keep_intent", issue_schema["properties"])

    def test_inspector_prompt_schema_example_mentions_required_optional_fields(self) -> None:
        from app.translation.agents.inspector import InspectionAgent

        prompt = InspectionAgent(self._config()).prompt_template
        self.assertIn("review_label", prompt)
        self.assertIn("keep_intent", prompt)
        self.assertIn("Required issue fields", prompt)


if __name__ == "__main__":
    unittest.main()
