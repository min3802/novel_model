from __future__ import annotations

import os
import unittest
from dataclasses import asdict
from unittest.mock import patch

from app.translation import PipelineConfig, TranslationMode, TranslationPipeline
from app.translation.glossary_store import default_glossary_repository
from app.translation.infra.country_locale import resolve_country_for_locale
from app.translation.v3_literary_package import (
    GlossaryEntry,
    WorkMemory,
    build_rag_packets,
    build_sample_work_memory,
    build_v3_guidelines,
    build_v3_literary_package,
    detect_idiom_notes,
    run_translation_loop,
)
from backend.services.translation_service import translate


IDIOM_SOURCE = "그는 발등에 불이 떨어지다 싶을 만큼 급했다."
PLAIN_SOURCE = "그는 조용히 문을 닫고 복도를 걸었다."
GLOSSARY_SOURCE = "강현우는 균열 앞에 서다."
ENTITY_SOURCE = "리아는 북부대공 카이든 에른스트를 보았다. 그녀는 그를 검은 늑대라고 불렀다."


class TranslationV3LiteraryPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["WLIGHTER_MOCK_MODE"] = "true"
        default_glossary_repository.clear()

    def _work_memory(self, *, priority: str = "hard") -> WorkMemory:
        return WorkMemory(
            workId="work-1",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="강현우", target="Kang Hyunwoo", category="person", priority="hard", aliases=[], forbidden=["Gang Hyeon-u"], note="main character"),
                GlossaryEntry(source="균열", target="rift", category="system_term", priority=priority, aliases=[], forbidden=["crack"], note="setting term"),
            ],
            styleMemory={"tone": "literary"},
            previousSummary="previous episode summary",
        )

    def test_v3_pipeline_returns_translation_and_rationale(self) -> None:
        result = build_v3_literary_package(IDIOM_SOURCE, "ko_ja")
        self.assertEqual(result.pipeline, "v3_literary_package")
        self.assertTrue(result.finalTranslation)
        self.assertEqual(result.translationRationale.title, "왜 이렇게 번역했는지")
        self.assertTrue(result.translationRationale.items)
        self.assertIn("idiomNotes", result.internal)

    def test_idiom_notes_are_internal_and_rationale_inputs(self) -> None:
        result = build_v3_literary_package(IDIOM_SOURCE, "ko_ja")
        internal_notes = result.internal["idiomNotes"]
        rationale_spans = [item.sourceSpan for item in result.translationRationale.items]
        self.assertEqual(internal_notes[0]["canonical"], "발등에 불이 떨어지다")
        self.assertIn("발등에 불이 떨어지다", rationale_spans)

    def test_no_idiom_sentence_still_delivers_with_empty_idiom_notes(self) -> None:
        result = build_v3_literary_package(PLAIN_SOURCE, "ko_ja")
        self.assertEqual(result.internal["idiomNotes"], [])
        self.assertTrue(result.finalTranslation)
        self.assertTrue(result.translationRationale.items)

    def test_work_memory_none_keeps_existing_v3_behavior(self) -> None:
        result = build_v3_literary_package(PLAIN_SOURCE, "ko_ja", work_memory=None)
        self.assertIsNone(result.internal["workMemory"])
        self.assertEqual(result.internal["ragPackets"]["translatorBrief"]["glossary"], [])

    def test_v3_internal_includes_character_and_entity_evidence(self) -> None:
        result = build_v3_literary_package(ENTITY_SOURCE, "ko_en_us")

        self.assertIn("characterReferences", result.internal)
        self.assertIn("entityCandidates", result.internal)
        self.assertTrue(result.internal["characterReferences"])
        self.assertTrue(result.internal["entityCandidates"])
        self.assertIn("그녀", result.internal["characterReferences"][0]["references_ko"])
        self.assertIn("characterReferences", result.internal["ragPackets"]["editorEvidence"])
        self.assertIn("entityCandidates", result.internal["ragPackets"]["editorEvidence"])

    def test_sample_work_memory_helper_builds_valid_payload(self) -> None:
        payload = build_sample_work_memory("ko_en_us", work_id="sample-1")
        self.assertEqual(payload["workId"], "sample-1")
        self.assertEqual(payload["targetLocale"], "ko_en_us")
        self.assertGreaterEqual(len(payload["approvedGlossary"]), 3)
        result = build_v3_literary_package(GLOSSARY_SOURCE, "ko_en_us", work_memory=payload)
        self.assertEqual(result.internal["workMemory"]["workId"], "sample-1")

    def test_work_memory_is_preserved_in_v3_internal_evidence(self) -> None:
        result = build_v3_literary_package(GLOSSARY_SOURCE, "ko_ja", work_memory=self._work_memory())
        rag = result.internal["ragPackets"]
        self.assertTrue(rag["translatorBrief"]["glossary"])
        self.assertTrue(rag["editorEvidence"]["approvedGlossary"])
        self.assertEqual(rag["translatorBrief"]["glossary"], rag["editorEvidence"]["approvedGlossary"])
        self.assertEqual(rag["translatorBrief"]["glossary"], rag["rationaleEvidence"]["approvedGlossary"])

    def test_approved_glossary_is_compacted_into_translator_brief(self) -> None:
        notes = detect_idiom_notes(GLOSSARY_SOURCE, "ko_ja")
        packets = build_rag_packets(GLOSSARY_SOURCE, "ko_ja", "hunter fantasy", notes, work_memory=self._work_memory())
        brief_glossary = packets.translatorBrief["glossary"]
        self.assertLessEqual(len(brief_glossary), 50)
        self.assertIn("rift", [row["target"] for row in brief_glossary])
        self.assertIn("approvedGlossary", packets.editorEvidence)
        self.assertEqual(brief_glossary, packets.editorEvidence["approvedGlossary"])
        self.assertEqual(brief_glossary, packets.rationaleEvidence["approvedGlossary"])

    def test_ko_ja_guidelines_include_nonliteral_idiom_policy(self) -> None:
        notes = detect_idiom_notes("그는 마른세수를 했다. 지금은 발등에 불이 떨어져도 눈이 감길 것 같았다.", "ko_ja")
        packets = build_rag_packets("그는 마른세수를 했다.", "ko_ja", "modern web novel", notes, work_memory=None)
        guidelines = build_v3_guidelines("그는 마른세수를 했다.", "ko_ja", "modern web novel", notes, packets)
        locale_policy = "\n".join(packets.editorEvidence["localePolicy"])

        self.assertIn("word-for-word", guidelines.translatorGuideline)
        self.assertIn("마른세수", guidelines.translatorGuideline)
        self.assertIn("발등에 불", guidelines.translatorGuideline)
        self.assertIn("팀장", guidelines.translatorGuideline)
        self.assertIn("dry face-washing", locale_policy)
        self.assertIn("feet on fire", locale_policy)
        self.assertIn("チーム長", locale_policy)

    def test_hard_glossary_missing_target_creates_p1_issue(self) -> None:
        result = build_v3_literary_package(
            GLOSSARY_SOURCE,
            "ko_ja",
            work_memory=self._work_memory(),
            translate_once=lambda strict, attempt: ("Kang Hyunwoo saw the anomaly.", {"delivery_status": "deliverable"}),
        )
        issues = [issue for issue in result.qaIssues if issue["code"] == "glossary_consistency"]
        self.assertTrue(issues)
        self.assertEqual(issues[0]["priority"], "P1")
        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertIn("glossary_consistency_issue", result.internal["failureSignals"])
        self.assertTrue(issues[0]["autoRevisionEligible"])

    def test_approved_glossary_flags_clear_mistranslation_without_pending_candidates(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="철수", target="チョルス", category="person", priority="hard", aliases=[], forbidden=[]),
            ],
        )
        result = build_v3_literary_package(
            "철수! 지금 와야 해.",
            "ko_ja",
            work_memory=memory,
            translate_once=lambda strict, attempt: ("撤退! 今すぐ来なければならない。", {"delivery_status": "deliverable"}),
        )

        issues = [issue for issue in result.qaIssues if issue["code"] == "glossary_consistency"]
        self.assertTrue(issues)
        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertEqual(issues[0]["sourceSpan"], "철수")
        self.assertEqual(issues[0]["targetSpan"], "チョルス")

    def test_hard_glossary_missing_revision_can_restore_deliverable(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="낙원동", target="ナクウォンドン", category="place", priority="hard", aliases=[], forbidden=[]),
            ],
        )
        calls = []

        def translate_once(strict: bool, attempt: int):
            calls.append((strict, attempt))
            if not strict:
                return "落園洞の地下商店街へ向かった。", {"delivery_status": "deliverable"}
            return "ナクウォンドンの地下商店街へ向かった。", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(
            "그는 낙원동 지하상가로 향했다.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=translate_once,
        )

        self.assertEqual(calls, [(False, 0), (True, 1)])
        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertEqual(result.qaIssues, [])
        self.assertIn("ナクウォンドン", result.finalTranslation)

    def test_glossary_source_absent_does_not_create_false_positive(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="강도윤", target="カン・ドユン", category="person", priority="hard", aliases=[], forbidden=[]),
            ],
        )
        result = build_v3_literary_package(
            "도윤은 문을 열었다.",
            "ko_ja",
            work_memory=memory,
            max_iterations=1,
            translate_once=lambda strict, attempt: ("ドユンは扉を開けた。", {"delivery_status": "deliverable"}),
        )

        self.assertFalse(any(issue["code"] == "glossary_consistency" for issue in result.qaIssues))
        self.assertEqual(result.deliveryStatus, "deliverable")

    def test_glossary_alias_presence_is_checked(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="도윤", target="ドユン", category="person", priority="hard", aliases=["강도윤"], forbidden=[]),
            ],
        )
        result = build_v3_literary_package(
            "강도윤은 문을 열었다.",
            "ko_ja",
            work_memory=memory,
            max_iterations=1,
            translate_once=lambda strict, attempt: ("カン・ドインは扉を開けた。", {"delivery_status": "deliverable"}),
        )

        issue = next(issue for issue in result.qaIssues if issue["code"] == "glossary_consistency")
        self.assertEqual(issue["priority"], "P1")
        self.assertTrue(issue["autoRevisionEligible"])
        self.assertEqual(result.deliveryStatus, "qa_warning")

    def test_hard_glossary_revision_failure_keeps_qa_warning_not_safety_block(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="낙원동", target="ナクウォンドン", category="place", priority="hard", aliases=[], forbidden=[]),
            ],
        )

        def translate_once(strict: bool, attempt: int):
            return "No approved place surface remains after retry.", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(
            "그는 낙원동 지하상가로 향했다.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=translate_once,
        )

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertNotEqual(result.deliveryStatus, "blocked_translation_safety")
        self.assertTrue(any(issue["code"] == "glossary_consistency" for issue in result.qaIssues))

    def test_forbidden_glossary_translation_creates_issue(self) -> None:
        result = build_v3_literary_package(
            GLOSSARY_SOURCE,
            "ko_ja",
            work_memory=self._work_memory(),
            translate_once=lambda strict, attempt: ("Kang Hyunwoo entered the crack near the rift.", {"delivery_status": "deliverable"}),
        )
        self.assertTrue(any(issue["code"] == "glossary_forbidden_translation" for issue in result.qaIssues))

    def test_soft_glossary_missing_target_does_not_escalate_to_p1_or_p0(self) -> None:
        result = build_v3_literary_package(
            GLOSSARY_SOURCE,
            "ko_ja",
            work_memory=self._work_memory(priority="soft"),
            translate_once=lambda strict, attempt: ("Kang Hyunwoo saw the anomaly.", {"delivery_status": "deliverable"}),
        )
        priorities = {issue.get("priority") for issue in result.qaIssues if issue.get("code") == "glossary_consistency"}
        self.assertFalse(priorities & {"P0", "P1"})

    def test_glossary_rationale_only_when_target_exists(self) -> None:
        result = build_v3_literary_package(
            GLOSSARY_SOURCE,
            "ko_ja",
            work_memory=self._work_memory(),
            translate_once=lambda strict, attempt: ("Kang Hyunwoo entered the rift.", {"delivery_status": "deliverable"}),
        )
        terminology_items = [item for item in result.translationRationale.items if item.category == "terminology"]
        self.assertTrue(any(item.targetSpan == "rift" for item in terminology_items))
        missing = build_v3_literary_package(
            GLOSSARY_SOURCE,
            "ko_ja",
            work_memory=self._work_memory(),
            translate_once=lambda strict, attempt: ("Kang Hyunwoo entered the anomaly.", {"delivery_status": "deliverable"}),
        )
        self.assertFalse(any(item.targetSpan == "rift" for item in missing.translationRationale.items if item.category == "terminology"))

    def test_idiom_detector_default_rule_and_ft_disabled(self) -> None:
        result = build_v3_literary_package(IDIOM_SOURCE, "ko_ja")
        self.assertEqual(result.internal["idiomDetection"]["mode"], "rule")
        self.assertFalse(result.internal["idiomDetection"]["ftEnabled"])
        self.assertEqual(detect_idiom_notes(IDIOM_SOURCE, "ko_ja", mode="ft"), [])

    def test_translation_loop_never_exceeds_two_iterations(self) -> None:
        notes = detect_idiom_notes(IDIOM_SOURCE, "ko_ja")
        def bad_translation_once(strict_retry: bool, retry_attempt: int):
            return IDIOM_SOURCE, {"delivery_status": "deliverable"}
        loop = run_translation_loop(IDIOM_SOURCE, "ko_ja", "short", "long", idiom_notes=notes, max_iterations=5, translate_once=bad_translation_once)
        self.assertLessEqual(len(loop.iterations), 2)
        self.assertTrue(loop.finalTranslation)
        self.assertEqual(loop.deliveryStatus, "qa_warning")
        self.assertTrue(any(issue["code"] == "hangul_residue_integrity" for issue in loop.qaIssues))

    def test_pipeline_method_exposes_v3_result(self) -> None:
        pipeline = TranslationPipeline(PipelineConfig(locale="ko_ja", mode=TranslationMode.V3_LITERARY_PACKAGE, mock=True))
        data = asdict(pipeline.run_v3_literary_package(IDIOM_SOURCE))
        self.assertEqual(data["pipeline"], "v3_literary_package")
        self.assertIn("translationRationale", data)
        self.assertTrue(data["finalTranslation"])

    def test_translation_service_selects_v3_mode(self) -> None:
        country = resolve_country_for_locale("ko_ja")
        response = translate({"sourceText": IDIOM_SOURCE, "targetCountry": country, "mode": "v3_literary_package"})
        self.assertEqual(response["mode"], "v3_literary_package")
        self.assertTrue(response["finalTranslation"])
        self.assertIn("translationRationale", response)
        self.assertIn("internal", response)

    def test_translation_service_accepts_v3_work_memory_payload(self) -> None:
        country = resolve_country_for_locale("ko_ja")
        response = translate(
            {
                "sourceText": GLOSSARY_SOURCE,
                "targetCountry": country,
                "mode": "v3_literary_package",
                "workMemory": build_sample_work_memory("ko_ja", work_id="svc-work"),
            }
        )
        internal = response["internal"]
        self.assertEqual(internal["workMemory"]["workId"], "svc-work")
        self.assertEqual(internal["workMemorySource"], "request_payload")
        self.assertTrue(internal["ragPackets"]["translatorBrief"]["glossary"])

    def test_translation_service_prefers_request_work_memory_over_store(self) -> None:
        country = resolve_country_for_locale("ko_ja")
        default_glossary_repository.clear()
        default_glossary_repository.upsert_entry(
            work_id="svc-work",
            country="JP",
            source="강현우",
            target="ストア由来",
            category="person",
        )
        request_memory = {
            "workId": "svc-work",
            "targetLocale": "ko_ja",
            "approvedGlossary": [
                {
                    "source": "균열",
                    "target": "request-rift",
                    "category": "genre_term",
                    "priority": "hard",
                    "aliases": [],
                    "forbidden": [],
                    "note": "request payload wins",
                }
            ],
        }

        response = translate(
            {
                "sourceText": GLOSSARY_SOURCE,
                "targetCountry": country,
                "mode": "v3_literary_package",
                "workId": "svc-work",
                "workMemory": request_memory,
            }
        )

        glossary = response["internal"]["ragPackets"]["translatorBrief"]["glossary"]
        self.assertEqual(response["internal"]["workMemorySource"], "request_payload")
        self.assertIn("request-rift", [row["target"] for row in glossary])
        self.assertNotIn("ストア由来", [row["target"] for row in glossary])

    def test_translation_service_hydrates_work_memory_from_store(self) -> None:
        country = resolve_country_for_locale("ko_ja")
        default_glossary_repository.clear()
        default_glossary_repository.upsert_entry(
            work_id="svc-work",
            country="JP",
            source="강현우",
            target="カン・ヒョヌ",
            category="person",
        )

        response = translate(
            {
                "sourceText": GLOSSARY_SOURCE,
                "targetCountry": country,
                "mode": "v3_literary_package",
                "workId": "svc-work",
            }
        )

        internal = response["internal"]
        glossary = internal["ragPackets"]["translatorBrief"]["glossary"]
        editor_glossary = internal["ragPackets"]["editorEvidence"]["approvedGlossary"]
        self.assertEqual(internal["workMemorySource"], "rdb_hydrated")
        self.assertEqual(internal["workMemoryGlossaryCount"], 1)
        # Every stored row is an enforced rule; aliases live in their own rows.
        self.assertEqual(glossary[0]["priority"], "hard")
        self.assertEqual(glossary[0]["aliases"], [])
        self.assertEqual(editor_glossary[0]["target"], "カン・ヒョヌ")

    def test_translation_service_candidate_capture_removed(self) -> None:
        response = translate(
            {
                "sourceText": IDIOM_SOURCE,
                "targetLocale": "ko_ja",
                "pipeline": "v3_literary_package",
                "workId": "svc-work",
            }
        )

        # Auto-capture has been removed: the glossary is a single, manually
        # curated rule table, so translation never writes candidates.
        self.assertEqual(
            response["internal"]["glossaryCandidateCapture"],
            {"enabled": False, "reason": "auto_capture_disabled", "savedCount": 0},
        )

    def test_translation_service_hydration_failure_falls_back_without_blocking(self) -> None:
        country = resolve_country_for_locale("ko_ja")
        with patch("backend.services.translation_service.hydrate_work_memory", side_effect=RuntimeError("store down")):
            response = translate(
                {
                    "sourceText": IDIOM_SOURCE,
                    "targetCountry": country,
                    "mode": "v3_literary_package",
                    "workId": "svc-work",
                }
            )

        self.assertTrue(response["finalTranslation"])
        self.assertEqual(response["internal"]["workMemorySource"], "none")
        self.assertIn("glossary_hydration_failed", response["internal"]["workMemoryFallbackReason"])

    def test_translation_service_accepts_v3_target_locale_without_target_country(self) -> None:
        response = translate(
            {
                "sourceText": IDIOM_SOURCE,
                "targetLocale": "ko_ja",
                "pipeline": "v3_literary_package",
            }
        )
        self.assertEqual(response["locale"], "ko_ja")
        self.assertEqual(response["mode"], "v3_literary_package")

    def test_translation_service_accepts_v3_target_country_without_target_locale(self) -> None:
        response = translate(
            {
                "sourceText": IDIOM_SOURCE,
                "targetCountry": "JP",
                "pipeline": "v3_literary_package",
            }
        )
        self.assertEqual(response["country"], "JP")
        self.assertEqual(response["locale"], "ko_ja")
        self.assertEqual(response["mode"], "v3_literary_package")

    def test_translation_service_rejects_mismatched_country_and_locale(self) -> None:
        response = translate(
            {
                "sourceText": IDIOM_SOURCE,
                "targetCountry": "US",
                "targetLocale": "ko_ja",
                "pipeline": "v3_literary_package",
            }
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["errorCode"], "target_country_locale_mismatch")
        self.assertEqual(response["status"], 400)

    def test_ko_ja_hangul_residue_contract_is_preserved(self) -> None:
        result = build_v3_literary_package(IDIOM_SOURCE, "ko_ja")
        self.assertNotEqual(result.deliveryStatus, "blocked_translation_safety")
        self.assertNotRegex(result.finalTranslation, r"[가-힣]")

    def test_ko_ja_integrity_flags_korean_person_name_residue(self) -> None:
        result = build_v3_literary_package(
            "도윤은 문을 열었다.",
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("도윤は扉を開けた。", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertEqual(result.qaIssues, [])
        self.assertIn("ドユンは", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))
        self.assertTrue(any((it.get("action") == "Deterministic Known Person Residue Patch") for it in result.internal["iterations"]))

    def test_ko_ja_integrity_flags_mixed_hangul_kana_place_residue(self) -> None:
        result = build_v3_literary_package(
            "도윤은 낙원동 지하상가로 내려갔다.",
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("ドユンは낙원동の地下商店街へ降りた。", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("ナクウォンドンの", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_ko_ja_name_residue_patch_handles_cha_minhyeok_particle(self) -> None:
        result = build_v3_literary_package(
            "차민혁은 처음부터 말로 끝낼 생각이 없었다.",
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("차민혁は最初から、言葉で片をつけるつもりなどないようだった。", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertEqual(result.qaIssues, [])
        self.assertIn("チャ・ミンヒョクは", result.finalTranslation)

    def test_ko_ja_integrity_flags_bracket_role_and_order_mismatch(self) -> None:
        source = "휴대폰 화면에 [어머니]가 떴다.\n그는 뒤쪽 게이트로 뛰었다.\n[관리자 권한 확인 중……]"
        bad_translation = "携帯の画面に[管理者権限を確認中……]が浮かんだ。\n彼は裏手のゲートへ走った。\n[母]"
        result = build_v3_literary_package(
            source,
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: (bad_translation, {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertTrue(any(issue["code"] == "bracket_block_role_or_order_mismatch" for issue in result.qaIssues))
        issue = next(issue for issue in result.qaIssues if issue["code"] == "bracket_block_role_or_order_mismatch")
        self.assertEqual(issue["priority"], "P1")
        self.assertTrue(issue["autoRevisionEligible"])
        self.assertIn("[어머니]", issue["sourceSpan"])
        self.assertIn("[管理者権限を確認中……]", issue["targetSpan"])
        self.assertEqual(result.internal["judge"]["autoRevisionRequired"], True)




    def test_ko_ja_integrity_accepts_corner_bracket_contact_block(self) -> None:
        source = "[\uc5b4\uba38\ub2c8]\n\uc804\ud654\uac00 \uc654\ub2e4."
        result = build_v3_literary_package(
            source,
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("\u3010\u6bcd\u3011\n\u96fb\u8a71\u304c\u6765\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertFalse(any(issue["code"] == "bracket_block_count_mismatch" for issue in result.qaIssues))

    def test_ko_ja_integrity_accepts_fullwidth_square_bracket_blocks(self) -> None:
        source = "[\uc0ac\uc6a9\uc790: \uac15\ub3c4\uc724]\n[\uc9c1\uc5c5: \ub358\uc804 \uad00\ub9ac\uc790]"
        result = build_v3_literary_package(
            source,
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("\uff3b\u30e6\u30fc\u30b6\u30fc\uff1a\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\uff3d\n\uff3b\u8077\u696d\uff1a\u30c0\u30f3\u30b8\u30e7\u30f3\u7ba1\u7406\u8005\uff3d", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertFalse(any(issue["code"] == "bracket_block_count_mismatch" for issue in result.qaIssues))

    def test_bracket_zero_target_revision_context_lists_source_blocks(self) -> None:
        source = (
            "[\ubc15 \ud300\uc7a5]\n"
            "\ubb38\uc790\uac00 \ub3c4\ucc29\ud588\ub2e4.\n"
            "[\ub300\ud55c\ubbfc\uad6d \ud5cc\ud130\ud611\ud68c \uc790\uc0b0\uad00\ub9ac\uad6d]\n"
            "[\uad00\ub9ac\uc790 \ud29c\ud1a0\ub9ac\uc5bc\uc774 \uc2dc\uc791\ub429\ub2c8\ub2e4.]"
        )
        calls = []

        def translate_once(strict: bool, attempt: int, revision_context: str = ""):
            calls.append((strict, attempt, revision_context))
            return "\u30e1\u30c3\u30bb\u30fc\u30b8\u304c\u5c4a\u3044\u305f\u3002", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(source, "ko_ja", max_iterations=2, translate_once=translate_once)

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertTrue(any(issue["code"] == "bracket_block_count_mismatch" for issue in result.qaIssues))
        self.assertGreaterEqual(len(calls), 2)
        revision_context = calls[1][2]
        self.assertIn("source bracket block count: 3", revision_context)
        self.assertIn("[\ubc15 \ud300\uc7a5]", revision_context)
        self.assertIn("[\ub300\ud55c\ubbfc\uad6d \ud5cc\ud130\ud611\ud68c \uc790\uc0b0\uad00\ub9ac\uad6d]", revision_context)
        self.assertIn("target bracket block count: 0", revision_context)

    def test_bracket_preserving_revision_success_restores_deliverable(self) -> None:
        source = "[\ubc15 \ud300\uc7a5]\n\ubb38\uc790.\n[\uc0c1\ud0dc: \uad76\uc8fc\ub9bc / \ubd88\uc548]\n[\uad00\ub9ac\uc790 \ud29c\ud1a0\ub9ac\uc5bc\uc774 \uc2dc\uc791\ub429\ub2c8\ub2e4.]"

        def translate_once(strict: bool, attempt: int, revision_context: str = ""):
            if not strict:
                return "\u30e1\u30c3\u30bb\u30fc\u30b8\u3002", {"delivery_status": "deliverable"}
            return "[\u30d1\u30af\u30c1\u30fc\u30e0\u9577]\n\u30e1\u30c3\u30bb\u30fc\u30b8\u3002\n[\u72b6\u614b: \u98e2\u3048 / \u4e0d\u5b89]\n[\u7ba1\u7406\u8005\u30c1\u30e5\u30fc\u30c8\u30ea\u30a2\u30eb\u304c\u958b\u59cb\u3055\u308c\u307e\u3059\u3002]", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(source, "ko_ja", max_iterations=2, translate_once=translate_once)

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertEqual(result.qaIssues, [])
        self.assertEqual(len([b for b in result.finalTranslation.split("[") if "]" in b]), 3)

    def test_bracket_preserving_revision_failure_keeps_qa_warning_not_safety(self) -> None:
        source = "[\ubc15 \ud300\uc7a5]\n\ubb38\uc790.\n[\uc0c1\ud0dc: \uad76\uc8fc\ub9bc / \ubd88\uc548]\n[\uad00\ub9ac\uc790 \ud29c\ud1a0\ub9ac\uc5bc\uc774 \uc2dc\uc791\ub429\ub2c8\ub2e4.]"

        def translate_once(strict: bool, attempt: int, revision_context: str = ""):
            if not strict:
                return "\u30e1\u30c3\u30bb\u30fc\u30b8\u3002", {"delivery_status": "deliverable"}
            return "[\u30d1\u30af\u30c1\u30fc\u30e0\u9577]\n\u30e1\u30c3\u30bb\u30fc\u30b8\u3002", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(source, "ko_ja", max_iterations=2, translate_once=translate_once)

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertNotEqual(result.deliveryStatus, "blocked_translation_safety")
        self.assertTrue(any(issue["code"] == "bracket_block_count_mismatch" for issue in result.qaIssues))

    def test_ko_ja_integrity_revision_can_restore_deliverable_output(self) -> None:
        source = "휴대폰 화면에 [어머니]가 떴다.\n그는 뒤쪽 게이트로 뛰었다.\n[관리자 권한 확인 중……]"
        calls = []

        def translate_once(strict: bool, attempt: int):
            calls.append((strict, attempt))
            if not strict:
                return "携帯の画面に[管理者権限を確認中……]が浮かんだ。\n彼は裏手のゲートへ走った。\n[母]", {"delivery_status": "deliverable"}
            return "携帯の画面に[母]と表示された。\n彼は裏手のゲートへ走った。\n[管理者権限を確認中……]", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(source, "ko_ja", max_iterations=2, translate_once=translate_once)

        self.assertEqual(calls, [(False, 0), (True, 1)])
        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertEqual(result.qaIssues, [])
        self.assertEqual(result.internal["iterations"][1]["action"], "Deterministic QA Revision")

    def test_ko_ja_integrity_accepts_clean_japanese_output(self) -> None:
        result = build_v3_literary_package(
            "도윤은 문을 열었다. 휴대폰 화면에 [어머니]가 떴다.",
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("ドユンは扉を開けた。携帯の画面に[母]と表示された。", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertFalse(any(issue["code"].startswith("hangul_") or issue["code"].startswith("bracket_") for issue in result.qaIssues))


    def test_deterministic_glossary_patch_corrects_nakwon_dong_hanja_variant(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="\ub099\uc6d0\ub3d9", target="\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", category="place", priority="hard", aliases=[], forbidden=[]),
            ],
        )

        result = build_v3_literary_package(
            "\uadf8\ub294 \ub099\uc6d0\ub3d9 \uc9c0\ud558\uc0c1\uac00\ub85c \ud5a5\ud588\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\u5f7c\u306f\u697d\u5712\u6d1e\u306e\u5730\u4e0b\u5546\u5e97\u8857\u3078\u5411\u304b\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", result.finalTranslation)
        self.assertNotIn("\u697d\u5712\u6d1e", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "glossary_consistency" for issue in result.qaIssues))
        self.assertEqual(result.internal["iterations"][-1]["action"], "Deterministic Glossary Patch")

    def test_deterministic_glossary_patch_corrects_nakwon_dong_katakana_typo(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\ub099\uc6d0\ub3d9", target="\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", category="place", priority="hard")],
        )

        result = build_v3_literary_package(
            "\ub099\uc6d0\ub3d9\uc758 \uc9c0\ud558\uac00\uac00 \ub208\uc55e\uc5d0 \ud3bc\uccd0\uc84c\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\u30ca\u30b0\u30a9\u30f3\u30c9\u30f3\u306e\u5730\u4e0b\u8857\u304c\u5e83\u304c\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "glossary_consistency" for issue in result.qaIssues))

    def test_deterministic_glossary_patch_skips_when_target_already_present(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\ub099\uc6d0\ub3d9", target="\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", category="place", priority="hard")],
        )
        translation = "\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3\u3001\u697d\u5712\u6d1e\u3068\u547c\u3070\u308c\u305f\u5834\u6240\u3060\u3002"

        result = build_v3_literary_package(
            "\ub099\uc6d0\ub3d9\uc740 \uc624\ub798\ub41c \ub3d9\ub124\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: (translation, {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertEqual(result.finalTranslation, translation)
        self.assertFalse(any((it.get("action") == "Deterministic Glossary Patch") for it in result.internal["iterations"]))


    def test_known_person_residue_patch_handles_full_name_without_work_memory(self) -> None:
        result = build_v3_literary_package(
            "\uac15\ub3c4\uc724\uc740 \ubaa8\ub2c8\ud130\ub97c \ubcf4\uc558\ub2e4. [\uc0ac\uc6a9\uc790: \uac15\ub3c4\uc724]",
            "ko_ja",
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\uac15\ub3c4\uc724\u306f\u30e2\u30cb\u30bf\u30fc\u3092\u898b\u305f\u3002\n[\u30e6\u30fc\u30b6\u30fc\uff1a\uac15\ub3c4\uc724]", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f\u30e2\u30cb\u30bf\u30fc", result.finalTranslation)
        self.assertIn("[\u30e6\u30fc\u30b6\u30fc\uff1a\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3]", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_ko_ja_name_residue_patch_handles_cha_minhyeok_particle(self) -> None:
        result = build_v3_literary_package(
            "\ucc28\ubbfc\ud601\uc740 \ucc98\uc74c\ubd80\ud130 \ub9d0\ub85c \ub05d\ub0bc \uc0dd\uac01\uc774 \uc5c6\uc5c8\ub2e4.",
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("\ucc28\ubbfc\ud601\u306f\u6700\u521d\u304b\u3089\u3001\u8a00\u8449\u3067\u7247\u3092\u3064\u3051\u308b\u3064\u3082\u308a\u306a\u3069\u306a\u3044\u3088\u3046\u3060\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertEqual(result.qaIssues, [])
        self.assertIn("\u30c1\u30e3\u30fb\u30df\u30f3\u30d2\u30e7\u30af\u306f", result.finalTranslation)



    def test_known_place_variant_patch_runs_without_glossary_issue(self) -> None:
        result = build_v3_literary_package(
            "\ub099\uc6d0\ub3d9\uc758 \uc9c0\ud558\uc0c1\uac00\ub85c \ub0b4\ub824\uac14\ub2e4.",
            "ko_ja",
            max_iterations=1,
            translate_once=lambda strict, attempt: ("\u697d\u5712\u6d1e\u306e\u5730\u4e0b\u5546\u5e97\u8857\u3078\u964d\u308a\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3\u306e\u5730\u4e0b", result.finalTranslation)
        self.assertNotIn("\u697d\u5712\u6d1e", result.finalTranslation)

    def test_known_place_residue_patch_handles_nakwon_dong_without_work_memory(self) -> None:
        result = build_v3_literary_package(
            "\ub099\uc6d0\ub3d9\uc758 \uc9c0\ud558\uc0c1\uac00\ub85c \ub0b4\ub824\uac14\ub2e4.",
            "ko_ja",
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\ub099\uc6d0\ub3d9\u306e\u5730\u4e0b\u5546\u5e97\u8857\u3078\u964d\u308a\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3\u306e\u5730\u4e0b", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_hard_glossary_source_residue_replaces_korean_particle(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard")],
        )

        result = build_v3_literary_package(
            "\uac15\ub3c4\uc724\uc740 \ubaa8\ub2c8\ud130 \uc624\ub978\ucabd \uc544\ub798\uc758 \uc2dc\uac01\uc744 \ubcf4\uc558\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\uac15\ub3c4\uc724\uc740 \u30e2\u30cb\u30bf\u30fc\u53f3\u4e0b\u306b\u8868\u793a\u3055\u308c\u305f\u6642\u523b\u3092\u898b\u3066\u3044\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f \u30e2\u30cb\u30bf\u30fc", result.finalTranslation)
        self.assertNotIn("\uac15\ub3c4\uc724", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_hard_glossary_source_residue_replaces_attached_japanese_particle(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard")],
        )

        result = build_v3_literary_package(
            "\uac15\ub3c4\uc724\uc740 \ud53c\uace4\ud55c \uc5bc\uad74\uc744 \ub450 \uc190\uc73c\ub85c \ubb38\uc9c8\ub800\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\uac15\ub3c4\uc724\u306f\u75b2\u308c\u5207\u3063\u305f\u9854\u3092\u4e21\u624b\u3067\u3053\u3059\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f\u75b2\u308c\u5207\u3063\u305f\u9854\u3092", result.finalTranslation)
        self.assertNotIn("\uac15\ub3c4\uc724", result.finalTranslation)

    def test_hard_glossary_source_residue_replaces_bracket_system_ui(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard")],
        )

        result = build_v3_literary_package(
            "[\uc0ac\uc6a9\uc790: \uac15\ub3c4\uc724] \uba54\uc2dc\uc9c0\uac00 \ub5b4\uc62c\ub790\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("[\u30e6\u30fc\u30b6\u30fc\uff1a\uac15\ub3c4\uc724]\u30e1\u30c3\u30bb\u30fc\u30b8\u304c\u6d6e\u304b\u3093\u3060\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("[\u30e6\u30fc\u30b6\u30fc\uff1a\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3]", result.finalTranslation)
        self.assertNotIn("\uac15\ub3c4\uc724", result.finalTranslation)

    def test_hard_glossary_source_residue_replaces_even_when_target_already_exists(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard")],
        )

        result = build_v3_literary_package(
            "\uac15\ub3c4\uc724\uc740 \ubaa8\ub2c8\ud130\ub97c \ubcf4\uc558\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\uac15\ub3c4\uc724\uc740 \u30e2\u30cb\u30bf\u30fc\u3092\u898b\u305f\u3002\u5f8c\u306b\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f\u7acb\u3061\u4e0a\u304c\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f \u30e2\u30cb\u30bf\u30fc", result.finalTranslation)
        self.assertIn("\u5f8c\u306b\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f", result.finalTranslation)
        self.assertNotIn("\uac15\ub3c4\uc724", result.finalTranslation)

    def test_hard_glossary_source_residue_skips_when_source_absent_from_source_text(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard")],
        )

        result = build_v3_literary_package(
            "\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\uac15\ub3c4\uc724\u306f\u6249\u3092\u958b\u3051\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertIn("\uac15\ub3c4\uc724", result.finalTranslation)
        self.assertTrue(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))
        self.assertFalse(any((it.get("action") == "Deterministic Glossary Patch") for it in result.internal["iterations"]))

    def test_hard_glossary_source_residue_patch_does_not_translate_general_korean_sentence(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard")],
        )

        result = build_v3_literary_package(
            "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3\u306f\u6249\u3092\u958b\u3051\u305f\u3002 \uc218\uc120\uc740 \uc544\uc9c1 \ub05d\ub098\uc9c0 \uc54a\uc558\ub2e4.", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertIn("\uc218\uc120\uc740", result.finalTranslation)
        self.assertTrue(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_deterministic_glossary_patch_skips_entry_absent_from_source(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\ub099\uc6d0\ub3d9", target="\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", category="place", priority="hard")],
        )

        result = build_v3_literary_package(
            "\uadf8\ub294 \uc9c0\ud558\uc0c1\uac00\ub85c \ud5a5\ud588\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\u5f7c\u306f\u697d\u5712\u6d1e\u306e\u5730\u4e0b\u5546\u5e97\u8857\u3078\u5411\u304b\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u697d\u5712\u6d1e", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "glossary_consistency" for issue in result.qaIssues))

    def test_glossary_alias_matching_ignores_alias_that_is_separate_source(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard", aliases=["\ub3c4\uc724"]),
                GlossaryEntry(source="\ub3c4\uc724", target="\u30c9\u30e6\u30f3", category="person", priority="hard", aliases=["\uac15\ub3c4\uc724"]),
            ],
        )

        result = build_v3_literary_package(
            "\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=1,
            translate_once=lambda strict, attempt: ("\u30c9\u30e6\u30f3\u306f\u6249\u3092\u958b\u3051\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        messages = "\n".join(issue["message"] for issue in result.qaIssues)
        self.assertNotIn("\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", messages)

    def test_glossary_alias_policy_still_checks_direct_full_name(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[
                GlossaryEntry(source="\uac15\ub3c4\uc724", target="\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3", category="person", priority="hard", aliases=["\ub3c4\uc724"]),
                GlossaryEntry(source="\ub3c4\uc724", target="\u30c9\u30e6\u30f3", category="person", priority="hard", aliases=["\uac15\ub3c4\uc724"]),
            ],
        )

        result = build_v3_literary_package(
            "\uac15\ub3c4\uc724\uc740 \ubb38\uc744 \uc5f4\uc5c8\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=1,
            translate_once=lambda strict, attempt: ("\u30c9\u30e6\u30f3\u306f\u6249\u3092\u958b\u3051\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        issues = [issue for issue in result.qaIssues if issue["code"] == "glossary_consistency"]
        self.assertTrue(any(issue["targetSpan"] == "\u30ab\u30f3\u30fb\u30c9\u30e6\u30f3" for issue in issues))
        self.assertEqual(result.deliveryStatus, "qa_warning")

    def test_deterministic_glossary_patch_failure_keeps_qa_warning_not_safety_block(self) -> None:
        memory = WorkMemory(
            workId="work-glossary",
            targetLocale="ko_ja",
            approvedGlossary=[GlossaryEntry(source="\ub099\uc6d0\ub3d9", target="\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3", category="place", priority="hard")],
        )

        result = build_v3_literary_package(
            "\ub099\uc6d0\ub3d9\uc73c\ub85c \uac14\ub2e4.",
            "ko_ja",
            work_memory=memory,
            max_iterations=2,
            translate_once=lambda strict, attempt: ("\u5f7c\u306f\u5730\u4e0b\u5546\u5e97\u8857\u3078\u884c\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertNotEqual(result.deliveryStatus, "blocked_translation_safety")
        self.assertTrue(any(issue["code"] == "glossary_consistency" for issue in result.qaIssues))





    def test_bracket_contact_label_hangul_residue_patch_is_limited_to_bracket(self) -> None:
        source = "[\uc5b4\uba38\ub2c8] \uc804\ud654\uac00 \uc654\ub2e4."

        def translate_once(strict: bool, attempt: int):
            return "[\uc5b4\uba38\ub2c8]\n\u96fb\u8a71\u304c\u6765\u305f\u3002", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(source, "ko_ja", max_iterations=2, translate_once=translate_once)

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("[\u6bcd]", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_system_ui_hangul_residue_patch_replaces_short_term_inside_bracket(self) -> None:
        source = "[\uc0c1\ud0dc: \uad76\uc8fc\ub9bc / \ubd88\uc548 / \uc601\uc5ed \ubc29\uc5b4 \uc911]"

        def translate_once(strict: bool, attempt: int):
            return "[\u72b6\u614b: \u98e2\u3048 / \u4e0d\u5b89 / \uc601\uc5ed\u9632\u885b\u4e2d]", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(source, "ko_ja", max_iterations=2, translate_once=translate_once)

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("[\u72b6\u614b: \u98e2\u3048 / \u4e0d\u5b89 / \u9818\u57df\u9632\u885b\u4e2d]", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))
        self.assertEqual(result.internal["iterations"][-1]["action"], "Deterministic System UI Hangul Residue Patch")

    def test_system_ui_hangul_residue_patch_replaces_full_korean_phrase_only_in_bracket(self) -> None:
        source = "[\uc0c1\ud0dc: \uad76\uc8fc\ub9bc / \ubd88\uc548 / \uc601\uc5ed \ubc29\uc5b4 \uc911] \uadf8\ub294 \uc601\uc5ed\uc744 \ub5a0\uc62c\ub838\ub2e4."

        def translate_once(strict: bool, attempt: int):
            return "[\uc0c1\ud0dc: \uad76\uc8fc\ub9bc / \ubd88\uc548 / \uc601\uc5ed \ubc29\uc5b4 \uc911] \u5f7c\u306f\uc601\uc5ed\u3092\u601d\u3044\u51fa\u3057\u305f\u3002", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(source, "ko_ja", max_iterations=2, translate_once=translate_once)

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertIn("[\u72b6\u614b: \u98e2\u3048 / \u4e0d\u5b89 / \u9818\u57df\u9632\u885b\u4e2d]", result.finalTranslation)
        self.assertIn("\uc601\uc5ed\u3092", result.finalTranslation)
        self.assertTrue(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_system_ui_hangul_residue_patch_does_not_replace_general_prose(self) -> None:
        def translate_once(strict: bool, attempt: int):
            return "\u5f7c\u306f \uc601\uc5ed \u9632\u885b \u4e2d\u3060\u3068\u8a00\u3063\u305f\u3002", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(
            "\uadf8\ub294 \uc601\uc5ed \ubc29\uc5b4 \uc911\uc774\ub77c\uace0 \ub9d0\ud588\ub2e4.".replace("\u0008", ""),
            "ko_ja",
            max_iterations=2,
            translate_once=translate_once,
        )

        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertIn("\uc601\uc5ed", result.finalTranslation)
        self.assertTrue(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))
        self.assertFalse(any((it.get("action") == "Deterministic System UI Hangul Residue Patch") for it in result.internal["iterations"]))

    def test_hangul_residue_patch_translates_only_short_sign_labels(self) -> None:
        def translate_once(strict: bool, attempt: int):
            if not strict:
                return "\uc218\uc120 \ubd84\uc2dd", {"delivery_status": "deliverable"}
            return "\u53e4\u3044\u30c1\u30e9\u30b7\u306b\u300e\uc218\uc120\u300f\u300e\ubd84\uc2dd\u300f\u3068\u66f8\u304b\u308c\u3066\u3044\u305f\u3002", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(
            "\uacc4\ub2e8\uc5d0\ub294 \u2018\uc218\uc120\u2019, \u2018\ubd84\uc2dd\u2019 \uac19\uc740 \uae00\uc790\uac00 \ub0a8\uc544 \uc788\uc5c8\ub2e4.",
            "ko_ja",
            max_iterations=2,
            translate_once=translate_once,
        )

        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertIn("\u300e\u4fee\u7406\u300f", result.finalTranslation)
        self.assertIn("\u300e\u8efd\u98df\u300f", result.finalTranslation)
        self.assertFalse(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))

    def test_hangul_residue_patch_does_not_translate_general_dialogue_or_prose(self) -> None:
        calls = []

        def translate_once(strict: bool, attempt: int):
            calls.append((strict, attempt))
            if not strict:
                return "\uc218\uc120\uc740 \uc544\uc9c1 \ub05d\ub098\uc9c0 \uc54a\uc558\ub2e4.", {"delivery_status": "deliverable"}
            return "\u300c\uc218\uc120\uc740 \uc544\uc9c1 \ub05d\ub098\uc9c0 \uc54a\uc558\ub2e4\u300d\u3068\u5f7c\u306f\u8a00\u3063\u305f\u3002", {"delivery_status": "deliverable"}

        result = build_v3_literary_package(
            "\uadf8\ub294 \uc218\uc120\uc740 \uc544\uc9c1 \ub05d\ub098\uc9c0 \uc54a\uc558\ub2e4\uace0 \ub9d0\ud588\ub2e4.",
            "ko_ja",
            max_iterations=2,
            translate_once=translate_once,
        )

        self.assertEqual(calls, [(False, 0), (True, 1)])
        self.assertEqual(result.deliveryStatus, "qa_warning")
        self.assertIn("\uc218\uc120", result.finalTranslation)
        self.assertTrue(any(issue["code"] == "hangul_residue_integrity" for issue in result.qaIssues))
        self.assertFalse(any((it.get("action") == "Deterministic Hangul Residue Patch") for it in result.internal["iterations"]))

    def test_common_location_noun_residue_is_not_name_residue(self) -> None:
        result = build_v3_literary_package(
            "\uadf8\ub294 \ub099\uc6d0\ub3d9 \uc9c0\ud558\uc0c1\uac00\ub85c \ub3cc\uc544\uac14\ub2e4.",
            "ko_ja",
            max_iterations=2,
            translate_once=lambda strict, attempt, revision_context="": ("\u30ca\u30af\u30a6\u30a9\u30f3\u30c9\u30f3 \uc9c0\ud558\uc0c1\uac00\u306b\u623b\u3063\u305f\u3002", {"delivery_status": "deliverable"}),
        )

        spans = result.qaIssues[0]["details"]["spans"]
        self.assertEqual(spans[0]["residueCategory"], "genre_term_residue")
        self.assertFalse(spans[0]["personNameRisk"])
        self.assertTrue(spans[0]["commonNounResidueDetected"])
        self.assertTrue(spans[0]["nameResidueFalsePositiveAvoided"])

    def test_mixed_script_partial_name_residue_expands_to_whole_token(self) -> None:
        result = build_v3_literary_package(
            "\ucca0\uc218\uac00 \uc678\ucce4\ub2e4.",
            "ko_ja",
            max_iterations=2,
            translate_once=lambda strict, attempt, revision_context="": ("\u9244\uc218\uff01", {"delivery_status": "deliverable"}),
        )

        first_critique = result.internal["iterations"][0]["critique"]
        spans = first_critique[0]["details"]["spans"]
        self.assertEqual(spans[0]["text"], "\u9244\uc218")
        self.assertEqual(spans[0]["residueCategory"], "mixed_script_name_residue")
        self.assertTrue(spans[0]["mixedScriptNameResidueDetected"])
        self.assertTrue(spans[0]["partialNameResidueDetected"])
        self.assertEqual(spans[0]["repairAffectedToken"], "\u9244\uc218")
        self.assertEqual(result.deliveryStatus, "deliverable")
        self.assertNotIn("\uc218", result.finalTranslation)


if __name__ == "__main__":
    unittest.main()
