
from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from app.translation import PipelineConfig, TranslationMode, TranslationPipeline
from app.translation.agents.direct_translator import DirectTranslator
from app.translation.engine.graph_orchestrator import build_v3_graph_literary_package, run_graph_orchestrator
from app.translation.engine.literary_package import GlossaryEntry, WorkMemory
from backend.services.translation_service import translate


class TranslationV3GraphOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = os.environ.copy()
        os.environ["WLIGHTER_MOCK_MODE"] = "true"

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)

    def _pipeline(self) -> TranslationPipeline:
        return TranslationPipeline(PipelineConfig(locale="ko_ja", mode=TranslationMode.V3_LITERARY_PACKAGE, mock=True))

    def test_graph_mode_response_contract(self) -> None:
        result = asdict(self._pipeline().run_v3_literary_package("\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4."))

        self.assertEqual(result["pipeline"], "v3_literary_package")
        self.assertIn("finalTranslation", result)
        self.assertIn("deliveryStatus", result)
        self.assertIn("qaIssues", result)
        self.assertIn("translationRationale", result)
        self.assertIn("authorReviewCards", result)
        self.assertIn("readerEndnotes", result)
        self.assertEqual(result["readerEndnotes"], [])
        self.assertIn("internal", result)
        self.assertIn("graphTrace", result["internal"])
        nodes = [row["node"] for row in result["internal"]["graphTrace"]]
        self.assertIn("repair_or_accept", nodes)
        self.assertIn("final_integrity_check", nodes)
        self.assertIn("graphReviewTrace", result["internal"])
        self.assertEqual(result["internal"]["graphOrchestrator"]["executionFrame"], "langgraph_stategraph")
        self.assertTrue(all("status" in row and "skipped" in row for row in result["internal"]["graphTrace"]))

    def test_graph_trace_records_each_core_node_once(self) -> None:
        state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.", "targetLocale": "ko_ja"},
            },
            max_iterations=1,
            translate_once=lambda strict, attempt, revision_context="": ("\u5f37\u30c9\u30e6\u30f3\u306f\u30c9\u30a2\u3092\u958b\u3051\u305f\u3002", {"delivery_status": "deliverable"}),
        )
        nodes = [row["node"] for row in state["translationPackage"].internal["graphTrace"]]

        for node in [
            "normalize_input",
            "load_work_memory",
            "prepare_translation_context",
            "run_literary_translation",
            "deterministic_precheck",
            "review_voice",
            "review_naturalness",
            "review_cultural",
            "review_glossary",
            "review_integrity",
            "aggregate_review",
            "repair_or_accept",
            "final_integrity_check",
            "build_translation_package",
            "chunk_source_text",
            "detect_annotation_candidates",
            "retrieve_korean_culture_context",
            "write_reader_endnotes",
            "filter_rank_endnotes",
            "align_endnotes_to_final_translation",
        ]:
            self.assertEqual(nodes.count(node), 1, node)

    def test_graph_mode_service_response_contract(self) -> None:
        response = translate(
            {
                "sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
                "targetCountry": "JP",
                "mode": "v3_literary_package",
                "includeInternal": True,
            }
        )

        for key in ["country", "locale", "pipeline", "finalTranslation", "deliveryStatus", "qaIssues", "translationRationale", "authorReviewCards"]:
            self.assertIn(key, response)
        self.assertIn("readerEndnotes", response)
        self.assertEqual(response["readerEndnotes"], [])
        self.assertEqual(response["country"], "JP")
        self.assertEqual(response["locale"], "ko_ja")
        self.assertEqual(response["pipeline"], "v3_literary_package")
        self.assertIn("graphTrace", response["internal"])

    def test_service_defaults_missing_mode_and_pipeline_to_v3_graph(self) -> None:
        response = translate(
            {
                "sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
                "targetCountry": "JP",
                "includeInternal": True,
            }
        )

        self.assertEqual(response["pipeline"], "v3_literary_package")
        self.assertIn("graphTrace", response["internal"])

    def test_graph_mode_is_default_when_env_unset(self) -> None:
        os.environ.pop("TRANSLATION_ORCHESTRATOR", None)
        result = asdict(self._pipeline().run_v3_literary_package("\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4."))

        self.assertEqual(result["pipeline"], "v3_literary_package")
        self.assertIn("graphTrace", result["internal"])
        self.assertIn("repair_or_accept", [row["node"] for row in result["internal"]["graphTrace"]])

    def test_explicit_legacy_orchestrator_env_is_ignored_for_graph_only_v3(self) -> None:
        os.environ["TRANSLATION_ORCHESTRATOR"] = "legacy"
        result = asdict(self._pipeline().run_v3_literary_package("\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4."))

        self.assertEqual(result["pipeline"], "v3_literary_package")
        self.assertIn("graphTrace", result["internal"])
        self.assertIn("repair_or_accept", [row["node"] for row in result["internal"]["graphTrace"]])

    def test_graph_only_entrypoint_calls_graph_orchestrator(self) -> None:
        with patch("app.translation.translation_pipeline.build_v3_graph_literary_package") as graph_entry:
            graph_entry.return_value = build_v3_graph_literary_package("\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.", "ko_ja")
            self._pipeline().run_v3_literary_package("\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.")

        self.assertTrue(graph_entry.called)

    def test_reviewer_fanout_records_diagnostic_only_nodes(self) -> None:
        state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.", "targetLocale": "ko_ja"},
            },
            max_iterations=1,
            translate_once=lambda strict, attempt, revision_context="": ("\u5f37\u30c9\u30e6\u30f3\u306f\u30c9\u30a2\u3092\u958b\u3051\u305f\u3002", {"delivery_status": "deliverable"}),
        )
        internal = state["translationPackage"].internal
        nodes = [row["node"] for row in internal["graphTrace"]]
        for node in ["review_voice", "review_naturalness", "review_cultural", "review_glossary", "review_integrity", "aggregate_review"]:
            self.assertIn(node, nodes)
        reviewer_rows = [row for row in internal["graphTrace"] if str(row["node"]).startswith("review_")]
        self.assertTrue(reviewer_rows)
        self.assertTrue(all(row.get("finalTranslationChanged") is False for row in reviewer_rows))
        self.assertTrue(all(row.get("deliveryStatusChanged") is False for row in reviewer_rows))
        self.assertIn("aggregateReview", internal)

    def test_reviewer_findings_merge_into_aggregate_review(self) -> None:
        source = "\uc228\ud1b5\uc774 \ud2b8\uc774\ub2e4. \uade0\uc5f4\uc744 \ubcf4\uc558\ub2e4."
        draft = (
            "\uc228\ud1b5\uc774 \ud2b8\uc774\ub2e4. "
            "\u5f7c\u306f \uade0\uc5f4\u3092\u898b\u305f\u3002"
            "\u5eca\u4e0b\u306e\u5149\u306f\u9759\u304b\u306b\u63fa\u308c\u305f\u3002"
        )
        with patch("app.translation.engine.graph_orchestrator._mock_literary_translation", return_value=draft):
            state = run_graph_orchestrator(
                {
                    "request": {"sourceText": source, "targetLocale": "ko_ja"},
                },
                max_iterations=1,
            )
        internal = state["translationPackage"].internal
        aggregate = internal["aggregateReview"]
        repair_trace = next(row for row in internal["graphTrace"] if row["node"] == "repair_or_accept")

        self.assertGreater(len(internal["reviewFindings"]), 0)
        self.assertGreater(len(internal["graphReviewTrace"]), 0)
        self.assertGreater(aggregate["issueCount"], 0)
        self.assertEqual(aggregate["maxSeverity"], "P1")
        self.assertTrue(aggregate["repairRequired"])
        self.assertEqual(repair_trace["aggregateIssueCount"], aggregate["issueCount"])
        self.assertEqual(repair_trace["repairRequired"], aggregate["repairRequired"])
        self.assertEqual(repair_trace["repairStrategy"], aggregate["repairStrategy"])

    def test_multiple_reviewer_findings_are_preserved_without_overwrite(self) -> None:
        source = "\uc228\ud1b5\uc774 \ud2b8\uc774\ub2e4. \uade0\uc5f4\uc744 \ubcf4\uc558\ub2e4."
        draft = "\uc228\ud1b5\uc774 \ud2b8\uc774\ub2e4. \u5f7c\u306f \uade0\uc5f4\u3092\u898b\u305f\u3002"
        memory = WorkMemory(
            workId="work-review",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="\uade0\uc5f4", target="\u4e80\u88c2", category="genre_term", priority="hard")
            ],
        )
        with patch("app.translation.engine.graph_orchestrator._mock_literary_translation", return_value=draft):
            state = run_graph_orchestrator(
                {
                    "request": {"sourceText": source, "targetLocale": "ko_ja"},
                    "workMemory": memory,
                },
                max_iterations=1,
            )
        internal = state["translationPackage"].internal
        reviewer_types = {finding["reviewerType"] for finding in internal["reviewFindings"]}
        trace_by_type = {row["reviewerType"]: row for row in internal["graphReviewTrace"]}
        aggregate = internal["aggregateReview"]

        self.assertGreaterEqual(len(internal["reviewFindings"]), 3)
        self.assertIn("naturalness", reviewer_types)
        self.assertIn("glossary", reviewer_types)
        self.assertIn("integrity", reviewer_types)
        for reviewer_type in ["voice", "naturalness", "cultural", "glossary", "integrity"]:
            self.assertIn(reviewer_type, trace_by_type)
        self.assertEqual(trace_by_type["naturalness"]["issueCount"], 1)
        self.assertEqual(trace_by_type["glossary"]["issueCount"], 1)
        self.assertEqual(trace_by_type["integrity"]["issueCount"], 1)
        self.assertEqual(aggregate["reviewerIssueCounts"]["naturalness"], 1)
        self.assertEqual(aggregate["reviewerIssueCounts"]["glossary"], 1)
        self.assertEqual(aggregate["reviewerIssueCounts"]["integrity"], 1)
        self.assertEqual(aggregate["issueCount"], 3)

    def test_aggregate_repair_required_reflects_reviewer_findings(self) -> None:
        source = "\uc228\ud1b5\uc774 \ud2b8\uc774\ub2e4. \uade0\uc5f4\uc744 \ubcf4\uc558\ub2e4."
        draft = "\uc228\ud1b5\uc774 \ud2b8\uc774\ub2e4. \u5f7c\u306f \uade0\uc5f4\u3092\u898b\u305f\u3002"
        memory = WorkMemory(
            workId="work-review",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="\uade0\uc5f4", target="\u4e80\u88c2", category="genre_term", priority="hard")
            ],
        )
        with patch("app.translation.engine.graph_orchestrator._mock_literary_translation", return_value=draft):
            state = run_graph_orchestrator(
                {
                    "request": {"sourceText": source, "targetLocale": "ko_ja"},
                    "workMemory": memory,
                },
                max_iterations=1,
            )
        aggregate = state["translationPackage"].internal["aggregateReview"]
        repair_trace = next(row for row in state["translationPackage"].internal["graphTrace"] if row["node"] == "repair_or_accept")

        self.assertTrue(aggregate["repairRequired"])
        self.assertEqual(aggregate["repairStrategy"], "integrity_guarded_repair")
        self.assertNotEqual(aggregate["repairStrategy"], "accept_or_light_review")
        self.assertTrue(repair_trace["repairRequired"])
        self.assertEqual(repair_trace["repairStrategy"], "integrity_guarded_repair")

    def test_repair_and_final_integrity_authority_trace(self) -> None:
        state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.", "targetLocale": "ko_ja"},
            },
            max_iterations=1,
            translate_once=lambda strict, attempt, revision_context="": ("\u5f37\u30c9\u30e6\u30f3\u306f\u30c9\u30a2\u3092\u958b\u3051\u305f\u3002", {"delivery_status": "deliverable"}),
        )
        trace = state["translationPackage"].internal["graphTrace"]
        repair_rows = [row for row in trace if row["node"] == "repair_or_accept"]
        final_rows = [row for row in trace if row["node"] == "final_integrity_check"]
        self.assertEqual(len(repair_rows), 1)
        self.assertEqual(len(final_rows), 1)
        self.assertFalse(final_rows[0]["finalTranslationChanged"])
        self.assertEqual(final_rows[0]["finalDeliveryStatus"], "deliverable")

    def test_annotation_branch_returns_reader_endnotes_without_touching_translation(self) -> None:
        def candidate_hook(state):
            return [
                {
                    "sourceSpan": "\uc0bc\uac01\uae40\ubc25",
                    "category": "food_culture",
                    "sourceChunkId": "episode-unknown-p1",
                }
            ]

        def retrieval_hook(state):
            return [{"id": "culture_food_003", "category": "food_culture"}]

        def writer_hook(state):
            return [
                {
                    "sourceSpan": "\uc0bc\uac01\uae40\ubc25",
                    "targetSpan": "\u4e09\u89d2\u30ad\u30f3\u30d1",
                    "category": "food_culture",
                    "note": "\ud14c\uc2a4\ud2b8 \ubb38\ud654 \ubbf8\uc8fc",
                    "sourceChunkId": "episode-unknown-p1",
                    "retrievalRefs": ["culture_food_003"],
                    "confidence": "high",
                }
            ]

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\uc0bc\uac01\uae40\ubc25\uc744 \uba39\uc5c8\ub2e4.", "targetLocale": "ko_ja"},
                "annotationCandidateHook": candidate_hook,
                "annotationRetrievalHook": retrieval_hook,
                "readerEndnoteWriterHook": writer_hook,
            },
            max_iterations=1,
            translate_once=lambda strict, attempt, revision_context="": ("\u4e09\u89d2\u30ad\u30f3\u30d1\u3092\u98df\u3079\u305f\u3002", {"delivery_status": "deliverable"}),
        )
        package = state["translationPackage"]

        self.assertEqual(package.finalTranslation, "\u4e09\u89d2\u30ad\u30f3\u30d1\u3092\u98df\u3079\u305f\u3002")
        self.assertEqual(len(package.readerEndnotes), 1)
        self.assertNotIn(package.readerEndnotes[0]["note"], package.finalTranslation)
        annotation_rows = [
            row
            for row in state["graphTrace"]
            if row["node"]
            in {
                "chunk_source_text",
                "detect_annotation_candidates",
                "retrieve_korean_culture_context",
                "write_reader_endnotes",
                "filter_rank_endnotes",
                "align_endnotes_to_final_translation",
            }
        ]
        self.assertFalse(any(row.get("finalTranslationChanged") for row in annotation_rows))
        self.assertEqual(package.internal["annotationTrace"]["keptCount"], 1)

    def test_blocked_translation_aligns_endnotes_before_single_package_build(self) -> None:
        source = (
            "\uc55e\uc740 \uc774\ubbf8 \uc5f4\ub824 \uc788\uc5c8\ub2e4. "
            "\ubb38\ud2c8 \uc0ac\uc774\ub85c \ubd89\uc740 \ube5b\uc774 \uc0c8\uc5b4 \ub098\uc654\ub2e4."
        )

        def writer_hook(state):
            return [
                {
                    "sourceSpan": "\ubb38\ud2c8",
                    "targetSpan": "\u9580\u67a0",
                    "category": "setting",
                    "note": "\ubb38\ud2c8 \uc124\uba85",
                    "sourceChunkId": "episode-unknown-p1",
                    "retrievalRefs": [],
                    "confidence": "medium",
                }
            ]

        def translate_once(strict, attempt, revision_context=""):
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
                "annotationCandidateHook": lambda state: [{"sourceSpan": "\ubb38\ud2c8", "category": "setting", "sourceChunkId": "episode-unknown-p1"}],
                "annotationRetrievalHook": lambda state: [{"id": "setting_001", "category": "setting"}],
                "readerEndnoteWriterHook": writer_hook,
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        nodes = [row["node"] for row in package.internal["graphTrace"]]

        self.assertEqual(package.deliveryStatus, "blocked_translation_integrity")
        self.assertEqual(package.finalTranslation, "")
        self.assertEqual(nodes.count("align_endnotes_to_final_translation"), 1)
        self.assertEqual(nodes.count("build_translation_package"), 1)
        self.assertEqual(package.readerEndnotes, [])
        self.assertFalse(any((note.get("note") or "") in package.finalTranslation for note in package.readerEndnotes))

    def test_graph_hangul_body_residue_gets_retranslation_retry(self) -> None:
        calls = []
        korean_residue = "\uac15\ub3c4\uc724\uc740 \ubaa8\ub2c8\ud130\ub97c \ubcf4\uc558\ub2e4. \uc0ac\ubb34\uc2e4\uc740 \uc870\uc6a9\ud588\ub2e4."

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            if len(calls) < 3:
                return korean_residue, {"delivery_status": "deliverable"}
            return "\u5f37\u30c9\u30e6\u30f3\u306f\u30e2\u30cb\u30bf\u30fc\u3092\u898b\u3064\u3081\u305f\u3002\u4e8b\u52d9\u6240\u306f\u9759\u304b\u3060\u3063\u305f\u3002", {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": korean_residue, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.qaIssues, [])
        self.assertEqual(len(calls), 3)
        self.assertIn("GRAPH CLEAN FULL TRANSLATOR RETRY", calls[-1]["revisionContext"])
        self.assertIn("Japanese only", calls[-1]["revisionContext"])
        self.assertTrue(any(row.get("action") == "Graph Clean Full Translator Retry" for row in package.internal["iterations"]))
        self.assertEqual(package.internal["graphRepairTrace"][0]["action"], "clean_full_translator_retry")

        trace = package.internal["graphRepairTrace"][0]
        self.assertEqual(trace["hangulResidueSpanCount"], 0)
        self.assertEqual(trace["hangulResidueCategory"], "none")
        self.assertTrue(trace["cleanTranslatorRetryAttempted"])
        self.assertTrue(trace["cleanTranslatorRetrySucceeded"])
        self.assertEqual(trace["integrityFailureType"], "prose_residue")
        self.assertFalse(trace["sourceCopyDetected"])
        self.assertFalse(trace["proseResidueDetected"])
        self.assertEqual(trace["failureCategory"], "none")
        self.assertEqual(trace["finalDeliveryStatus"], "deliverable")

    def test_graph_hangul_body_residue_retry_failure_is_integrity_not_safety(self) -> None:
        calls = []
        korean_residue = "\ud575\uc2ec \uade0\uc5f4\ubb38 \uc55e\uc740 \uc774\ubbf8 \uc9c0\uc625\ucc98\ub7fc \ubb38\ud2c8 \uc0ac\uc774\ub85c \ub0a8\uc558\ub2e4."

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            return korean_residue, {
                "delivery_status": "blocked_translation_safety",
                "user_visible_error_code": "translation_safety_failed",
                "source_copy_status": "fail",
                "residual_hangul_status": "fail",
            }

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": korean_residue, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "blocked_translation_integrity")
        self.assertEqual(package.userVisibleErrorCode, "translation_integrity_failed")
        self.assertEqual(package.finalTranslation, "")
        self.assertNotEqual(package.deliveryStatus, "blocked_translation_safety")
        self.assertTrue(any(issue["code"] == "hangul_residue_integrity" for issue in package.qaIssues))
        self.assertEqual(len(calls), 4)
        self.assertIn("GRAPH STRICT CLEAN FINAL FALLBACK", calls[-1]["revisionContext"])
        trace = package.internal["graphRepairTrace"][0]
        self.assertEqual(trace["hangulResidueCategory"], "prose_residue")
        self.assertTrue(trace["cleanTranslatorRetryAttempted"])
        self.assertFalse(trace["cleanTranslatorRetrySucceeded"])
        self.assertTrue(trace["strictCleanFallbackAttempted"])
        self.assertFalse(trace["strictCleanFallbackSucceeded"])
        self.assertEqual(trace["finalFallbackAttemptCount"], 1)
        self.assertIn(trace["integrityFailureType"], {"prose_residue", "source_copy_and_prose_residue"})
        self.assertEqual(trace["failureCategory"], "integrity")
        self.assertEqual(trace["finalDeliveryStatus"], "blocked_translation_integrity")

    def test_graph_source_copy_retry_result_is_not_success(self) -> None:
        calls = []
        source = (
            "\ud575\uc2ec \uade0\uc5f4\ubb38 \uc55e\uc740 \uc774\ubbf8 \uc5f4\ub824 \uc788\uc5c8\ub2e4. "
            "\ubb38\ud2c8 \uc0ac\uc774\ub85c \ubd89\uc740 \ube5b\uc774 \uc0c8\uc5b4 \ub098\uc654\ub2e4. "
            "\uadf8\ub294 \ud55c \ubc1c \ub4a4\ub85c \ubb3c\ub7ec\uc130\ub2e4."
        )

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "blocked_translation_integrity")
        self.assertEqual(package.userVisibleErrorCode, "translation_integrity_failed")
        self.assertEqual(package.finalTranslation, "")
        self.assertNotEqual(package.deliveryStatus, "blocked_translation_safety")
        self.assertIn("GRAPH STRICT CLEAN FINAL FALLBACK", calls[-1]["revisionContext"])
        trace = package.internal["graphRepairTrace"][0]
        self.assertTrue(trace["sourceCopyDetected"])
        self.assertTrue(trace["cleanTranslatorRetryAttempted"])
        self.assertFalse(trace["cleanTranslatorRetrySucceeded"])
        self.assertTrue(trace["strictCleanFallbackAttempted"])
        self.assertFalse(trace["strictCleanFallbackSucceeded"])
        self.assertEqual(trace["finalFallbackAttemptCount"], 1)
        self.assertIn(trace["integrityFailureType"], {"source_copy", "source_copy_and_prose_residue"})
        self.assertGreater(trace["residualHangulRatio"], 0.2)

    def test_graph_clean_retry_source_copy_failure_strict_fallback_success(self) -> None:
        calls = []
        source = (
            "\uc55e\uc740 \uc774\ubbf8 \uc5f4\ub824 \uc788\uc5c8\ub2e4. "
            "\uadf8\ub294 \uc870\uc6a9\ud788 \ub2e4\uc74c \ubb38\uc744 \ud655\uc778\ud588\ub2e4."
        )
        fallback = (
            "\u6249\u306f\u3059\u3067\u306b\u958b\u3044\u3066\u3044\u305f\u3002"
            "\u5f7c\u306f\u9759\u304b\u306b\u6b21\u306e\u6249\u3092\u78ba\u304b\u3081\u305f\u3002"
        )
        debug_artifact = {
            "debugArtifactDir": "reports/debug/episode_017",
            "rawOutputPath": "reports/debug/episode_017/strict_clean_fallback_raw_output.txt",
            "parsedCandidatePath": "reports/debug/episode_017/strict_clean_fallback_parsed_candidate.txt",
            "metricsPath": "reports/debug/episode_017/strict_clean_fallback_metrics.json",
        }

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            if "GRAPH STRICT CLEAN FINAL FALLBACK" in revision_context:
                return fallback, {"delivery_status": "deliverable", "debug_artifact": debug_artifact}
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        trace = package.internal["graphRepairTrace"][0]
        repair_trace = next(row for row in package.internal["graphTrace"] if row["node"] == "repair_or_accept")

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.qaIssues, [])
        self.assertEqual(package.finalTranslation, fallback)
        self.assertTrue(trace["strictCleanFallbackAttempted"])
        self.assertTrue(trace["strictCleanFallbackSucceeded"])
        self.assertFalse(trace["strictCleanFallbackSourceCopyDetected"])
        self.assertEqual(trace["strictCleanFallbackRawOutputPath"], debug_artifact["rawOutputPath"])
        self.assertEqual(trace["strictCleanFallbackParsedCandidatePath"], debug_artifact["parsedCandidatePath"])
        self.assertEqual(trace["strictCleanFallbackMetricsPath"], debug_artifact["metricsPath"])
        self.assertEqual(trace["finalFallbackAttemptCount"], 1)
        self.assertTrue(repair_trace["strictCleanFallbackAttempted"])
        self.assertTrue(repair_trace["strictCleanFallbackSucceeded"])
        self.assertNotRegex(package.finalTranslation, r"[\uac00-\ud7a3]")

    def test_graph_strict_fallback_preserves_bracket_blocks_and_endnotes_contract(self) -> None:
        source = (
            "[STATUS: \uacbd\uace0]\n"
            "\ubb38\uc740 \uc5f4\ub824 \uc788\uc5c8\uace0, \uadf8\ub294 \uc548\uc73c\ub85c \ub4e4\uc5b4\uac14\ub2e4."
        )
        fallback = (
            "[STATUS: \u8b66\u544a]\n"
            "\u6249\u306f\u958b\u3044\u3066\u304a\u308a\u3001\u5f7c\u306f\u4e2d\u3078\u8db3\u3092\u9032\u3081\u305f\u3002"
        )

        def translate_once(strict, attempt, revision_context=""):
            if "GRAPH STRICT CLEAN FINAL FALLBACK" in revision_context:
                return fallback, {"delivery_status": "deliverable"}
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
                "readerEndnoteWriterHook": lambda _state: [{"note": "reader note must stay separate"}],
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        trace = package.internal["graphRepairTrace"][0]

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertTrue(trace["strictCleanFallbackSucceeded"])
        self.assertEqual(package.finalTranslation.count("["), source.count("["))
        self.assertEqual(package.finalTranslation.count("]"), source.count("]"))
        self.assertFalse(any((note.get("note") or "") in package.finalTranslation for note in package.readerEndnotes))

    def test_graph_strict_fallback_not_used_for_normal_deliverable(self) -> None:
        final = (
            "\u6249\u306f\u9759\u304b\u306b\u958b\u304d\u3001"
            "\u5f7c\u306f\u3072\u3068\u3064\u606f\u3092\u3064\u3044\u305f\u3002"
        )

        def translate_once(strict, attempt, revision_context=""):
            return final, {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\ubb38\uc774 \uc5f4\ub838\uace0, \uadf8\ub294 \uc228\uc744 \ub0b4\uc26c\uc5c8\ub2e4.", "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.internal["graphRepairTrace"], [])

    def test_graph_clean_retry_success_recovers_source_copy(self) -> None:
        calls = []
        source = (
            "\uc55e\uc740 \uc774\ubbf8 \uc9c0\uc625\ucc98\ub7fc \ubd89\uc5b4\uc838 \uc788\uc5c8\ub2e4. "
            "\uadf8\ub294 \uc9e7\uac8c \uc228\uc744 \ub4e4\uc774\uc26c\uace0 \uac80\uc744 \ub4e4\uc5c8\ub2e4. "
            "\ubc14\ub78c\uc774 \ubcf5\ub3c4 \ub05d\uc5d0\uc11c \ub0ae\uac8c \uc6b8\uc5c8\ub2e4."
        )

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            if len(calls) < 3:
                return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}
            return "\u76ee\u306e\u524d\u306f\u3059\u3067\u306b\u5730\u7344\u306e\u3088\u3046\u306b\u8d64\u304f\u67d3\u307e\u3063\u3066\u3044\u305f\u3002\u5f7c\u306f\u77ed\u304f\u606f\u3092\u5438\u3044\u3001\u5263\u3092\u63e1\u3063\u305f\u3002", {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.qaIssues, [])
        self.assertTrue(package.finalTranslation)
        trace = package.internal["graphRepairTrace"][0]
        self.assertIn(trace["integrityFailureType"], {"source_copy", "source_copy_and_prose_residue"})
        self.assertFalse(trace["sourceCopyDetected"])
        self.assertTrue(trace["cleanTranslatorRetrySucceeded"])
        self.assertFalse(trace["strictCleanFallbackAttempted"])
        self.assertEqual(trace["finalDeliveryStatus"], "deliverable")

    def test_graph_small_prose_residue_after_clean_retry_gets_targeted_repair(self) -> None:
        calls = []
        source = (
            "\uc544\uc774\ub294 \ud68c\uc0c9 \uc720\ub9ac\ubb38 \uc55e\uc5d0 \uba48\ucdb0 \uc130\ub2e4. "
            "\uc791\uc740 \uacbd\uace0\ub4f1\uc774 \ub450 \ubc88 \uae5c\ube61\uc600\ub2e4."
        )
        small_residue = (
            "\u5c11\u5e74\u306f\u7070\u8272\u306e\u30ac\u30e9\u30b9\u6249\u306e\u524d\u3067\u8db3\u3092\u6b62\u3081\u305f\u3002"
            "\u5468\u56f2\u306e\u7a7a\u6c17\u306f\u9759\u304b\u306b\u6c88\u307f\u3001\u5f7c\u306e\u606f\u3060\u3051\u304c\u5eca\u4e0b\u306b\u6b8b\u3063\u305f\u3002"
            "\uc794"
            "\u5c0f\u3055\u306a\u8b66\u544a\u706f\u304c\u4e8c\u5ea6\u307e\u305f\u305f\u304d\u3001\u7269\u8a9e\u306e\u30c6\u30f3\u30dd\u3092\u5d29\u3055\u305a\u306b\u7dca\u5f35\u3092\u6dfb\u3048\u305f\u3002"
        )
        repaired = (
            "\u5c11\u5e74\u306f\u7070\u8272\u306e\u30ac\u30e9\u30b9\u6249\u306e\u524d\u3067\u8db3\u3092\u6b62\u3081\u305f\u3002"
            "\u5468\u56f2\u306e\u7a7a\u6c17\u306f\u9759\u304b\u306b\u6c88\u307f\u3001\u5f7c\u306e\u606f\u3060\u3051\u304c\u5eca\u4e0b\u306b\u6b8b\u3063\u305f\u3002"
            "\u304b\u3059\u304b\u306a\u6c17\u914d\u304c\u6b8b\u308a\u3001"
            "\u5c0f\u3055\u306a\u8b66\u544a\u706f\u304c\u4e8c\u5ea6\u307e\u305f\u305f\u304d\u3001\u7269\u8a9e\u306e\u30c6\u30f3\u30dd\u3092\u5d29\u3055\u305a\u306b\u7dca\u5f35\u3092\u6dfb\u3048\u305f\u3002"
        )

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                return repaired, {"delivery_status": "deliverable"}
            if "GRAPH CLEAN FULL TRANSLATOR RETRY" in revision_context:
                return small_residue, {"delivery_status": "deliverable"}
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        traces = package.internal["graphRepairTrace"]
        targeted = [row for row in traces if row.get("action") == "targeted_small_prose_residue_repair"]

        self.assertTrue(targeted)
        self.assertTrue(traces[0]["smallProseResidueDetected"])
        self.assertTrue(targeted[0]["targetedRepairAttempted"])
        self.assertTrue(targeted[0]["targetedRepairSucceeded"])
        self.assertEqual(targeted[0]["residualHangulCharCountAfter"], 0)
        self.assertFalse(any(row.get("strictCleanFallbackAttempted") for row in traces))
        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.qaIssues, [])
        self.assertEqual(package.finalTranslation, repaired)
        self.assertIn("GRAPH TARGETED SMALL PROSE RESIDUE REPAIR", calls[-1]["revisionContext"])

    def test_graph_korean_noun_japanese_particle_residue_is_not_name_residue(self) -> None:
        calls = []
        source = (
            "\ud575\uc2ec \uade0\uc5f4\ubb38\uc744 \ud655\uc778\ud55c \ub2e4\uc74c\ub0a0, "
            "\uadf8\ub294 \ub2e4\uc2dc \ubb38 \uc55e\uc5d0 \uc130\ub2e4."
        )
        small_residue = (
            "\ud575\uc2ec \uade0\uc5f4\ubb38\u3092\u78ba\u8a8d\u3057\u305f\u7fcc\u65e5\u3001"
            "\u5f7c\u306f\u307e\u305f\u9580\u306e\u524d\u306b\u7acb\u3063\u305f\u3002"
        )
        repaired = (
            "\u6838\u5fc3\u306e\u4e80\u88c2\u9580\u3092\u78ba\u8a8d\u3057\u305f\u7fcc\u65e5\u3001"
            "\u5f7c\u306f\u307e\u305f\u9580\u306e\u524d\u306b\u7acb\u3063\u305f\u3002"
        )
        japanese_tail = (
            "\u5eca\u4e0b\u306e\u5149\u306f\u9759\u304b\u306b\u63fa\u308c\u3001\u5f7c\u306e\u8db3\u97f3\u3060\u3051\u304c\u9577\u304f\u97ff\u3044\u305f\u3002"
            "\u898b\u5f35\u308a\u306e\u9b54\u6cd5\u706f\u306f\u9752\u304f\u77ac\u304d\u3001\u6249\u306e\u5965\u304b\u3089\u4e7e\u3044\u305f\u98a8\u304c\u6f0f\u308c\u305f\u3002"
            "\u8a18\u9332\u4fc2\u306f\u58f0\u3092\u6f5c\u3081\u3001\u6b21\u306e\u5831\u544a\u66f8\u3092\u4e21\u624b\u3067\u62b1\u3048\u76f4\u3057\u305f\u3002"
            "\u8ab0\u3082\u7b11\u308f\u305a\u3001\u8584\u3044\u7dca\u5f35\u3060\u3051\u304c\u7815\u3051\u305f\u77f3\u5e8a\u306e\u4e0a\u306b\u6b8b\u3063\u305f\u3002"
            "\u305d\u308c\u3067\u3082\u5f7c\u306f\u547c\u5438\u3092\u6574\u3048\u3001\u6b21\u306e\u78ba\u8a8d\u624b\u9806\u3078\u3068\u8996\u7dda\u3092\u79fb\u3057\u305f\u3002"
        )
        small_residue += japanese_tail
        repaired += japanese_tail

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                return repaired, {"delivery_status": "deliverable"}
            return small_residue, {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        traces = package.internal["graphRepairTrace"]
        targeted = [row for row in traces if row.get("action") == "targeted_small_prose_residue_repair"]
        issue = next(issue for issue in package.internal["iterations"][0]["critique"] if issue.get("code") == "hangul_residue_integrity")
        initial_spans = (issue.get("details") or {}).get("spans") or []

        self.assertTrue(targeted)
        self.assertFalse(any(span.get("personNameRisk") for span in initial_spans))
        self.assertTrue(any(span.get("residueCategory") == "genre_term_residue" for span in initial_spans))
        self.assertEqual(targeted[0]["hangulResidueCategory"], "genre_term_residue")
        self.assertTrue(targeted[0]["smallGenreTermResidueDetected"])
        self.assertTrue(targeted[0]["nameResidueFalsePositiveAvoided"])
        self.assertTrue(targeted[0]["targetedRepairAttempted"])
        self.assertTrue(targeted[0]["targetedRepairSucceeded"])
        self.assertFalse(any(row.get("strictCleanFallbackAttempted") for row in traces))
        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.qaIssues, [])
        self.assertEqual(package.finalTranslation, repaired)
        self.assertIn("GRAPH TARGETED SMALL PROSE RESIDUE REPAIR", calls[-1]["revisionContext"])

    def test_graph_targeted_repair_failure_fallback_success_is_deliverable(self) -> None:
        calls = []
        source = (
            "\ubb38\uc740 \uc870\uc6a9\ud788 \uc5f4\ub838\uace0, \uadf8\ub294 \ub0ae\uac8c \uc228\uc744 \ub0b4\uc26c\uc5c8\ub2e4. "
            "\ubc14\ub78c\uc774 \ub4a4\uc5d0\uc11c \uc2a4\uccd0 \uc9c0\ub098\uac14\ub2e4."
        )
        small_residue = (
            "\u6249\u306f\u9759\u304b\u306b\u958b\u304d\u3001\u5f7c\u306f\u4f4e\u304f\u606f\u3092\u5410\u3044\u305f\u3002"
            "\u9060\u304f\u3067\u5149\u304c\u63fa\u308c\u3001\u8db3\u5143\u306e\u5f71\u304c\u3086\u3063\u304f\u308a\u4f38\u3073\u3066\u3044\u304f\u3002"
            "\uc794"
            "\u80cc\u5f8c\u3092\u98a8\u304c\u304b\u3059\u3081\u3001\u5f7c\u306f\u3082\u3046\u4e00\u5ea6\u524d\u3092\u898b\u305f\u3002"
            "\u7269\u8a9e\u306e\u547c\u5438\u3092\u4fdd\u3061\u306a\u304c\u3089\u3001\u5834\u9762\u306e\u7dca\u5f35\u306f\u9759\u304b\u306b\u7d9a\u3044\u305f\u3002"
        )
        repaired = small_residue.replace("\uc794", "\u304b\u3059\u304b\u306a\u4f59\u97fb\u3092\u6b8b\u3057\u3001")

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            if "GRAPH TARGETED SMALL PROSE RESIDUE FALLBACK" in revision_context:
                return repaired, {"delivery_status": "deliverable"}
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                return small_residue, {"delivery_status": "deliverable"}
            if "GRAPH CLEAN FULL TRANSLATOR RETRY" in revision_context:
                return small_residue, {"delivery_status": "deliverable"}
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        targeted = [row for row in package.internal["graphRepairTrace"] if row.get("action") == "targeted_small_prose_residue_repair"]
        repair_trace = [row for row in package.internal["graphTrace"] if row["node"] == "repair_or_accept"][-1]

        self.assertTrue(targeted)
        self.assertFalse(targeted[0]["targetedRepairSucceeded"])
        self.assertTrue(targeted[0]["targetedRepairFallbackAttempted"])
        self.assertTrue(targeted[0]["targetedRepairFallbackSucceeded"])
        self.assertEqual(targeted[0]["targetedRepairFallbackFailedReason"], "")
        self.assertEqual(targeted[0]["targetedRepairFallbackResidualHangulRatioAfter"], 0.0)
        self.assertEqual(targeted[0]["finalFallbackAttemptCount"], 1)
        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.qaIssues, [])
        self.assertEqual(package.finalTranslation, repaired)
        self.assertTrue(repair_trace["targetedRepairFallbackAttempted"])
        self.assertTrue(repair_trace["targetedRepairFallbackSucceeded"])
        self.assertFalse(any(row.get("strictCleanFallbackAttempted") for row in targeted))
        self.assertEqual(sum(1 for row in calls if "GRAPH TARGETED SMALL PROSE RESIDUE FALLBACK" in row["revisionContext"]), 1)
        self.assertNotRegex(package.finalTranslation, r"[\uac00-\ud7a3]")

    def test_graph_true_name_residue_does_not_enter_small_genre_repair(self) -> None:
        calls = []
        source = "\uac15\ub3c4\uc724\uc740 \ub2e4\uc2dc \ubb38 \uc55e\uc5d0 \uc130\ub2e4."
        name_residue = "\uac15\ub3c4\uc724\u306f\u307e\u305f\u9580\u306e\u524d\u306b\u7acb\u3063\u305f\u3002"
        memory = WorkMemory(
            workId="work-name",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard")],
        )

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            return name_residue, {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja", "workMemory": memory},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertIn("\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f", package.finalTranslation)
        self.assertFalse(any(row.get("action") == "targeted_small_prose_residue_repair" for row in package.internal["graphRepairTrace"]))
        self.assertFalse(any("GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in row["revisionContext"] for row in calls))

    def test_graph_small_prose_residue_targeted_repair_failure_is_not_safety(self) -> None:
        calls = []
        source = (
            "\ubb38\uc740 \uc870\uc6a9\ud788 \uc5f4\ub838\uace0, \uadf8\ub294 \ub0ae\uac8c \uc228\uc744 \ub0b4\uc26c\uc5c8\ub2e4. "
            "\ubc14\ub78c\uc774 \ub4a4\uc5d0\uc11c \uc2a4\uccd0 \uc9c0\ub098\uac14\ub2e4."
        )
        small_residue = (
            "\u6249\u306f\u9759\u304b\u306b\u958b\u304d\u3001\u5f7c\u306f\u4f4e\u304f\u606f\u3092\u5410\u3044\u305f\u3002"
            "\u9060\u304f\u3067\u5149\u304c\u63fa\u308c\u3001\u8db3\u5143\u306e\u5f71\u304c\u3086\u3063\u304f\u308a\u4f38\u3073\u3066\u3044\u304f\u3002"
            "\uc794"
            "\u80cc\u5f8c\u3092\u98a8\u304c\u304b\u3059\u3081\u3001\u5f7c\u306f\u3082\u3046\u4e00\u5ea6\u524d\u3092\u898b\u305f\u3002"
            "\u7269\u8a9e\u306e\u547c\u5438\u3092\u4fdd\u3061\u306a\u304c\u3089\u3001\u5834\u9762\u306e\u7dca\u5f35\u306f\u9759\u304b\u306b\u7d9a\u3044\u305f\u3002"
        )
        failed_repair = small_residue

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            if "GRAPH TARGETED SMALL PROSE RESIDUE FALLBACK" in revision_context:
                return small_residue, {"delivery_status": "deliverable"}
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                return failed_repair, {"delivery_status": "deliverable"}
            if "GRAPH CLEAN FULL TRANSLATOR RETRY" in revision_context:
                return small_residue, {"delivery_status": "deliverable"}
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        targeted = [row for row in package.internal["graphRepairTrace"] if row.get("action") == "targeted_small_prose_residue_repair"]

        self.assertTrue(targeted)
        self.assertFalse(targeted[0]["targetedRepairSucceeded"])
        self.assertEqual(targeted[0]["targetedRepairFailedReason"], "hangul_residue_remaining")
        self.assertTrue(targeted[0]["targetedRepairFallbackAttempted"])
        self.assertFalse(targeted[0]["targetedRepairFallbackSucceeded"])
        self.assertEqual(targeted[0]["targetedRepairFallbackFailedReason"], "hangul_residue_remaining")
        self.assertEqual(targeted[0]["finalFallbackAttemptCount"], 1)
        self.assertEqual(package.deliveryStatus, "qa_warning")
        self.assertNotEqual(package.deliveryStatus, "blocked_translation_safety")
        self.assertNotEqual(package.userVisibleErrorCode, "translation_safety_failed")

    def test_graph_targeted_repair_preserves_reviewer_authority_and_unrelated_text(self) -> None:
        source = (
            "\uc2dc\uc2a4\ud15c \ucc3d\uc774 \uba3c\uc800 \ub5a0\uc62c\ub790\ub2e4. "
            "\uadf8\ub294 \uc870\uc6a9\ud788 \ub2e4\uc74c \ubb38\uc7a5\uc744 \uc77d\uc5c8\ub2e4."
        )
        small_residue = (
            "[STATUS: OK]\n"
            "\u3053\u306e\u884c\u306f\u305d\u306e\u307e\u307e\u6b8b\u308b\u3002"
            "\u5f7c\u306f\u9759\u304b\u306b\u6b21\u306e\u6587\u3092\u8aad\u3093\u3060\u3002"
            "\uc794"
            "\u7269\u8a9e\u306f\u307e\u3060\u7d42\u308f\u3089\u306a\u3044\u3002"
            "\u5eca\u4e0b\u306e\u5149\u306f\u8584\u304f\u63fa\u308c\u3001\u5f7c\u306e\u8996\u7dda\u306f\u6b21\u306e\u884c\u3078\u9759\u304b\u306b\u6d41\u308c\u305f\u3002"
        )
        repaired = (
            "[STATUS: OK]\n"
            "\u3053\u306e\u884c\u306f\u305d\u306e\u307e\u307e\u6b8b\u308b\u3002"
            "\u5f7c\u306f\u9759\u304b\u306b\u6b21\u306e\u6587\u3092\u8aad\u3093\u3060\u3002"
            "\u304b\u3059\u304b\u306a\u4f59\u97fb\u304c\u6b8b\u308a\u3001"
            "\u7269\u8a9e\u306f\u307e\u3060\u7d42\u308f\u3089\u306a\u3044\u3002"
            "\u5eca\u4e0b\u306e\u5149\u306f\u8584\u304f\u63fa\u308c\u3001\u5f7c\u306e\u8996\u7dda\u306f\u6b21\u306e\u884c\u3078\u9759\u304b\u306b\u6d41\u308c\u305f\u3002"
        )

        def translate_once(strict, attempt, revision_context=""):
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                return repaired, {"delivery_status": "deliverable"}
            if "GRAPH CLEAN FULL TRANSLATOR RETRY" in revision_context:
                return small_residue, {"delivery_status": "deliverable"}
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        reviewer_rows = [row for row in package.internal["graphTrace"] if str(row["node"]).startswith("review_")]
        repair_rows = [row for row in package.internal["graphTrace"] if row["node"] == "repair_or_accept"]

        self.assertTrue(all(row.get("finalTranslationChanged") is False for row in reviewer_rows))
        self.assertTrue(all(row.get("deliveryStatusChanged") is False for row in reviewer_rows))
        self.assertTrue(repair_rows[0]["finalTranslationChanged"])
        self.assertIn("[STATUS: OK]", package.finalTranslation)
        self.assertIn("\u3053\u306e\u884c\u306f\u305d\u306e\u307e\u307e\u6b8b\u308b\u3002", package.finalTranslation)
        self.assertEqual(package.finalTranslation.count("["), small_residue.count("["))
        self.assertEqual(package.finalTranslation.count("]"), small_residue.count("]"))

    def test_debug_capture_off_does_not_create_model_output_files(self) -> None:
        (Path.cwd() / "reports").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "reports") as tmp:
            debug_dir = Path(tmp) / "debug" / "episode_001"
            pipeline = DirectTranslator(PipelineConfig(locale="ko_ja", mock=True))

            pipeline.translate_once(
                "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
                debug_capture={"enabled": False, "artifactDir": str(debug_dir), "attemptName": "initial_translation"},
            )

            self.assertFalse(debug_dir.exists())

    def test_debug_capture_on_writes_retry_artifact_files(self) -> None:
        (Path.cwd() / "reports").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "reports") as tmp:
            debug_dir = Path(tmp) / "debug" / "episode_001"
            pipeline = DirectTranslator(PipelineConfig(locale="ko_ja", mock=True))

            result = pipeline.translate_once(
                "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
                memory_context="[GRAPH CLEAN FULL TRANSLATOR RETRY]\n- Output Japanese only.",
                strict_locale_retry=True,
                retry_attempt=1,
                debug_capture={
                    "enabled": True,
                    "artifactDir": str(debug_dir),
                    "attemptName": "graph_clean_full_translator_retry",
                    "promptPreview": "[GRAPH CLEAN FULL TRANSLATOR RETRY]\n- Output Japanese only.",
                },
            )

            artifact = result.metadata["debug_artifact"]
            for key in ["rawOutputPath", "parsedCandidatePath", "metricsPath", "promptPreviewPath", "promptMetadataPath"]:
                self.assertTrue(Path(artifact[key]).exists(), key)
            metrics = json.loads(Path(artifact["metricsPath"]).read_text(encoding="utf-8"))
            self.assertEqual(metrics["attemptName"], "graph_clean_full_translator_retry")
            self.assertIn("raw_model_response_length", metrics)
            self.assertIn("source_copy_suspected", metrics)

    def test_debug_capture_on_writes_strict_fallback_artifact_files(self) -> None:
        (Path.cwd() / "reports").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "reports") as tmp:
            debug_dir = Path(tmp) / "debug" / "episode_017"
            pipeline = DirectTranslator(PipelineConfig(locale="ko_ja", mock=True))

            result = pipeline.translate_once(
                "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
                memory_context="[GRAPH STRICT CLEAN FINAL FALLBACK]\n- Output only the complete Japanese translation.",
                strict_locale_retry=True,
                retry_attempt=3,
                debug_capture={
                    "enabled": True,
                    "artifactDir": str(debug_dir),
                    "attemptName": "strict_clean_fallback",
                    "promptPreview": "[GRAPH STRICT CLEAN FINAL FALLBACK]\n- Output only the complete Japanese translation.",
                },
            )

            artifact = result.metadata["debug_artifact"]
            for key in ["rawOutputPath", "parsedCandidatePath", "metricsPath", "promptPreviewPath", "promptMetadataPath"]:
                self.assertTrue(Path(artifact[key]).exists(), key)
                self.assertIn("strict_clean_fallback", Path(artifact[key]).name)
            metrics = json.loads(Path(artifact["metricsPath"]).read_text(encoding="utf-8"))
            self.assertEqual(metrics["attemptName"], "strict_clean_fallback")

    def test_debug_capture_on_writes_targeted_repair_fallback_artifact_files(self) -> None:
        (Path.cwd() / "reports").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "reports") as tmp:
            debug_dir = Path(tmp) / "debug" / "episode_017"
            pipeline = DirectTranslator(PipelineConfig(locale="ko_ja", mock=True))

            result = pipeline.translate_once(
                "\ubb38\uc740 \uc870\uc6a9\ud788 \uc5f4\ub838\ub2e4.",
                memory_context="[GRAPH TARGETED SMALL PROSE RESIDUE FALLBACK]\n- Repair only the affected sentence.",
                strict_locale_retry=True,
                retry_attempt=3,
                debug_capture={
                    "enabled": True,
                    "artifactDir": str(debug_dir),
                    "attemptName": "targeted_repair_fallback",
                    "promptPreview": "[GRAPH TARGETED SMALL PROSE RESIDUE FALLBACK]\n- Repair only the affected sentence.",
                },
            )

            artifact = result.metadata["debug_artifact"]
            for key in ["rawOutputPath", "parsedCandidatePath", "metricsPath", "promptPreviewPath", "promptMetadataPath"]:
                self.assertTrue(Path(artifact[key]).exists(), key)
                self.assertIn("targeted_repair_fallback", Path(artifact[key]).name)
            metrics = json.loads(Path(artifact["metricsPath"]).read_text(encoding="utf-8"))
            self.assertEqual(metrics["attemptName"], "targeted_repair_fallback")

    def test_graph_repair_trace_records_debug_artifact_summary_and_discard_reason(self) -> None:
        source = (
            "\uc55e\uc740 \uc774\ubbf8 \uc5f4\ub824 \uc788\uc5c8\ub2e4. "
            "\ubb38\ud2c8 \uc0ac\uc774\ub85c \ubd89\uc740 \ube5b\uc774 \uc0c8\uc5b4 \ub098\uc654\ub2e4."
        )
        debug_artifact = {
            "debugArtifactDir": "reports/debug/episode_001",
            "rawOutputPath": "reports/debug/episode_001/graph_clean_full_translator_retry_raw_output.txt",
            "parsedCandidatePath": "reports/debug/episode_001/graph_clean_full_translator_retry_parsed_candidate.txt",
            "metricsPath": "reports/debug/episode_001/graph_clean_full_translator_retry_metrics.json",
        }

        def translate_once(strict, attempt, revision_context=""):
            return source, {"delivery_status": "deliverable", "source_copy_status": "fail", "debug_artifact": debug_artifact}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        trace = package.internal["graphRepairTrace"][0]
        response_json = json.dumps(asdict(package), ensure_ascii=False)

        self.assertEqual(trace["debugArtifactDir"], debug_artifact["debugArtifactDir"])
        self.assertEqual(trace["rawOutputPath"], debug_artifact["rawOutputPath"])
        self.assertTrue(trace["candidateDiscarded"])
        self.assertIn(trace["discardReason"], {"source_copy", "source_copy_and_prose_residue"})
        self.assertNotIn("raw_model_output", response_json)

    def test_graph_system_ui_patch_does_not_trigger_clean_retry(self) -> None:
        source = "[\uc0c1\ud0dc: \uad76\uc8fc\ub9bc / \ubd88\uc548 / \uc601\uc5ed \ubc29\uc5b4 \uc911]"
        calls = []

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"strict": strict, "attempt": attempt, "revisionContext": revision_context})
            return "[\u72b6\u614b: \uad76\uc8fc\ub9bc / \u4e0d\u5b89 / \uc601\uc5ed \ubc29\uc5b4 \uc911]", {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": source, "targetLocale": "ko_ja"},
            },
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertEqual(package.qaIssues, [])
        self.assertEqual(package.internal.get("graphRepairTrace"), [])
        self.assertFalse(any("GRAPH CLEAN FULL TRANSLATOR RETRY" in row["revisionContext"] for row in calls))

    def test_delivery_status_meaning_is_preserved_for_qa_warning_not_safety(self) -> None:
        memory = WorkMemory(
            workId="work-graph",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\ub099\uc6d0\ub3d9", target="\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", category="place", priority="hard")],
        )
        state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\ub099\uc6d0\ub3d9\uc73c\ub85c \uac14\ub2e4.", "targetLocale": "ko_ja"},
                "sourceText": "\ub099\uc6d0\ub3d9\uc73c\ub85c \uac14\ub2e4.",
                "targetLocale": "ko_ja",
                "workMemory": memory,
                "workMemorySource": "request_payload",
            },
            max_iterations=2,
            translate_once=lambda strict, attempt, revision_context="": ("\u5f7c\u306f\u5730\u4e0b\u5546\u5e97\u8857\u3078\u884c\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )
        package = state["translationPackage"]

        self.assertEqual(package.deliveryStatus, "qa_warning")
        self.assertNotEqual(package.deliveryStatus, "blocked_translation_safety")
        self.assertTrue(any(issue["code"] == "glossary_consistency" for issue in package.qaIssues))

    def test_persistence_hook_runs_for_deliverable_and_skips_blocked(self) -> None:
        calls = []

        def persist_hook(state):
            calls.append(state["deliveryStatus"])
            return {"enabled": True, "saved": True, "savedTranslationId": 123}

        state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.", "targetLocale": "ko_ja", "saveTranslationResult": True},
                "persistHook": persist_hook,
            },
            max_iterations=1,
        )
        self.assertEqual(calls, ["deliverable"])
        self.assertEqual(state["savedTranslationId"], 123)

        calls.clear()
        blocked_state = run_graph_orchestrator(
            {
                "request": {"sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.", "targetLocale": "ko_ja", "saveTranslationResult": True},
                "persistHook": persist_hook,
            },
            max_iterations=1,
            translate_once=lambda strict, attempt, revision_context="": ("", {"delivery_status": "blocked_translation_safety"}),
        )
        self.assertEqual(calls, [])
        self.assertEqual(blocked_state["translationPackage"].deliveryStatus, "blocked_translation_safety")

    def test_glossary_capture_hook_runs_when_requested_and_skips_blocked(self) -> None:
        calls = []

        def capture_hook(state):
            calls.append(state["workId"])
            return {"enabled": True, "savedCount": 2, "skippedCount": 0}

        state = run_graph_orchestrator(
            {
                "request": {
                    "sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
                    "targetLocale": "ko_ja",
                    "workId": "work-1",
                    "captureGlossaryCandidates": True,
                },
                "captureHook": capture_hook,
            },
            max_iterations=1,
        )
        self.assertEqual(calls, ["work-1"])
        self.assertEqual(state["glossarySavedCount"], 2)

        calls.clear()
        blocked_state = run_graph_orchestrator(
            {
                "request": {
                    "sourceText": "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
                    "targetLocale": "ko_ja",
                    "workId": "work-1",
                    "captureGlossaryCandidates": True,
                },
                "captureHook": capture_hook,
            },
            max_iterations=1,
            translate_once=lambda strict, attempt, revision_context="": ("", {"delivery_status": "blocked_translation_safety"}),
        )
        self.assertEqual(calls, [])
        self.assertEqual(blocked_state["translationPackage"].deliveryStatus, "blocked_translation_safety")


    def test_common_noun_residue_routes_to_targeted_repair(self) -> None:
        source = "\uadf8\ub294 \ub099\uc6d0\ub3d9 \uc9c0\ud558\uc0c1\uac00\ub85c \ub3cc\uc544\uac14\ub2e4."
        calls = []

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"attempt": attempt, "revisionContext": revision_context})
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                return "\u305d\u306e\u591c\u3001\u5f7c\u306f\u9759\u304b\u306b\u901a\u308a\u3092\u629c\u3051\u3001\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3\u306e\u5730\u4e0b\u5546\u5e97\u8857\u306b\u623b\u3063\u305f\u3002\u5468\u56f2\u306e\u7a7a\u6c17\u306f\u91cd\u304f\u3001\u8ab0\u3082\u58f0\u3092\u4e0a\u3052\u306a\u304b\u3063\u305f\u3002", {"delivery_status": "deliverable"}
            return "\u305d\u306e\u591c\u3001\u5f7c\u306f\u9759\u304b\u306b\u901a\u308a\u3092\u629c\u3051\u3001\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3 \uc9c0\ud558\uc0c1\uac00\u306b\u623b\u3063\u305f\u3002\u5468\u56f2\u306e\u7a7a\u6c17\u306f\u91cd\u304f\u3001\u8ab0\u3082\u58f0\u3092\u4e0a\u3052\u306a\u304b\u3063\u305f\u3002", {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {"request": {"sourceText": source, "targetLocale": "ko_ja"}},
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        trace = package.internal["graphRepairTrace"][0]

        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertFalse(package.qaIssues)
        self.assertTrue(trace["commonNounResidueDetected"])
        self.assertTrue(trace["nameResidueFalsePositiveAvoided"])
        self.assertTrue(trace["targetedRepairSucceeded"])
        self.assertFalse(trace["targetedRepairFallbackAttempted"])
        self.assertNotIn("\uc9c0\ud558\uc0c1\uac00", package.finalTranslation)

    def test_hangul_residue_repair_uses_sentence_window_offsets(self) -> None:
        source = "\ud575\uc2ec \uade0\uc5f4\ubb38\uc744 \ud655\uc778\ud55c \ub2e4\uc74c\ub0a0, \uadf8\ub294 \uc228\uc744 \ub0b4\uc26c\uc5c8\ub2e4."
        mixed_sentence = "\ud575\uc2ec \uade0\uc5f4\ubb38\u3092\u78ba\u8a8d\u3057\u305f\u7fcc\u65e5\u3001\u5f7c\u306f\u6df1\u304f\u606f\u3092\u5410\u3044\u305f\u3002"
        prefix = "\u96e8\u306e\u97f3\u3060\u3051\u304c\u9577\u3044\u5eca\u4e0b\u306b\u6b8b\u3063\u3066\u3044\u305f\u3002"
        suffix = "\u5f7c\u306f\u8a00\u8449\u3092\u9078\u3073\u306a\u304c\u3089\u3001\u3082\u3046\u4e00\u5ea6\u5730\u56f3\u3092\u958b\u3044\u305f\u3002"
        initial = prefix + mixed_sentence + suffix
        repaired_sentence = "\u6838\u5fc3\u3068\u306a\u308b\u4e80\u88c2\u9580\u3092\u78ba\u8a8d\u3057\u305f\u7fcc\u65e5\u3001\u5f7c\u306f\u6df1\u304f\u606f\u3092\u5410\u3044\u305f\u3002"
        calls = []

        def translate_once(strict, attempt, revision_context=""):
            calls.append({"attempt": attempt, "revisionContext": revision_context})
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                self.assertIn("[repair sentence window]", revision_context)
                self.assertIn(mixed_sentence, revision_context)
                self.assertIn("sentenceWindowStart=", revision_context)
                self.assertIn("sentenceWindowEnd=", revision_context)
                self.assertIn("residualSpan=\ud575\uc2ec", revision_context)
                self.assertIn("residualSpan=\uade0\uc5f4\ubb38", revision_context)
                return repaired_sentence, {"delivery_status": "deliverable"}
            return initial, {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {"request": {"sourceText": source, "targetLocale": "ko_ja"}},
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        trace = package.internal["graphRepairTrace"][0]
        initial_spans = package.internal["iterations"][0]["critique"][0]["details"]["spans"]

        self.assertEqual([span["text"] for span in initial_spans[:2]], ["\ud575\uc2ec", "\uade0\uc5f4\ubb38"])
        self.assertEqual(package.finalTranslation, prefix + repaired_sentence + suffix)
        self.assertNotRegex(package.finalTranslation, r"[\uac00-\ud7a3]")
        self.assertTrue(trace["targetedRepairSucceeded"])
        self.assertEqual(trace["residualHangulCharCountAfter"], 0)
        self.assertGreater(trace["targetedRepairWindowStart"], 0)
        self.assertIn(mixed_sentence, trace["targetedRepairWindowText"])
        self.assertEqual(sum(1 for row in calls if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in row["revisionContext"]), 1)

    def test_mixed_script_partial_name_residue_repairs_whole_token(self) -> None:
        source = "\ucca0\uc218\uac00 \uc678\ucce4\ub2e4."
        contexts = []

        def translate_once(strict, attempt, revision_context=""):
            contexts.append(revision_context)
            if "GRAPH TARGETED SMALL PROSE RESIDUE REPAIR" in revision_context:
                return "\u5f7c\u306f\u3059\u3050\u306b\u632f\u308a\u8fd4\u308a\u3001\u4eba\u3054\u307f\u306e\u4e2d\u3067\u606f\u3092\u5451\u3093\u3060\u3002\u300c\u30c1\u30e7\u30eb\u30b9\uff01\u300d\u5468\u56f2\u306e\u8996\u7dda\u304c\u4e00\u6589\u306b\u96c6\u307e\u3063\u305f\u3002", {"delivery_status": "deliverable"}
            return "\u5f7c\u306f\u3059\u3050\u306b\u632f\u308a\u8fd4\u308a\u3001\u4eba\u3054\u307f\u306e\u4e2d\u3067\u606f\u3092\u5451\u3093\u3060\u3002\u300c\u9244\uc218\uff01\u300d\u5468\u56f2\u306e\u8996\u7dda\u304c\u4e00\u6589\u306b\u96c6\u307e\u3063\u305f\u3002", {"delivery_status": "deliverable"}

        state = run_graph_orchestrator(
            {"request": {"sourceText": source, "targetLocale": "ko_ja"}},
            max_iterations=2,
            translate_once=translate_once,
        )
        package = state["translationPackage"]
        self.assertEqual(package.deliveryStatus, "deliverable")
        self.assertFalse(package.qaIssues)
        self.assertNotIn("\u9244\uc218", package.finalTranslation)
        self.assertNotIn("\uc218", package.finalTranslation)
        initial_critique = package.internal["iterations"][0]["critique"]
        spans = initial_critique[0]["details"]["spans"]
        self.assertEqual(spans[0]["text"], "\u9244\uc218")
        self.assertTrue(spans[0]["mixedScriptNameResidueDetected"])
        self.assertTrue(spans[0]["partialNameResidueDetected"])
        self.assertEqual(spans[0]["repairAffectedToken"], "\u9244\uc218")


if __name__ == "__main__":
    unittest.main()
