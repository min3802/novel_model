from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import backend.services.translation_service as translation_service_module
from app.translation import DEFAULT_QUALITY_MODE, MODEL_PROFILES, PipelineConfig, TranslationMode, TranslationPipeline
from app.translation.infra.country_locale import resolve_country_for_locale
from app.translation.retrieval.annotation_retriever import AnnotationResult
from app.translation.retrieval.retriever import RetrievalResult
from app.translation.v2_pipeline import (
    DirectTranslationResult,
    PatchProposer,
    PostTranslationQA,
    QAItem,
    REQUIRED_EVALUATION_PHRASES,
    RiskItem,
    SourceSideAnalyzer,
    V2TranslationResult,
    build_evaluation_markdown,
    split_user_visible_qa_report,
    split_user_visible_risk_items,
)
from app.translation.v2_dual_draft_review import (
    AuthorReviewCard,
    AuthorReviewCardGenerator,
    V2DualDraftReviewResult,
    MeaningDraft,
    MeaningDraftTranslator,
    RagEvidence,
    TranslationDecisionAnalyzer,
    risk_item_to_rag_evidence,
)
from backend.services.translation_service import translate


class TranslationV2PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["WLIGHTER_MOCK_MODE"] = "true"

    def _config(self) -> PipelineConfig:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)

        idiom_dataset = base / "idiom_dataset.json"
        idiom_dataset.write_text(
            json.dumps(
                [
                    {
                        "id": "idiom_001",
                        "source_id": "idiom_001",
                        "embedding_text": "노는 물. 사람의 처지나 활동 무대가 달라지는 상황을 가리키는 표현.",
                        "context_text": "한국어 기준 표현: 노는 물\n일본어 후보: 住む世界 / 活躍の場 / ステージ",
                        "ko_anchor_expression": ["노는 물"],
                        "ko_expression": ["노는 물"],
                        "matched_phrase": "노는 물",
                        "evidence_chunk": "그녀가 노는 물은 이제 대한민국을 넘어 세계로 향하고 있었다.",
                        "expression": "住む世界",
                        "meaning": "사람의 활동 무대나 수준이 달라졌음을 뜻한다.",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        annotation_dataset = base / "annotation_dataset.json"
        annotation_dataset.write_text(
            json.dumps(
                [
                    {
                        "id": "anno_001",
                        "keyword_ko": "한복",
                        "context_text": "일본어 후보: 韓服 / チマチョゴリ",
                        "embedding_text": "hanbok traditional korean clothing note",
                        "category": ["culture"],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        return PipelineConfig(
            locale="ko_ja",
            mode=TranslationMode.LEGACY_FULL,
            rag_dataset_path=idiom_dataset,
            annotation_dataset_path=annotation_dataset,
            score_threshold=0.0,
            annotation_score_threshold=0.0,
            mock=True,
            embedding_cache_dir=base / "cache",
        )

    def _idiom_row(self, *, source_id: str, matched_phrase: str, evidence_chunk: str, final_score: float = 0.9) -> RetrievalResult:
        return RetrievalResult(
            item={
                "source_id": source_id,
                "matched_phrase": matched_phrase,
                "evidence_chunk": evidence_chunk,
                "context_text": f"한국어 기준 표현: {matched_phrase}\n일본어 후보: ダミー候補",
                "embedding_text": f"{matched_phrase}, 테스트용 관용어 설명",
                "meaning": "테스트용 의미",
            },
            score=final_score,
            similarity_score=final_score,
            anchor_boost=0.0,
            final_score=final_score,
        )

    def _make_review_decision(
        self,
        *,
        decision_id: str,
        decision_type: str,
        source_span: str,
        meaning_draft_span: str,
        vibe_translation_span: str,
        reason: str,
        evidence_ids: list[str],
        author_note: str,
        confidence: str,
        needs_author_review: bool,
        risk_level: str,
    ):
        return type(
            "_DecisionStub",
            (),
            {
                "id": decision_id,
                "source_span": source_span,
                "meaning_draft_span": meaning_draft_span,
                "vibe_translation_span": vibe_translation_span,
                "decision_type": decision_type,
                "reason": reason,
                "evidence_ids": evidence_ids,
                "author_note": author_note,
                "confidence": confidence,
                "needs_author_review": needs_author_review,
                "risk_level": risk_level,
                "source_start": None,
                "source_end": None,
                "target_span": "",
                "target_start": None,
                "target_end": None,
                "alignment_status": "target_unresolved",
                "priority": "P1",
                "card_status": "pending",
                "unresolved_risk": decision_type == "risk_unresolved",
                "suggested_actions": [],
            },
        )()

    def test_legacy_full_still_runs(self) -> None:
        pipeline = TranslationPipeline(self._config())
        result = pipeline.run_with_inspection("그녀가 노는 물이 달라졌다.")
        self.assertFalse(result.blocked)
        self.assertIn("translation", result.draft)
        self.assertIn("summary", result.inspection)

    def test_direct_only_skips_retrieval_review_and_inspection(self) -> None:
        pipeline = TranslationPipeline(self._config())

        def fail(*args, **kwargs):
            raise AssertionError("unexpected call")

        pipeline.retriever.search = fail  # type: ignore[assignment]
        pipeline.annotation_retriever.search = fail  # type: ignore[assignment]
        pipeline.inspector.inspect = fail  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = fail  # type: ignore[assignment]

        result = pipeline.run_direct_only("그녀가 노는 물이 달라졌다.")

        self.assertEqual(result.mode, "direct_only")
        self.assertTrue(result.final_translation)
        self.assertFalse(result.metadata["rag_enabled"])
        self.assertFalse(result.metadata["review_enabled"])
        self.assertFalse(result.metadata["inspection_enabled"])


    def test_direct_only_blocks_when_translation_safety_still_fails(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "그는 마운드 위에 섰다."
        fail_translation = source_text
        fail_safety = TranslationPipeline._translation_safety_checks(
            source_text=source_text,
            final_translation=fail_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        initial_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=fail_translation,
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=fail_safety,
            ),
        )
        retry_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=fail_translation,
            draft={"prompt_debug": {"prompt_hash": "retry-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=fail_safety,
            ),
        )
        calls = iter([initial_result, retry_result])
        pipeline._run_direct_translation_once = lambda *args, **kwargs: next(calls)  # type: ignore[assignment]

        result = pipeline.run_direct_only(source_text)

        self.assertEqual(result.delivery_status, "blocked_translation_safety")
        self.assertEqual(result.user_visible_error_code, "translation_safety_failed")
        self.assertTrue(result.metadata["translation_safety_retry_attempted"])
        self.assertEqual(result.metadata["translation_safety_retry_count"], 1)
        self.assertFalse(result.metadata["retry_success"])

    def test_v2_direct_qa_returns_filtered_and_grouped_fields(self) -> None:
        pipeline = TranslationPipeline(self._config())
        result = pipeline.run_v2_direct_qa("그녀가 노는 물이 달라졌다. 한복을 입었다.")

        self.assertEqual(result.mode, "v2_direct_qa")
        self.assertIsInstance(result.risk_items, list)
        self.assertIsInstance(result.qa_report, list)
        self.assertIsInstance(result.user_visible_risk_items, list)
        self.assertIsInstance(result.user_visible_qa_report, dict)
        self.assertIn("확인 필요", result.user_visible_qa_report)
        self.assertTrue(result.risk_items)

    def test_rag_evidence_adapter_maps_risk_item_to_rag_evidence(self) -> None:
        risk_item = RiskItem(
            id="idiom:001",
            type="idiom",
            source_span="밥 한번 먹자",
            anchor="밥 한번 먹자",
            meaning_ko="식사 제안 또는 관계 유지용 완곡 표현",
            target_candidates=["let's eat sometime", "have a meal sometime"],
            confidence="high",
            policy="check_after_translation",
            source="rag",
            visibility_bucket="?뺤씤 ?꾩슂",
            user_visible=True,
            debug_reason="idiom score=0.912",
        )

        evidence = risk_item_to_rag_evidence(risk_item)

        self.assertIsInstance(evidence, RagEvidence)
        self.assertEqual(evidence.source_span, "밥 한번 먹자")
        self.assertEqual(evidence.anchor, "밥 한번 먹자")
        self.assertEqual(evidence.evidence_type, "idiom")
        self.assertEqual(evidence.literal_meaning, "식사 제안 또는 관계 유지용 완곡 표현")
        self.assertIn("reference only", " | ".join(evidence.strategy_hints))
        self.assertEqual(evidence.candidate_translations, ["let's eat sometime", "have a meal sometime"])
        self.assertTrue(evidence.user_visible)
        self.assertEqual(evidence.source, "idiom_rag")
        self.assertNotIn("force", evidence.__dataclass_fields__)
        self.assertNotIn("must_apply", evidence.__dataclass_fields__)
        self.assertNotIn("required_translation", evidence.__dataclass_fields__)

    def test_meaning_draft_translator_uses_seed_or_deterministic_fallback(self) -> None:
        translator = MeaningDraftTranslator(self._config())
        seeded = translator.translate(
            "아무 말이나",
            locale="ko_ja",
            seed_translation="seed meaning text",
        )
        fallback = translator.translate(
            "",
            locale="ko_ja",
            seed_translation=None,
        )

        self.assertEqual(seeded.text, "seed meaning text")
        self.assertIsInstance(seeded.text, str)
        self.assertEqual(fallback.text, "")
        self.assertEqual(seeded.purpose, "semantic_baseline")
        self.assertEqual(seeded.temperature_profile, "low")

    def test_v2_dual_draft_review_populates_rag_evidence_from_analyzer(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "밥 한번 먹자고 말했다."
        risk_item = RiskItem(
            id="idiom:002",
            type="idiom",
            source_span="밥 한번 먹자",
            anchor="밥 한번 먹자",
            meaning_ko="식사 제안 또는 관계 유지용 완곡 표현",
            target_candidates=["let's eat sometime"],
            confidence="high",
            policy="check_after_translation",
            source="rag",
            visibility_bucket="?뺤씤 ?꾩슂",
            user_visible=True,
            debug_reason="idiom score=0.901",
        )

        pipeline.source_side_analyzer.analyze = lambda text: [risk_item]  # type: ignore[assignment]
        pipeline.run_direct_only = lambda *args, **kwargs: DirectTranslationResult(  # type: ignore[assignment]
            mode="direct_only",
            final_translation="translated text",
            draft={"prompt_debug": {"prompt_hash": "stub-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=TranslationPipeline._locale_adherence_metadata(
                    source_text=source_text,
                    final_translation="translated text",
                    locale="ko_ja",
                    target_language_name="Japanese",
                ),
            ),
            delivery_status="deliverable",
            user_visible_error_code=None,
        )

        result = pipeline.run_v2_dual_draft_review(source_text)

        self.assertIsInstance(result.rag_evidence, list)
        self.assertEqual(len(result.rag_evidence), 1)
        evidence = result.rag_evidence[0]
        self.assertIsInstance(evidence, RagEvidence)
        self.assertEqual(evidence.source_id, "idiom:002")
        self.assertEqual(evidence.candidate_translations, ["let's eat sometime"])
        self.assertTrue(evidence.user_visible)
        self.assertFalse(hasattr(evidence, "force"))
        self.assertFalse(hasattr(evidence, "must_apply"))
        self.assertFalse(hasattr(evidence, "required_translation"))

    def test_v2_dual_draft_review_populates_meaning_draft_from_translator(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "그는 마을의 주인이다."
        pipeline.source_side_analyzer.analyze = lambda text: []  # type: ignore[assignment]
        pipeline.run_direct_only = lambda *args, **kwargs: DirectTranslationResult(  # type: ignore[assignment]
            mode="direct_only",
            final_translation="translated text",
            draft={"prompt_debug": {"prompt_hash": "meaning-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=TranslationPipeline._locale_adherence_metadata(
                    source_text=source_text,
                    final_translation="translated text",
                    locale="ko_ja",
                    target_language_name="Japanese",
                ),
            ),
            delivery_status="deliverable",
            user_visible_error_code=None,
        )

        result = pipeline.run_v2_dual_draft_review(source_text)

        self.assertEqual(result.final_translation, "translated text")
        self.assertEqual(result.meaning_draft.text, "translated text")
        self.assertEqual(result.meaning_draft.purpose, "semantic_baseline")
        self.assertEqual(result.meaning_draft.temperature_profile, "low")

    def test_translate_service_exposes_dual_draft_review_fields(self) -> None:
        country = resolve_country_for_locale("ko_ja")
        direct_result = translate(
            {
                "targetCountry": country,
                "sourceText": "그는 마을의 주인이다.",
                "mode": "direct_only",
            }
        )
        result = translate(
            {
                "targetCountry": country,
                "sourceText": "그는 마을의 주인이다.",
                "mode": "v2_dual_draft_review",
            }
        )

        self.assertEqual(result["mode"], "v2_dual_draft_review")
        self.assertIn("meaningDraft", result)
        self.assertIn("ragEvidence", result)
        self.assertIn("translationDecisions", result)
        self.assertIn("authorReviewCards", result)
        self.assertIn("deliveryStatus", result)
        self.assertIn("userVisibleErrorCode", result)
        self.assertEqual(result["finalTranslation"], direct_result["finalTranslation"])
        self.assertIn("text", result["meaningDraft"])
        self.assertEqual(result["authorReviewCards"], [])
        self.assertIsInstance(result["ragEvidence"], list)

    def test_v2_dual_draft_review_shell_reuses_direct_translation(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "그는 마을의 주인이다."

        direct_result = pipeline.run_direct_only(source_text)
        dual_result = pipeline.run_v2_dual_draft_review(source_text)

        self.assertEqual(dual_result.mode, "v2_dual_draft_review")
        self.assertEqual(dual_result.final_translation, direct_result.final_translation)
        self.assertEqual(dual_result.delivery_status, direct_result.delivery_status)
        self.assertEqual(dual_result.user_visible_error_code, direct_result.user_visible_error_code)
        if direct_result.delivery_status == "deliverable":
            self.assertEqual(dual_result.meaning_draft.text, direct_result.final_translation)
        else:
            self.assertEqual(dual_result.meaning_draft.text, "")
        self.assertEqual(dual_result.rag_evidence, [])
        self.assertEqual(dual_result.translation_decisions, [])
        self.assertEqual(dual_result.author_review_cards, [])

    def test_v2_dual_draft_review_populates_author_review_cards(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "have a meal sometime"
        risk_item = RiskItem(
            id="idiom:010",
            type="idiom",
            source_span="have a meal sometime",
            anchor="have a meal sometime",
            meaning_ko="관계 유지용 완곡 표현",
            target_candidates=["let's eat sometime"],
            confidence="high",
            policy="check_after_translation",
            source="rag",
            visibility_bucket="확인 필요",
            user_visible=True,
            debug_reason="idiom score=0.93",
        )

        pipeline.source_side_analyzer.analyze = lambda text: [risk_item]  # type: ignore[assignment]
        pipeline.run_direct_only = lambda *args, **kwargs: DirectTranslationResult(  # type: ignore[assignment]
            mode="direct_only",
            final_translation="have a meal sometime",
            draft={"prompt_debug": {"prompt_hash": "card-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=TranslationPipeline._locale_adherence_metadata(
                    source_text=source_text,
                    final_translation="have a meal sometime",
                    locale="ko_ja",
                    target_language_name="Japanese",
                ),
            ),
            delivery_status="deliverable",
            user_visible_error_code=None,
        )

        result = pipeline.run_v2_dual_draft_review(source_text)

        self.assertTrue(result.translation_decisions)
        self.assertTrue(result.author_review_cards)
        decision = result.translation_decisions[0]
        self.assertEqual(decision.source_start, 0)
        self.assertEqual(decision.source_end, len(source_text))
        self.assertEqual(decision.target_span, source_text)
        self.assertEqual(decision.target_start, 0)
        self.assertEqual(decision.target_end, len(source_text))
        self.assertEqual(decision.alignment_status, "exact")
        self.assertEqual(decision.priority, "P1")
        self.assertEqual(decision.card_status, "pending")
        self.assertFalse(decision.unresolved_risk)
        self.assertIsInstance(decision.suggested_actions, list)
        card = result.author_review_cards[0]
        self.assertIsInstance(card, AuthorReviewCard)
        self.assertEqual(card.decision_label, "원어 유지")
        self.assertIn("keep", [option["id"] for option in card.options])
        self.assertIn("review", [option["id"] for option in card.options])
        self.assertIsNone(card.patch_suggestion)
        self.assertEqual(card.priority, decision.priority)
        self.assertEqual(card.status, decision.card_status)
        self.assertEqual(card.target_span, decision.target_span)
        self.assertEqual(card.suggested_actions, decision.suggested_actions)
        self.assertEqual(card.created_from_evidence_ids, decision.evidence_ids)

    def test_v2_dual_draft_review_blocks_keep_safety_contract(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "그는 마을의 주인이다."
        blocked_translation = ""
        blocked_safety = TranslationPipeline._translation_safety_checks(
            source_text=source_text,
            final_translation=blocked_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        blocked_direct = DirectTranslationResult(
            mode="direct_only",
            final_translation=blocked_translation,
            draft={"prompt_debug": {"prompt_hash": "blocked-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=blocked_safety,
            ),
            delivery_status="blocked_translation_safety",
            user_visible_error_code="translation_safety_failed",
        )
        pipeline.run_direct_only = lambda *args, **kwargs: blocked_direct  # type: ignore[assignment]

        result = pipeline.run_v2_dual_draft_review(source_text)

        self.assertEqual(result.delivery_status, "blocked_translation_safety")
        self.assertEqual(result.user_visible_error_code, "translation_safety_failed")
        self.assertEqual(result.final_translation, "")
        self.assertEqual(result.author_review_cards, [])
        self.assertEqual(result.rag_evidence, [])
        self.assertEqual(result.translation_decisions, [])
        self.assertEqual(result.metadata["translation_decision_count"], 0)
        self.assertEqual(result.metadata["author_review_card_count"], 0)

    def test_translation_decision_analyzer_uses_user_visible_evidence(self) -> None:
        analyzer = TranslationDecisionAnalyzer(self._config())
        evidence = RagEvidence(
            id="evidence:001",
            source_span="have a meal sometime",
            anchor="have a meal sometime",
            evidence_type="idiom",
            literal_meaning="literal meal invitation",
            pragmatic_function="casual relational cue",
            tone="soft",
            cultural_meaning="",
            literal_risk="literal translation may miss the intended figurative meaning",
            strategy_hints=["reference only; do not force the candidate translation"],
            candidate_translations=["let's eat sometime"],
            confidence="high",
            source="idiom_rag",
            source_id="risk:001",
            user_visible=True,
        )

        decisions = analyzer.analyze(
            [evidence],
            MeaningDraft(text="meaning draft baseline", model="mock-model"),
            "We should have a meal sometime.",
            source_text="have a meal sometime",
            locale="ko_ja",
        )

        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision.decision_type, "preserved")
        self.assertTrue(decision.needs_author_review)
        self.assertEqual(decision.evidence_ids, ["risk:001", "evidence:001"])
        self.assertIn("보존 여부", decision.reason)
        self.assertTrue(decision.author_note)
        self.assertEqual(decision.source_span, "have a meal sometime")
        self.assertEqual(decision.source_start, 0)
        self.assertEqual(decision.source_end, len("have a meal sometime"))
        self.assertEqual(decision.target_span, "have a meal sometime")
        self.assertEqual(decision.target_start, "We should have a meal sometime.".find("have a meal sometime"))
        self.assertEqual(decision.target_end, decision.target_start + len("have a meal sometime"))
        self.assertEqual(decision.alignment_status, "exact")
        self.assertEqual(decision.priority, "P1")
        self.assertEqual(decision.card_status, "pending")
        self.assertFalse(decision.unresolved_risk)
        self.assertEqual(decision.suggested_actions, ["현재 번역 유지 검토"])

    def test_translation_decision_analyzer_defaults_to_risk_unresolved(self) -> None:
        analyzer = TranslationDecisionAnalyzer(self._config())
        evidence = RagEvidence(
            id="evidence:002",
            source_span="culture phrase",
            anchor="culture phrase",
            evidence_type="annotation",
            literal_meaning="cultural note",
            pragmatic_function="context-sensitive cue",
            tone="",
            cultural_meaning="culture note",
            literal_risk="literal translation may omit the context",
            strategy_hints=["consider an explanatory note"],
            candidate_translations=[],
            confidence="medium",
            source="annotation_rag",
            source_id="risk:002",
            user_visible=True,
        )

        decisions = analyzer.analyze(
            [evidence],
            MeaningDraft(text="baseline", model="mock-model"),
            "translated text with no matching span",
            source_text="culture phrase",
            locale="ko_ja",
        )

        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].decision_type, "risk_unresolved")
        self.assertIn("작가 검수", decisions[0].reason)
        self.assertEqual(decisions[0].source_start, 0)
        self.assertEqual(decisions[0].source_end, len("culture phrase"))
        self.assertEqual(decisions[0].target_span, "")
        self.assertIsNone(decisions[0].target_start)
        self.assertIsNone(decisions[0].target_end)
        self.assertEqual(decisions[0].alignment_status, "target_unresolved")
        self.assertEqual(decisions[0].priority, "P1")
        self.assertEqual(decisions[0].card_status, "pending")
        self.assertTrue(decisions[0].unresolved_risk)
        self.assertEqual(decisions[0].suggested_actions, ["작가 검토"])

    def test_translation_decision_analyzer_skips_hidden_evidence(self) -> None:
        analyzer = TranslationDecisionAnalyzer(self._config())
        evidence = RagEvidence(
            id="evidence:003",
            source_span="internal note",
            anchor="internal note",
            evidence_type="term",
            literal_meaning="internal term",
            pragmatic_function="terminology handling",
            tone="",
            cultural_meaning="",
            literal_risk="internal only",
            strategy_hints=["internal debug"],
            candidate_translations=[],
            confidence="low",
            source="terminology",
            source_id="risk:003",
            user_visible=False,
        )

        decisions = analyzer.analyze(
            [evidence],
            MeaningDraft(text="baseline", model="mock-model"),
            "translated text",
            source_text="internal note",
            locale="ko_ja",
        )

        self.assertEqual(decisions, [])

    def test_translation_decision_analyzer_skips_low_confidence_visible_evidence(self) -> None:
        analyzer = TranslationDecisionAnalyzer(self._config())
        evidence = RagEvidence(
            id="evidence:004",
            source_span="maybe important phrase",
            anchor="maybe important phrase",
            evidence_type="pragmatic",
            literal_meaning="maybe important",
            pragmatic_function="context cue",
            tone="",
            cultural_meaning="",
            literal_risk="uncertain",
            strategy_hints=["debug only"],
            candidate_translations=[],
            confidence="low",
            source="source_side_analyzer",
            source_id="risk:004",
            user_visible=True,
        )

        decisions = analyzer.analyze(
            [evidence],
            MeaningDraft(text="baseline", model="mock-model"),
            "translated text",
            source_text="maybe important phrase",
            locale="ko_ja",
        )

        self.assertEqual(decisions, [])

    def test_author_review_card_generator_turns_review_decisions_into_cards(self) -> None:
        generator = AuthorReviewCardGenerator(self._config())
        decision = self._make_review_decision(
            decision_id="decision:001",
            decision_type="risk_unresolved",
            source_span="have a meal sometime",
            meaning_draft_span="meaning baseline",
            vibe_translation_span="We should have a meal sometime.",
            reason="literal translation may miss the intended figurative meaning. 작가 검수가 필요합니다.",
            evidence_ids=["risk:001", "evidence:001"],
            author_note="이 표현의 핵심이 실제 의미인가요, 관계성이나 톤인가요?",
            confidence="high",
            needs_author_review=True,
            risk_level="medium",
        )
        evidence = RagEvidence(
            id="evidence:001",
            source_span="have a meal sometime",
            anchor="have a meal sometime",
            evidence_type="idiom",
            literal_meaning="literal meal invitation",
            pragmatic_function="casual relational cue",
            tone="soft",
            cultural_meaning="",
            literal_risk="literal translation may miss the intended figurative meaning",
            strategy_hints=["reference only"],
            candidate_translations=["let's eat sometime"],
            confidence="high",
            source="idiom_rag",
            source_id="risk:001",
            user_visible=True,
        )

        cards = generator.generate([decision], rag_evidence=[evidence])

        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertIsInstance(card, AuthorReviewCard)
        self.assertEqual(card.decision_id, "decision:001")
        self.assertEqual(card.decision_label, "작가 확인 필요")
        self.assertIn("작가 검수", card.explanation)
        self.assertEqual(card.author_question, "이 표현의 핵심이 실제 의미인가요, 관계성이나 톤인가요?")
        self.assertIn("keep", [option["id"] for option in card.options])
        self.assertIn("review", [option["id"] for option in card.options])
        self.assertEqual(card.recommended_option_id, "review")
        self.assertIn("literal translation may miss", card.evidence_summary)
        self.assertIsNone(card.patch_suggestion)
        self.assertEqual(card.priority, decision.priority)
        self.assertEqual(card.status, decision.card_status)
        self.assertEqual(card.target_span, decision.target_span)
        self.assertEqual(card.suggested_actions, decision.suggested_actions)
        self.assertEqual(card.created_from_evidence_ids, decision.evidence_ids)

    def test_author_review_card_generator_skips_non_review_decisions(self) -> None:
        generator = AuthorReviewCardGenerator(self._config())
        decision = self._make_review_decision(
            decision_id="decision:002",
            decision_type="risk_unresolved",
            source_span="internal note",
            meaning_draft_span="meaning baseline",
            vibe_translation_span="translated text",
            reason="internal",
            evidence_ids=["risk:002"],
            author_note="",
            confidence="high",
            needs_author_review=False,
            risk_level="high",
        )

        cards = generator.generate([decision], rag_evidence=[])

        self.assertEqual(cards, [])

    def test_high_confidence_idiom_is_user_visible(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        row = RetrievalResult(
            item={
                "source_id": "idiom_001",
                "matched_phrase": "노는 물",
                "evidence_chunk": "그녀가 노는 물은 이제 대한민국을 넘어 세계로 향하고 있었다.",
                "context_text": "한국어 기준 표현: 노는 물\n일본어 후보: 住む世界 / 活躍の場 / ステージ",
                "embedding_text": "노는 물. 사람의 처지나 활동 무대가 달라지는 상황을 가리키는 표현.",
                "meaning": "사람의 활동 무대나 수준이 달라졌음을 뜻한다.",
            },
            score=0.9,
            similarity_score=0.9,
            anchor_boost=0.0,
            final_score=0.9,
        )

        item = analyzer._risk_from_idiom(row)
        self.assertTrue(item.user_visible)
        self.assertEqual(item.visibility_bucket, "확인 필요")

    def test_low_confidence_terminology_is_hidden(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        item = analyzer._risk_from_term(
            {"source": "구단", "type": "term", "policy": "candidate", "allowedTranslations": []},
            index=1,
        )
        self.assertFalse(item.user_visible)
        self.assertEqual(item.visibility_bucket, "내부 디버그")

    def test_source_span_uses_evidence_not_rag_description(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        row = RetrievalResult(
            item={
                "source_id": "idiom_001",
                "matched_phrase": "노는 물",
                "evidence_chunk": "그녀가 노는 물은 이제 대한민국을 넘어 세계로 향하고 있었다.",
                "context_text": "한국어 기준 표현: 노는 물\n일본어 후보: 住む世界 / 活躍の場 / ステージ",
                "embedding_text": "노는 물. 사람의 처지나 활동 무대가 달라지는 상황을 가리키는 표현.",
            },
            score=0.8,
            similarity_score=0.8,
            anchor_boost=0.0,
            final_score=0.8,
        )
        item = analyzer._risk_from_idiom(row)
        self.assertEqual(item.anchor, "노는 물")
        self.assertEqual(item.source_span, "그녀가 노는 물은 이제 대한민국을 넘어 세계로 향하고 있었다.")

    def test_target_candidates_are_parsed_from_context(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        row = RetrievalResult(
            item={
                "source_id": "idiom_001",
                "matched_phrase": "노는 물",
                "evidence_chunk": "그녀가 노는 물은 이제 대한민국을 넘어 세계로 향하고 있었다.",
                "context_text": "한국어 기준 표현: 노는 물\n일본어 후보: 住む世界 / 活躍の場 / ステージ",
                "embedding_text": "노는 물. 사람의 처지나 활동 무대가 달라지는 상황을 가리키는 표현.",
            },
            score=0.8,
            similarity_score=0.8,
            anchor_boost=0.0,
            final_score=0.8,
        )
        item = analyzer._risk_from_idiom(row)
        self.assertEqual(item.target_candidates, ["住む世界", "活躍の場", "ステージ"])

    def test_literal_hand_grasp_is_hidden_from_user_visible_risk_and_qa(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        row = self._idiom_row(
            source_id="jp-expanded-00111",
            matched_phrase="손에 쥐다",
            evidence_chunk="강현우는 오른손에 쥐인 야구공의 실밥을 쓸어내렸다.",
        )

        item = analyzer._risk_from_idiom(row)
        qa_item = PostTranslationQA().evaluate(
            "강현우는 오른손에 쥐인 야구공의 실밥을 쓸어내렸다.",
            "mock translation",
            [item],
        )[0]
        visible_risks, hidden_risks = split_user_visible_risk_items([item])
        visible_qa, hidden_qa = split_user_visible_qa_report([qa_item])

        self.assertFalse(item.user_visible)
        self.assertEqual(item.visibility_bucket, "내부 디버그")
        self.assertIn("literal physical grasp context: object=야구공", item.filter_reason)
        self.assertIn("physical object holding", item.debug_reason)
        self.assertEqual(qa_item.status, "unchecked")
        self.assertFalse(qa_item.user_visible)
        self.assertIn("literal physical grasp context: object=야구공", qa_item.reason)
        self.assertEqual(visible_risks, [])
        self.assertEqual(len(hidden_risks), 1)
        self.assertEqual(visible_qa["확인 필요"], [])
        self.assertEqual(visible_qa["검토 후보"], [])
        self.assertEqual(len(hidden_qa), 1)


    def test_v2_direct_qa_excludes_internal_debug_from_user_visible_count(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "그는 마운드 위에 섰다."
        translation_text = "カン・ヒョヌはマウンドに立った。"
        safety = TranslationPipeline._locale_adherence_metadata(
            source_text=source_text,
            final_translation=translation_text,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        initial_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=translation_text,
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=safety,
            ),
        )
        qa_item = QAItem(
            risk_item_id="qa-1",
            status="unchecked",
            source_span=source_text,
            translation_evidence=translation_text,
            reason="internal debug note",
            suggested_action="",
            review_bucket="내부 디버그",
            user_message="",
            user_visible=False,
        )
        pipeline.run_direct_only = lambda *args, **kwargs: initial_result  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = lambda source_text: []  # type: ignore[assignment]
        pipeline.post_translation_qa.evaluate = lambda source_text, translation, risk_items: [qa_item]  # type: ignore[assignment]
        pipeline.patch_proposer.propose = lambda translation, risk_items, qa_report: []  # type: ignore[assignment]

        result = pipeline.run_v2_direct_qa(source_text)

        self.assertEqual(result.metadata["user_visible_qa_count"], 0)
        self.assertEqual(result.metadata["hidden_qa_count"], 1)
        self.assertEqual(result.user_visible_qa_report["확인 필요"], [])
        self.assertEqual(result.user_visible_qa_report["검토 후보"], [])
        self.assertEqual(len(result.user_visible_qa_report["내부 디버그"]), 1)

    def test_abstract_victory_hand_grasp_remains_user_visible(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        row = self._idiom_row(
            source_id="jp-expanded-00111",
            matched_phrase="손에 쥐다",
            evidence_chunk="그는 마침내 승리를 손에 쥐었다.",
        )

        item = analyzer._risk_from_idiom(row)
        qa_item = PostTranslationQA().evaluate("그는 마침내 승리를 손에 쥐었다.", "mock translation", [item])[0]

        self.assertTrue(item.user_visible)
        self.assertEqual(item.visibility_bucket, "확인 필요")
        self.assertEqual(item.filter_reason, "")
        self.assertEqual(qa_item.status, "warn")
        self.assertTrue(qa_item.user_visible)

    def test_abstract_opportunity_hand_get_remains_user_visible(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        row = self._idiom_row(
            source_id="jp-expanded-00112",
            matched_phrase="손에 넣다",
            evidence_chunk="그녀는 기회를 손에 넣었다.",
        )

        item = analyzer._risk_from_idiom(row)
        qa_item = PostTranslationQA().evaluate("그녀는 기회를 손에 넣었다.", "mock translation", [item])[0]

        self.assertTrue(item.user_visible)
        self.assertEqual(item.visibility_bucket, "확인 필요")
        self.assertEqual(item.filter_reason, "")
        self.assertEqual(qa_item.status, "warn")
        self.assertTrue(qa_item.user_visible)

    def test_literal_cup_hold_is_hidden(self) -> None:
        analyzer = SourceSideAnalyzer(
            self._config(),
            idiom_retriever=None,  # type: ignore[arg-type]
            annotation_retriever=None,  # type: ignore[arg-type]
        )
        row = self._idiom_row(
            source_id="jp-expanded-00111",
            matched_phrase="손에 쥐다",
            evidence_chunk="그는 손에 쥔 컵을 내려놓았다.",
        )

        item = analyzer._risk_from_idiom(row)
        qa_item = PostTranslationQA().evaluate("그는 손에 쥔 컵을 내려놓았다.", "mock translation", [item])[0]

        self.assertFalse(item.user_visible)
        self.assertEqual(item.visibility_bucket, "내부 디버그")
        self.assertIn("object=컵", item.filter_reason)
        self.assertEqual(qa_item.status, "unchecked")
        self.assertFalse(qa_item.user_visible)

    def test_patch_suggestions_require_concrete_translation_evidence(self) -> None:
        patcher = PatchProposer()
        risk_items = [
            RiskItem(
                id="idiom:1",
                type="idiom",
                source_span="그녀가 노는 물은 달라졌다.",
                anchor="노는 물",
                meaning_ko="활동 무대",
                target_candidates=["住む世界"],
                confidence="high",
                source="rag",
            )
        ]
        qa_report = [
            QAItem(
                risk_item_id="idiom:1",
                status="warn",
                source_span="그녀가 노는 물은 달라졌다.",
                translation_evidence="",
                reason="needs manual confirmation",
                suggested_action="review",
                target_candidates=["住む世界"],
            )
        ]

        suggestions = patcher.propose("translated text", risk_items, qa_report)
        self.assertEqual(suggestions, [])

    def test_service_v2_direct_qa_exposes_user_visible_fields(self) -> None:
        result = translate(
            {
                "sourceText": "그녀가 노는 물이 달라졌다.",
                "targetCountry": "일본",
                "mode": "v2_direct_qa",
            }
        )

        self.assertEqual(result["mode"], "v2_direct_qa")
        self.assertIn("riskItems", result)
        self.assertIn("userVisibleRiskItems", result)
        self.assertIn("userVisibleQaReport", result)
        self.assertIn("hiddenQaReport", result)
        self.assertIsInstance(result["userVisibleRiskItems"], list)
        self.assertIsInstance(result["userVisibleQaReport"], dict)

    def test_service_v2_dual_draft_review_exposes_translation_decisions(self) -> None:
        class StubPipeline:
            def run_v2_dual_draft_review(self, source_text: str) -> V2DualDraftReviewResult:
                return V2DualDraftReviewResult(
                    mode="v2_dual_draft_review",
                    source_text=source_text,
                    final_translation="translated text",
                    meaning_draft=MeaningDraft(text="meaning draft", model="mock-model"),
                    rag_evidence=[],
                    translation_decisions=[],
                    author_review_cards=[],
                    metadata={"stub": True},
                    delivery_status="deliverable",
                    user_visible_error_code=None,
                )

        original_pipeline_for_mode = translation_service_module._pipeline_for_mode
        translation_service_module._pipeline_for_mode = lambda *args, **kwargs: StubPipeline()  # type: ignore[assignment]
        try:
            result = translate(
                {
                    "sourceText": "그는 마을에 산다.",
                    "targetCountry": resolve_country_for_locale("ko_ja"),
                    "mode": "v2_dual_draft_review",
                }
            )
        finally:
            translation_service_module._pipeline_for_mode = original_pipeline_for_mode  # type: ignore[assignment]

        self.assertEqual(result["mode"], "v2_dual_draft_review")
        self.assertIn("translationDecisions", result)
        self.assertIsInstance(result["translationDecisions"], list)
        self.assertIn("authorReviewCards", result)
        self.assertIsInstance(result["authorReviewCards"], list)
        self.assertIn("meaningDraft", result)
        self.assertIn("text", result["meaningDraft"])

    def test_service_direct_only_returns_no_rag_metadata(self) -> None:
        result = translate(
            {
                "sourceText": "그녀가 노는 물이 달라졌다.",
                "targetCountry": "일본",
                "mode": "direct_only",
            }
        )

        self.assertEqual(result["mode"], "direct_only")
        self.assertEqual(result["retrievalCount"], 0)
        self.assertFalse(result["metadata"]["rag_enabled"])
        self.assertFalse(result["metadata"]["review_enabled"])
        self.assertFalse(result["metadata"]["inspection_enabled"])

    def test_evaluation_markdown_contains_exact_required_phrases(self) -> None:
        result = {
            "risk_items": [
                {"anchor": "목청이 터져라", "source_span": "목청이 터져라 외쳤다.", "meaning_ko": ""},
                {"anchor": "다 잡은 고기를 놓치다", "source_span": "다 잡은 고기를 놓치다 같은 기분", "meaning_ko": ""},
                {"anchor": "노는 물", "source_span": "노는 물이 달라졌다.", "meaning_ko": ""},
                {"anchor": "발목을 잡다", "source_span": "발목을 잡는 일", "meaning_ko": ""},
                {"anchor": "손을 놓다", "source_span": "손을 놓지 않았다.", "meaning_ko": ""},
                {"anchor": "벼랑 끝에 몰리다", "source_span": "벼랑 끝에 몰리다", "meaning_ko": ""},
                {"anchor": "눈물 쏙 빼놓다", "source_span": "눈물 쏙 빼놓다", "meaning_ko": ""},
            ],
            "user_visible_risk_items": [],
            "patch_suggestions": [],
            "user_visible_qa_report": {"확인 필요": [], "검토 후보": [], "내부 디버그": []},
            "metadata": {"hidden_risk_item_count": 0},
        }
        markdown = build_evaluation_markdown(
            previous_risk_count=41,
            result=result,
            literal_false_positive=False,
            ui_ready=False,
        )
        for phrase in REQUIRED_EVALUATION_PHRASES:
            self.assertIn(phrase, markdown)

    def test_pipeline_config_quality_mode_profiles_map_expected_models(self) -> None:
        expected = {
            "fast": "gpt-5.4-nano",
            "standard": "gpt-5-mini",
            "quality": "gpt-5.4-mini",
            "baseline": "gpt-4.1-mini",
        }
        self.assertEqual(DEFAULT_QUALITY_MODE, "standard")
        for quality_mode, model_name in expected.items():
            config = PipelineConfig(locale="ko_ja", quality_mode=quality_mode, mock=True)
            self.assertEqual(config.translation_model, model_name)
            self.assertEqual(config.review_model, model_name)
            self.assertEqual(config.model_profile_name, quality_mode)
            self.assertEqual(MODEL_PROFILES[quality_mode]["translation_model"], model_name)

    def test_service_default_quality_mode_is_standard(self) -> None:
        result = translate(
            {
                "sourceText": "그녀가 노는 물이 달라졌다.",
                "targetCountry": "일본",
                "mode": "direct_only",
            }
        )

        self.assertEqual(result["metadata"]["quality_mode"], "standard")
        self.assertEqual(result["metadata"]["model_profile"], "standard")
        self.assertEqual(result["metadata"]["translation_model"], "gpt-5-mini")
        self.assertEqual(result["metadata"]["review_model"], "gpt-5-mini")
        self.assertFalse(result["metadata"]["model_override_used"])

    def test_service_quality_mode_routes_models(self) -> None:
        expectations = {
            "fast": "gpt-5.4-nano",
            "standard": "gpt-5-mini",
            "quality": "gpt-5.4-mini",
            "baseline": "gpt-4.1-mini",
        }
        for quality_mode, model_name in expectations.items():
            result = translate(
                {
                    "sourceText": "그녀가 노는 물이 달라졌다.",
                    "targetCountry": "일본",
                    "mode": "direct_only",
                    "qualityMode": quality_mode,
                }
            )
            self.assertEqual(result["metadata"]["quality_mode"], quality_mode)
            self.assertEqual(result["metadata"]["translation_model"], model_name)
            self.assertEqual(result["metadata"]["review_model"], model_name)

    def test_invalid_model_override_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported model override"):
            translate(
                {
                    "sourceText": "그녀가 노는 물이 달라졌다.",
                    "targetCountry": "일본",
                    "mode": "direct_only",
                    "translationModel": "gpt-unknown",
                }
            )

    def test_direct_only_metadata_includes_actual_model_selection(self) -> None:
        result = translate(
            {
                "sourceText": "그녀가 노는 물이 달라졌다.",
                "targetCountry": "일본",
                "mode": "direct_only",
                "model": "gpt-5.4-mini",
            }
        )

        metadata = result["metadata"]
        self.assertEqual(metadata["translation_model"], "gpt-5.4-mini")
        self.assertEqual(metadata["review_model"], "gpt-5.4-mini")
        self.assertTrue(metadata["model_override_used"])
        self.assertEqual(metadata["mode"], "direct_only")
        self.assertIn("translation_safety", metadata)
        self.assertIn("overall_translation_safety_status", metadata)

    def test_v2_direct_qa_metadata_includes_actual_model_selection(self) -> None:
        result = translate(
            {
                "sourceText": "그녀가 노는 물이 달라졌다.",
                "targetCountry": "일본",
                "mode": "v2_direct_qa",
                "qualityMode": "fast",
            }
        )

        metadata = result["metadata"]
        self.assertEqual(metadata["translation_model"], "gpt-5.4-nano")
        self.assertEqual(metadata["review_model"], "gpt-5.4-nano")
        self.assertEqual(metadata["quality_mode"], "fast")
        self.assertEqual(metadata["mode"], "v2_direct_qa")
        self.assertIn("translation_safety", metadata)
        self.assertIn("overall_translation_safety_status", metadata)

    def test_locale_adherence_metadata_fails_when_korean_source_is_copied(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            locale="ko_ja",
            target_language_name="Japanese",
        )
        self.assertEqual(metadata["locale_adherence_status"], "fail")
        self.assertTrue(metadata["source_copy_suspected"])
        self.assertGreater(metadata["korean_char_ratio"], 0.4)

    def test_locale_adherence_metadata_passes_for_japanese_output(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="彼は右手に握った野球ボールを見下ろしながら、静かに息を吐いた。",
            locale="ko_ja",
            target_language_name="Japanese",
        )
        self.assertEqual(metadata["locale_adherence_status"], "pass")
        self.assertFalse(metadata["source_copy_suspected"])
        self.assertGreater(metadata["japanese_char_ratio"], 0.2)

    def test_locale_adherence_metadata_fails_for_copied_korean_in_english_locale(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            locale="ko_en_us",
            target_language_name="English (US)",
        )
        self.assertEqual(metadata["locale_adherence_status"], "fail")
        self.assertTrue(metadata["source_copy_suspected"])
        self.assertEqual(metadata["target_script_ratio"], 0.0)

    def test_locale_adherence_metadata_passes_for_english_output(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="He looked down at the baseball in his right hand and quietly let out a breath.",
            locale="ko_en_us",
            target_language_name="English (US)",
        )
        self.assertEqual(metadata["locale_adherence_status"], "pass")
        self.assertFalse(metadata["source_copy_suspected"])
        self.assertGreater(metadata["latin_char_ratio"], 0.3)

    def test_locale_adherence_metadata_fails_for_copied_korean_in_chinese_locale(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            locale="ko_zh_cn",
            target_language_name="Simplified Chinese",
        )
        self.assertEqual(metadata["locale_adherence_status"], "fail")
        self.assertTrue(metadata["source_copy_suspected"])
        self.assertEqual(metadata["target_script_ratio"], 0.0)

    def test_locale_adherence_metadata_passes_for_chinese_output(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="他低头看着右手里握着的棒球，静静地吐出一口气。",
            locale="ko_zh_cn",
            target_language_name="Simplified Chinese",
        )
        self.assertEqual(metadata["locale_adherence_status"], "pass")
        self.assertFalse(metadata["source_copy_suspected"])
        self.assertGreater(metadata["han_char_ratio"], 0.3)

    def test_locale_adherence_metadata_fails_for_copied_korean_in_thai_locale(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            locale="ko_th_th",
            target_language_name="Thai",
        )
        self.assertEqual(metadata["locale_adherence_status"], "fail")
        self.assertTrue(metadata["source_copy_suspected"])
        self.assertEqual(metadata["target_script_ratio"], 0.0)

    def test_locale_adherence_metadata_passes_for_thai_output(self) -> None:
        metadata = TranslationPipeline._locale_adherence_metadata(
            source_text="그는 오른손에 쥔 야구공을 내려다보며 조용히 숨을 내쉬었다.",
            final_translation="เขาก้มมองลูกเบสบอลในมือขวา แล้วค่อย ๆ ปล่อยลมหายใจออกมาอย่างเงียบงัน",
            locale="ko_th_th",
            target_language_name="Thai",
        )
        self.assertEqual(metadata["locale_adherence_status"], "pass")
        self.assertFalse(metadata["source_copy_suspected"])
        self.assertGreater(metadata["thai_char_ratio"], 0.3)

    def test_translation_safety_checks_flags_full_source_copy(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다.",
            final_translation="강현우는 마운드 위에 섰다.",
            locale="ko_ja",
            target_language_name="Japanese",
        )

        self.assertEqual(safety["overall_translation_safety_status"], "fail")
        self.assertEqual(safety["source_copy_status"], "fail")
        self.assertTrue(safety["source_copy_suspected"])
        self.assertEqual(safety["translation_safety"]["source_copy"]["status"], "fail")
        self.assertEqual(safety["translation_safety"]["locale_adherence"]["status"], "fail")

    def test_translation_safety_checks_accepts_japanese_transliteration(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다.",
            final_translation="カン・ヒョヌはマウンドに立った。",
            locale="ko_ja",
            target_language_name="Japanese",
        )

        self.assertEqual(safety["overall_translation_safety_status"], "pass")
        self.assertEqual(safety["translation_safety"]["locale_adherence"]["status"], "pass")
        self.assertEqual(safety["translation_safety"]["source_copy"]["status"], "pass")
        self.assertEqual(safety["translation_safety"]["residual_hangul"]["status"], "pass")
        self.assertFalse(safety["source_copy_suspected"])

    def test_translation_safety_checks_marks_proper_noun_hangul_as_warn(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다.",
            final_translation="강현우はマウンドに立った。",
            locale="ko_ja",
            target_language_name="Japanese",
        )

        self.assertEqual(safety["translation_safety"]["source_copy"]["status"], "pass")
        self.assertEqual(safety["translation_safety"]["locale_adherence"]["status"], "pass")
        self.assertEqual(safety["translation_safety"]["residual_hangul"]["status"], "warn")
        self.assertEqual(safety["translation_safety"]["proper_noun_transliteration"]["status"], "warn")
        self.assertEqual(safety["overall_translation_safety_status"], "warn")
        self.assertFalse(safety["source_copy_suspected"])
        self.assertGreater(len(safety["translation_safety"]["proper_noun_transliteration"]["issues"]), 0)


    def test_translation_safety_checks_keeps_long_hangul_proper_noun_out_of_source_copy_fail(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="그는 한국프로야구위원회 앞에서 서울네오타이탄즈 관계자를 만났다.",
            final_translation="彼は 한국프로야구위원회 の前で 서울네오타이탄즈 の関係者に会った。",
            locale="ko_ja",
            target_language_name="Japanese",
        )

        self.assertNotEqual(safety["source_copy_status"], "fail")
        self.assertEqual(safety["translation_safety"]["residual_hangul"]["status"], "warn")
        self.assertIn(safety["translation_safety"]["proper_noun_transliteration"]["status"], {"warn", "unchecked"})
        self.assertEqual(safety["overall_translation_safety_status"], "warn")
        self.assertFalse(safety["source_copy_suspected"])

    def test_translation_safety_checks_fails_for_remaining_korean_sentence(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다. 그는 숨을 골랐다.",
            final_translation="カン・ヒョヌはマウンドに立った。그는 숨을 골랐다.",
            locale="ko_ja",
            target_language_name="Japanese",
        )

        self.assertEqual(safety["translation_safety"]["residual_hangul"]["status"], "fail")
        self.assertEqual(safety["overall_translation_safety_status"], "fail")
        self.assertIn(safety["translation_safety"]["source_copy"]["status"], {"pass", "warn", "fail"})

    def test_translation_safety_checks_passes_for_english_output(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다.",
            final_translation="Kang Hyun-woo stood on the mound.",
            locale="ko_en_us",
            target_language_name="English (US)",
        )

        self.assertEqual(safety["translation_safety"]["locale_adherence"]["status"], "pass")
        self.assertEqual(safety["translation_safety"]["residual_hangul"]["status"], "pass")
        self.assertEqual(safety["overall_translation_safety_status"], "pass")

    def test_translation_safety_checks_passes_for_chinese_output(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다.",
            final_translation="姜贤宇站在投手丘上。",
            locale="ko_zh_cn",
            target_language_name="Simplified Chinese",
        )

        self.assertEqual(safety["translation_safety"]["locale_adherence"]["status"], "pass")
        self.assertEqual(safety["translation_safety"]["residual_hangul"]["status"], "pass")
        self.assertEqual(safety["overall_translation_safety_status"], "pass")

    def test_translation_safety_checks_passes_for_thai_output(self) -> None:
        safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다.",
            final_translation="คังฮยอนอูยืนอยู่บนเนินขว้าง",
            locale="ko_th_th",
            target_language_name="Thai",
        )

        self.assertEqual(safety["translation_safety"]["locale_adherence"]["status"], "pass")
        self.assertEqual(safety["translation_safety"]["residual_hangul"]["status"], "pass")
        self.assertEqual(safety["overall_translation_safety_status"], "pass")

    def test_v2_direct_qa_delivers_without_retry_when_initial_pass(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "강현우는 마운드 위에 섰다."
        initial_translation = "カン・ヒョヌはマウンドに立った。"
        safety = TranslationPipeline._locale_adherence_metadata(
            source_text=source_text,
            final_translation=initial_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        initial_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=initial_translation,
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=safety,
            ),
        )
        pipeline._run_direct_translation_once = lambda *args, **kwargs: initial_result  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = lambda source_text: []  # type: ignore[assignment]
        pipeline.post_translation_qa.evaluate = lambda source_text, translation, risk_items: []  # type: ignore[assignment]
        pipeline.patch_proposer.propose = lambda translation, risk_items, qa_report: []  # type: ignore[assignment]

        result = pipeline.run_v2_direct_qa(source_text)

        self.assertFalse(result.metadata["translation_safety_retry_attempted"])
        self.assertEqual(result.metadata["translation_safety_retry_count"], 0)
        self.assertEqual(result.metadata["delivery_status"], "deliverable")
        self.assertIsNone(result.metadata["retry_success"])
        self.assertFalse(result.metadata["user_visible_error_code"])
        self.assertEqual(result.final_translation, initial_translation)

    def test_v2_direct_qa_retries_on_source_copy_fail_and_succeeds(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "강현우는 마운드 위에 섰다."
        initial_translation = source_text
        retry_translation = "カン・ヒョヌはマウンドに立った。"
        initial_safety = TranslationPipeline._locale_adherence_metadata(
            source_text=source_text,
            final_translation=initial_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        retry_safety = TranslationPipeline._locale_adherence_metadata(
            source_text=source_text,
            final_translation=retry_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        initial_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=initial_translation,
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=initial_safety,
            ),
        )
        retry_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=retry_translation,
            draft={"prompt_debug": {"prompt_hash": "retry-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=retry_safety,
            ),
        )
        calls = iter([initial_result, retry_result])
        pipeline._run_direct_translation_once = lambda *args, **kwargs: next(calls)  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = lambda source_text: []  # type: ignore[assignment]
        pipeline.post_translation_qa.evaluate = lambda source_text, translation, risk_items: []  # type: ignore[assignment]
        pipeline.patch_proposer.propose = lambda translation, risk_items, qa_report: []  # type: ignore[assignment]

        result = pipeline.run_v2_direct_qa(source_text)

        self.assertTrue(result.metadata["translation_safety_retry_attempted"])
        self.assertEqual(result.metadata["translation_safety_retry_count"], 1)
        self.assertEqual(result.metadata["delivery_status"], "deliverable")
        self.assertIsNone(result.metadata["user_visible_error_code"])
        self.assertTrue(result.metadata["retry_success"])
        self.assertEqual(result.final_translation, retry_translation)
        self.assertEqual(result.metadata["initial_source_copy_status"], "fail")
        self.assertEqual(result.metadata["final_source_copy_status"], "pass")
        self.assertEqual(result.metadata["retry_translation_model"], result.metadata["translation_model"])
        self.assertTrue(result.metadata["retry_prompt_hash"])

    def test_v2_direct_qa_retries_on_locale_fail_and_succeeds(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "강현우는 마운드 위에 섰다."
        initial_translation = "Hello."
        retry_translation = "カン・ヒョヌはマウンドに立った。"
        initial_safety = TranslationPipeline._locale_adherence_metadata(
            source_text=source_text,
            final_translation=initial_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        retry_safety = TranslationPipeline._locale_adherence_metadata(
            source_text=source_text,
            final_translation=retry_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        initial_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=initial_translation,
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=initial_safety,
            ),
        )
        retry_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=retry_translation,
            draft={"prompt_debug": {"prompt_hash": "retry-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=retry_safety,
            ),
        )
        calls = iter([initial_result, retry_result])
        pipeline._run_direct_translation_once = lambda *args, **kwargs: next(calls)  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = lambda source_text: []  # type: ignore[assignment]
        pipeline.post_translation_qa.evaluate = lambda source_text, translation, risk_items: []  # type: ignore[assignment]
        pipeline.patch_proposer.propose = lambda translation, risk_items, qa_report: []  # type: ignore[assignment]

        result = pipeline.run_v2_direct_qa(source_text)

        self.assertTrue(result.metadata["translation_safety_retry_attempted"])
        self.assertEqual(result.metadata["translation_safety_retry_count"], 1)
        self.assertEqual(result.metadata["delivery_status"], "deliverable")
        self.assertFalse(result.metadata["user_visible_error_code"])
        self.assertTrue(result.metadata["retry_success"])
        self.assertEqual(result.final_translation, retry_translation)
        self.assertEqual(result.metadata["initial_locale_adherence_status"], "fail")
        self.assertEqual(result.metadata["final_locale_adherence_status"], "pass")

    def test_v2_direct_qa_blocks_when_retry_still_fails(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "강현우는 마운드 위에 섰다."
        fail_translation = source_text
        fail_safety = TranslationPipeline._locale_adherence_metadata(
            source_text=source_text,
            final_translation=fail_translation,
            locale="ko_ja",
            target_language_name="Japanese",
        )
        initial_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=fail_translation,
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=fail_safety,
            ),
        )
        retry_result = DirectTranslationResult(
            mode="direct_only",
            final_translation=fail_translation,
            draft={"prompt_debug": {"prompt_hash": "retry-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=fail_safety,
            ),
        )
        calls = iter([initial_result, retry_result])
        pipeline._run_direct_translation_once = lambda *args, **kwargs: next(calls)  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = lambda source_text: []  # type: ignore[assignment]
        pipeline.post_translation_qa.evaluate = lambda source_text, translation, risk_items: []  # type: ignore[assignment]
        pipeline.patch_proposer.propose = lambda translation, risk_items, qa_report: []  # type: ignore[assignment]

        result = pipeline.run_v2_direct_qa(source_text)

        self.assertTrue(result.metadata["translation_safety_retry_attempted"])
        self.assertEqual(result.metadata["translation_safety_retry_count"], 1)
        self.assertEqual(result.metadata["delivery_status"], "blocked_translation_safety")
        self.assertEqual(result.metadata["user_visible_error_code"], "translation_safety_failed")
        self.assertFalse(result.metadata["retry_success"])

    def test_v2_direct_qa_does_not_retry_for_residual_hangul_warn(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "강현우는 마운드 위에 섰다."
        warn_translation = "カン・ヒョヌはマウンドに立った。"
        warn_safety = TranslationPipeline._translation_safety_checks(
            source_text=source_text,
            final_translation="강현우はマウンドに立った。",
            locale="ko_ja",
            target_language_name="Japanese",
        )
        result_item = DirectTranslationResult(
            mode="direct_only",
            final_translation=warn_translation,
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=warn_safety,
            ),
        )
        pipeline._run_direct_translation_once = lambda *args, **kwargs: result_item  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = lambda source_text: []  # type: ignore[assignment]
        pipeline.post_translation_qa.evaluate = lambda source_text, translation, risk_items: []  # type: ignore[assignment]
        pipeline.patch_proposer.propose = lambda translation, risk_items, qa_report: []  # type: ignore[assignment]

        result = pipeline.run_v2_direct_qa(source_text)

        self.assertFalse(result.metadata["translation_safety_retry_attempted"])
        self.assertEqual(result.metadata["translation_safety_retry_count"], 0)
        self.assertEqual(result.metadata["delivery_status"], "deliverable")
        self.assertIsNone(result.metadata["retry_success"])
        self.assertFalse(result.metadata["user_visible_error_code"])

    def test_v2_direct_qa_does_not_retry_for_proper_noun_warn(self) -> None:
        pipeline = TranslationPipeline(self._config())
        source_text = "강현우는 마운드 위에 섰다."
        warn_translation = "강현우はマウンドに立った。"
        warn_safety = TranslationPipeline._translation_safety_checks(
            source_text="강현우는 마운드 위에 섰다.",
            final_translation="강현우はマウンドに立った。",
            locale="ko_ja",
            target_language_name="Japanese",
        )
        result_item = DirectTranslationResult(
            mode="direct_only",
            final_translation="강현우はマウンドに立った。",
            draft={"prompt_debug": {"prompt_hash": "initial-hash"}},
            metadata=pipeline._metadata(
                source_side_rag_enabled=False,
                rag_enabled=False,
                terminology_enabled=False,
                glossary_enabled=False,
                review_enabled=False,
                inspection_enabled=False,
                extra=warn_safety,
            ),
        )
        pipeline._run_direct_translation_once = lambda *args, **kwargs: result_item  # type: ignore[assignment]
        pipeline.source_side_analyzer.analyze = lambda source_text: []  # type: ignore[assignment]
        pipeline.post_translation_qa.evaluate = lambda source_text, translation, risk_items: []  # type: ignore[assignment]
        pipeline.patch_proposer.propose = lambda translation, risk_items, qa_report: []  # type: ignore[assignment]

        result = pipeline.run_v2_direct_qa(source_text)

        self.assertFalse(result.metadata["translation_safety_retry_attempted"])
        self.assertEqual(result.metadata["translation_safety_retry_count"], 0)
        self.assertEqual(result.metadata["delivery_status"], "deliverable")
        self.assertIsNone(result.metadata["retry_success"])
        self.assertFalse(result.metadata["user_visible_error_code"])

    def test_translation_service_blocks_translation_safety_failures(self) -> None:
        from backend.services import translation_service as svc

        class FakePipeline:
            def run_v2_direct_qa(self, source_text: str) -> V2TranslationResult:
                return V2TranslationResult(
                    mode="v2_direct_qa",
                    final_translation=source_text,
                    risk_items=[],
                    qa_report=[],
                    user_visible_risk_items=[],
                    hidden_risk_items=[],
                    user_visible_qa_report={},
                    hidden_qa_report=[],
                    patch_suggestions=[],
                    metadata={"delivery_status": "blocked_translation_safety"},
                    draft={"prompt_debug": {"prompt_hash": "blocked-hash"}},
                    delivery_status="blocked_translation_safety",
                    user_visible_error_code="translation_safety_failed",
                )

        original = svc._pipeline_for_mode
        svc._pipeline_for_mode = lambda *args, **kwargs: FakePipeline()  # type: ignore[assignment]
        self.addCleanup(setattr, svc, "_pipeline_for_mode", original)

        result = translate(
            {
                "sourceText": "강현우는 마운드 위에 섰다.",
                "targetCountry": "일본",
                "mode": "v2_direct_qa",
            }
        )

        self.assertEqual(result["deliveryStatus"], "blocked_translation_safety")
        self.assertEqual(result["userVisibleErrorCode"], "translation_safety_failed")
        self.assertEqual(result["message"], "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요.")
        self.assertEqual(result["finalTranslation"], "")



    def test_translation_service_blocks_direct_only_translation_safety_failures(self) -> None:
        from backend.services import translation_service as svc

        class FakePipeline:
            def run_direct_only(self, source_text: str) -> DirectTranslationResult:
                return DirectTranslationResult(
                    mode="direct_only",
                    final_translation=source_text,
                    draft={"prompt_debug": {"prompt_hash": "blocked-hash"}},
                    metadata={"delivery_status": "blocked_translation_safety"},
                    delivery_status="blocked_translation_safety",
                    user_visible_error_code="translation_safety_failed",
                )

        original = svc._pipeline_for_mode
        svc._pipeline_for_mode = lambda *args, **kwargs: FakePipeline()  # type: ignore[assignment]
        self.addCleanup(setattr, svc, "_pipeline_for_mode", original)

        result = translate(
            {
                "sourceText": "그는 마운드 위에 섰다.",
                "targetCountry": "일본",
                "mode": "direct_only",
            }
        )

        self.assertEqual(result["deliveryStatus"], "blocked_translation_safety")
        self.assertEqual(result["userVisibleErrorCode"], "translation_safety_failed")
        self.assertEqual(result["message"], "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요.")
        self.assertEqual(result["finalTranslation"], "")

    def test_translation_service_normalizes_empty_deliverable_to_blocked(self) -> None:
        from backend.services import translation_service as svc

        class FakePipeline:
            def run_direct_only(self, source_text: str) -> DirectTranslationResult:
                return DirectTranslationResult(
                    mode="direct_only",
                    final_translation="",
                    draft={"prompt_debug": {"prompt_hash": "empty-deliverable-hash"}},
                    metadata={"delivery_status": "deliverable"},
                    delivery_status="deliverable",
                    user_visible_error_code=None,
                )

        original = svc._pipeline_for_mode
        svc._pipeline_for_mode = lambda *args, **kwargs: FakePipeline()  # type: ignore[assignment]
        self.addCleanup(setattr, svc, "_pipeline_for_mode", original)

        result = translate(
            {
                "sourceText": "그는 마운드에 섰다.",
                "targetCountry": "일본",
                "mode": "direct_only",
            }
        )

        self.assertEqual(result["deliveryStatus"], "blocked_translation_safety")
        self.assertEqual(result["userVisibleErrorCode"], "translation_safety_failed")
        self.assertEqual(result["finalTranslation"], "")
        self.assertEqual(result["message"], "대상 언어 번역 검증에 실패했습니다. 다시 시도해 주세요.")
        self.assertEqual(result["metadata"]["delivery_status"], "blocked_translation_safety")
        self.assertEqual(result["metadata"]["user_visible_error_code"], "translation_safety_failed")

    def test_translation_service_preserves_deliverable_success(self) -> None:
        from backend.services import translation_service as svc

        class FakePipeline:
            def run_direct_only(self, source_text: str) -> DirectTranslationResult:
                return DirectTranslationResult(
                    mode="direct_only",
                    final_translation="カン・ヒョヌはマウンドに立った。",
                    draft={"prompt_debug": {"prompt_hash": "deliverable-hash"}},
                    metadata={"delivery_status": "deliverable"},
                    delivery_status="deliverable",
                    user_visible_error_code=None,
                )

        original = svc._pipeline_for_mode
        svc._pipeline_for_mode = lambda *args, **kwargs: FakePipeline()  # type: ignore[assignment]
        self.addCleanup(setattr, svc, "_pipeline_for_mode", original)

        result = translate(
            {
                "sourceText": "강현우는 마운드에 섰다.",
                "targetCountry": "일본",
                "mode": "direct_only",
            }
        )

        self.assertEqual(result["deliveryStatus"], "deliverable")
        self.assertIsNone(result["userVisibleErrorCode"])
        self.assertNotEqual(result["finalTranslation"], "")
        self.assertEqual(result["message"], "")
        self.assertEqual(result["metadata"]["delivery_status"], "deliverable")

if __name__ == "__main__":
    unittest.main()
