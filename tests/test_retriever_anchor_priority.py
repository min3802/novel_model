from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.translation import TranslationPipeline, PipelineConfig
from app.translation.infra.locales import LOCALE_REGISTRY
from app.translation.retrieval.retriever import IdiomRetriever, MockEmbeddingBackend, RetrievalResult, build_search_text, create_embedding_backend
from app.translation.retrieval.idiom_retriever import build_anchor_index, extract_anchor_phrases, normalize_anchor_key


class IdiomRetrieverAnchorPriorityTests(unittest.TestCase):
    def test_search_text_uses_anchor_first_fields_only(self) -> None:
        item = {
            "id": "jp-00001",
            "expression": "sample-expression",
            "meaning": "sample-meaning",
            "usage": "sample-usage",
            "caution": "sample-caution",
            "translation_strategy": "idiom",
            "ko_anchor_expression": ["easy peasy", "two birds one stone"],
            "ko_expression": ["easy peasy", "double win"],
            "scene": ["office"],
            "tone": ["positive"],
        }

        search_text = build_search_text(item)

        self.assertIn("ko_anchor_expression: easy peasy | two birds one stone", search_text)
        self.assertIn("ko_expression: easy peasy | double win", search_text)
        self.assertNotIn("meaning:", search_text)
        self.assertNotIn("usage:", search_text)
        self.assertNotIn("caution:", search_text)
        self.assertNotIn("scene:", search_text)
        self.assertNotIn("tone:", search_text)

    def test_search_text_prefers_kure_ready_embedding_text(self) -> None:
        item = {
            "id": "US_000002",
            "embedding_text": "이렇게 하면 끝, 그거면 됐지, 식은 죽 먹기. 어렵지 않게 끝난다.",
            "context_text": "원문 표현: Bob's your uncle\n한국어 기준 표현: 이렇게 하면 끝",
            "ko_anchor_expression": ["legacy anchor should not be used"],
            "meaning": "legacy meaning should not be used",
        }

        self.assertEqual(build_search_text(item), item["embedding_text"])

    def test_find_anchor_matches_detects_exact_phrase(self) -> None:
        retriever = self._build_retriever(
            [
                {
                    "id": "jp-00112",
                    "embedding_text": "발목을 잡다, 발목을 붙잡다. 남의 일을 방해하거나 발목을 잡아 진도를 높이게 함",
                    "context_text": "원문 표현: 足を引っ張る\n한국어 기준 표현: 발목을 잡다, 발목을 붙잡다",
                }
            ],
            score_threshold=0.0,
        )

        chunk = "이런 초라한 모습으로 그녀의 발목을 잡다라는 표현을 사용했다."
        results = retriever.find_anchor_matches(chunk)

        self.assertTrue(any(row["anchor"] == "발목을 잡다" for row in results))
        row = next(row for row in results if row["anchor"] == "발목을 잡다")
        self.assertEqual(row["source_id"], "jp-00112")
        self.assertEqual(row["match_type"], "exact")
        self.assertEqual(row["evidence_chunk"], chunk)
        self.assertEqual(row["score"], 1.0)

    def test_find_anchor_matches_detects_normalized_ending(self) -> None:
        retriever = self._build_retriever(
            [
                {
                    "id": "jp-00112",
                    "embedding_text": "발목을 잡다, 발목을 붙잡다. 남의 일을 방해하거나 발목을 잡아 진도를 높이게 함",
                    "context_text": "원문 표현: 足を引っ張る\n한국어 기준 표현: 발목을 잡다, 발목을 붙잡다",
                }
            ],
            score_threshold=0.0,
        )

        chunk = "이런 초라한 모습으로 그녀의 발목을 잡고 있는 것은 아닌가 하는 생각이 하루에도 수십 번씩 머릿속을 매드렸다."
        results = retriever.find_anchor_matches(chunk)

        row = next(row for row in results if row["anchor"] == "발목을 잡다")
        self.assertEqual(row["source_id"], "jp-00112")
        self.assertIn(row["match_type"], {"normalized", "exact", "partial"})
        self.assertEqual(row["evidence_chunk"], chunk)
        self.assertEqual(row["score"], 0.95)

    def test_find_anchor_matches_detects_particle_drop_partial(self) -> None:
        retriever = self._build_retriever(
            [
                {
                    "id": "jp-00113",
                    "embedding_text": "손을 놓다, 손을 뗀다. 관계나 일을 포기하거나 그만두다",
                    "context_text": "원문 표현: x\n한국어 기준 표현: 손을 놓다, 손을 뗀다",
                }
            ],
            score_threshold=0.0,
        )

        chunk = "하지만 연주는 너무도 착하고 올곧한 사람이어서, 결코 먼저 손 놓지 않을 터였다."
        results = retriever.find_anchor_matches(chunk)

        row = next(row for row in results if row["anchor"] == "손을 놓다")
        self.assertEqual(row["source_id"], "jp-00113")
        self.assertEqual(row["match_type"], "partial")
        self.assertEqual(row["evidence_chunk"], chunk)
        self.assertEqual(row["score"], 0.9)
        self.assertEqual(row["confidence"], "low")

    def test_find_anchor_matches_rejects_semantic_neighbor_only(self) -> None:
        retriever = self._build_retriever(
            [
                {
                    "id": "jp-00999",
                    "embedding_text": "어겸이 가벼운다. 심리적으로 가벼운 상태",
                    "context_text": "원문 표현: x\n한국어 기준 표현: 어깨가 가볍다",
                }
            ],
            score_threshold=0.0,
        )

        chunk = "오늘 공 던지는 거 보니까 어겸 좀 무겁고 보이던데, 괜찮아?"
        results = retriever.find_anchor_matches(chunk)

        self.assertEqual(results, [])

    def test_extract_anchor_phrases_uses_embedding_text_prefix(self) -> None:
        payload = {
            "id": "jp-00112",
            "embedding_text": "발목을 잡다, 발목을 붙잡다. 남의 일을 방해하거나 발목을 잡아 진도를 늦추게 함",
            "context_text": "원문 표현: 足を引っ張る\n한국어 기준 표현: 발목을 잡다, 발목을 붙잡다",
        }

        self.assertEqual(extract_anchor_phrases(payload), ["발목을 잡다", "발목을 붙잡다"])

    def test_extract_anchor_phrases_supports_context_text_field(self) -> None:
        payload = {
            "id": "jp-00200",
            "embedding_text": "무관한 설명. 추가 설명",
            "context_text": "원문 표현: x\n한국어 기준 표현: 손에 땀을 쥐다, 속이 좁다",
        }

        self.assertEqual(extract_anchor_phrases(payload), ["손에 땀을 쥐다", "속이 좁다"])

    def test_extract_anchor_phrases_drops_short_and_explanatory_text(self) -> None:
        payload = {
            "id": "jp-00201",
            "embedding_text": "가, 나. 남의 일을 방해하거나 발목을 잡아 진도를 늦추게 함",
            "context_text": "한국어 기준 표현: 손, 손을, 손을 놓다",
        }

        self.assertEqual(extract_anchor_phrases(payload), ["손을 놓다"])

    def test_build_anchor_index_deduplicates_by_source_and_anchor(self) -> None:
        items = [
            {
                "id": "jp-00112",
                "embedding_text": "발목을 잡다, 발목을 붙잡다. 남의 일을 방해하거나 발목을 잡아 진도를 늦추게 함",
                "context_text": "한국어 기준 표현: 발목을 잡다, 발목을 붙잡다",
            },
            {
                "id": "jp-00112",
                "embedding_text": "발목을 잡다. 중복된 원본",
                "context_text": "한국어 기준 표현: 발목을 잡다",
            },
            {
                "source_id": "custom-001",
                "embedding_text": "손에 땀을 쥐다. 몹시 긴장되고 아슬아슬하다",
                "context_text": "한국어 기준 표현: 손에 땀을 쥐다",
            },
        ]

        anchor_index = build_anchor_index(items)

        self.assertIn("발목을 잡다", anchor_index)
        self.assertIn("발목을 붙잡다", anchor_index)
        self.assertIn("손에 땀을 쥐다", anchor_index)
        self.assertEqual(len(anchor_index["발목을 잡다"]), 1)
        self.assertEqual(anchor_index["발목을 잡다"][0]["source_id"], "jp-00112")
        self.assertEqual(anchor_index["손에 땀을 쥐다"][0]["source_id"], "custom-001")

    def test_manual_ko_ja_augmentation_entries_are_loaded_through_retrieve(self) -> None:
        retriever = self._build_retriever(
            [
                {
                    "id": "base-placeholder",
                    "source_id": "base-placeholder",
                    "embedding_text": "기본 더미 문장. 보강 데이터와 충돌하지 않는 자리표시자.",
                    "context_text": "한국어 기준 표현: 기본 더미 문장",
                }
            ],
            locale="ko_ja",
            score_threshold=0.0,
        )

        source_ids = {item.get("source_id") for item in retriever.items}
        self.assertEqual(len(source_ids), len(retriever.items))
        self.assertIn("manual-ko-ja-idiom-001", source_ids)
        self.assertIn("manual-ko-ja-idiom-002", source_ids)
        self.assertIn("manual-ko-ja-idiom-003", source_ids)
        self.assertIn("manual-ko-ja-idiom-004", source_ids)
        self.assertIn("manual-ko-ja-idiom-005", source_ids)
        self.assertIn("목청이 터져라", retriever.anchor_index)

        cases = [
            (
                "다 잡은 고기를 놓친 허탈함",
                "manual-ko-ja-idiom-001",
                "다 잡은 고기를 놓치다",
                "normalized",
                "high",
            ),
            (
                "그녀가 노는 물은 이제 대한민국을 넘어 세계로 향하고 있었다",
                "manual-ko-ja-idiom-002",
                "노는 물",
                {"exact", "normalized"},
                "high",
            ),
            (
                "벼랑 끝에 몰린 인간",
                "manual-ko-ja-idiom-003",
                "벼랑 끝에 몰리다",
                "normalized",
                "high",
            ),
            (
                "눈물 쏙 빼놓으십쇼",
                "manual-ko-ja-idiom-004",
                "눈물 쏙 빼놓다",
                "normalized",
                "high",
            ),
            (
                "목청이 터져라 따라 부르며",
                "manual-ko-ja-idiom-005",
                "목청이 터져라",
                "exact",
                "high",
            ),
        ]

        for query, expected_source_id, expected_anchor, match_types, expected_confidence in cases:
            with self.subTest(query=query):
                results = retriever.retrieve(query, top_k=5, return_k=5)
                candidate = next((row for row in results if row.item.get("source_id") == expected_source_id), None)
                self.assertIsNotNone(candidate, msg=f"missing {expected_source_id} for {query}")
                assert candidate is not None
                self.assertEqual(candidate.item.get("anchor"), expected_anchor)
                if isinstance(match_types, set):
                    self.assertIn(candidate.item.get("match_type"), match_types)
                else:
                    self.assertEqual(candidate.item.get("match_type"), match_types)
                self.assertEqual(candidate.item.get("confidence"), expected_confidence)

    def test_normalize_anchor_key_collapses_spacing_and_punctuation(self) -> None:
        self.assertEqual(normalize_anchor_key("발목을 잡다"), normalize_anchor_key("발목을  잡다"))
        self.assertEqual(normalize_anchor_key("손에 땀을 쥐다"), normalize_anchor_key("손에 땀을 쥐다."))

    def _build_retriever(
        self,
        items: list[dict],
        locale: str = "en_us",
        score_threshold: float = 0.0,
    ) -> IdiomRetriever:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        dataset_path = base / "dataset.json"
        dataset_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        config = PipelineConfig(
            locale=locale,
            rag_dataset_path=dataset_path,
            mock=True,
            score_threshold=score_threshold,
            embedding_cache_dir=base / "cache",
        )
        return IdiomRetriever(config)

    def test_exact_anchor_match_outranks_description_only_neighbors(self) -> None:
        items = [
            {
                "id": "jp-00001",
                "expression": "sample-1",
                "meaning": "getting two benefits from one action",
                "usage": "when one move gives two gains",
                "caution": "prefer natural idioms",
                "translation_strategy": "idiom",
                "ko_anchor_expression": ["two birds one stone"],
                "ko_expression": ["two birds one stone", "double win"],
                "scene": ["office"],
                "tone": ["positive"],
            },
            {
                "id": "jp-00160",
                "expression": "sample-2",
                "meaning": "being overly proud after success",
                "usage": "after success confidence becomes excessive",
                "caution": "translate as paraphrase",
                "translation_strategy": "paraphrase",
                "ko_anchor_expression": [],
                "ko_expression": ["arrogant", "full of oneself", "head in the clouds"],
                "scene": ["after success"],
                "tone": ["spoken"],
            },
            {
                "id": "jp-00132",
                "expression": "sample-3",
                "meaning": "suffering bad results from your own actions",
                "usage": "when someone causes their own problem",
                "caution": "idiomatic match is safer",
                "translation_strategy": "paraphrase",
                "ko_anchor_expression": ["you asked for it"],
                "ko_expression": ["you asked for it", "self-inflicted"],
                "scene": ["consequences"],
                "tone": ["spoken"],
            },
        ]
        retriever = self._build_retriever(items)

        results = retriever.retrieve("this is two birds one stone", top_k=3)
        boosted = IdiomRetriever._lexical_match_boost(items[0], "this is two birds one stone")

        self.assertGreater(boosted, 0.0)
        self.assertTrue(any(row.item["id"] == "jp-00001" for row in results))
        self.assertAlmostEqual(
            results[0].final_score,
            results[0].similarity_score + results[0].anchor_boost,
            places=6,
        )

    def test_items_without_anchor_fall_back_to_ko_expression_search(self) -> None:
        retriever = self._build_retriever(
            [
                {
                    "id": "jp-00160",
                    "expression": "sample-2",
                    "meaning": "being overly proud after success",
                    "usage": "after success confidence becomes excessive",
                    "caution": "translate as paraphrase",
                    "translation_strategy": "paraphrase",
                    "ko_anchor_expression": [],
                    "ko_expression": ["arrogant", "full of oneself", "head in the clouds"],
                    "scene": ["after success"],
                    "tone": ["spoken"],
                }
            ]
        )

        results = retriever.retrieve("he is so full of oneself", top_k=1)

        self.assertEqual(results[0].item["id"], "jp-00160")
        self.assertGreaterEqual(results[0].final_score, results[0].similarity_score)

    def test_pipeline_serializes_decomposed_scores(self) -> None:
        item = {
            "id": "jp-00001",
            "expression": "sample-1",
            "meaning": "getting two benefits from one action",
            "usage": "when one move gives two gains",
            "caution": "prefer natural idioms",
            "translation_strategy": "idiom",
            "ko_anchor_expression": ["two birds one stone"],
            "ko_expression": ["two birds one stone", "double win"],
            "scene": ["office"],
            "tone": ["positive"],
        }
        retriever = self._build_retriever([item], locale="ko_en_us")
        pipeline = TranslationPipeline(retriever.config)

        source = "이건 두 마리 토끼를 잡는 격이야."
        result = pipeline.run_with_inspection(source)
        row = result.retrievals[0]

        self.assertIn("similarity_score", row)
        self.assertIn("anchor_boost", row)
        self.assertIn("final_score", row)
        self.assertAlmostEqual(row["final_score"], row["similarity_score"] + row["anchor_boost"], places=6)
        self.assertEqual(result.reviewed_translation, f"[MOCK English (US)] {source}")

    def test_retrieve_returns_empty_when_all_scores_below_threshold(self) -> None:
        items = [
            {
                "id": "jp-00001",
                "expression": "sample-1",
                "meaning": "getting two benefits from one action",
                "usage": "when one move gives two gains",
                "caution": "prefer natural idioms",
                "translation_strategy": "idiom",
                "ko_anchor_expression": ["two birds one stone"],
                "ko_expression": ["two birds one stone", "double win"],
                "scene": ["office"],
                "tone": ["positive"],
            }
        ]
        retriever = self._build_retriever(items, score_threshold=999.0)
        results = retriever.retrieve("two birds one stone", top_k=3)
        self.assertEqual(results, [])

    def test_retrieve_respects_threshold_zero_returns_all(self) -> None:
        items = [
            {
                "id": "jp-00001",
                "expression": "sample-1",
                "meaning": "getting two benefits from one action",
                "usage": "when one move gives two gains",
                "caution": "prefer natural idioms",
                "translation_strategy": "idiom",
                "ko_anchor_expression": ["two birds one stone"],
                "ko_expression": ["two birds one stone", "double win"],
                "scene": ["office"],
                "tone": ["positive"],
            }
        ]
        retriever = self._build_retriever(items, score_threshold=0.0)
        results = retriever.retrieve("completely unrelated query xyz", top_k=1)
        self.assertEqual(len(results), 1)

    def test_locale_registry_includes_new_country_variants(self) -> None:
        self.assertTrue({"ko_ja", "ko_en_us", "ko_zh_cn", "ko_th_th"}.issubset(LOCALE_REGISTRY))

    def test_locale_registry_points_to_kure_ready_embedding_datasets(self) -> None:
        expected_names = {
            "ko_ja": "jp_idiom_embedding_anchor_meaning.json",
            "ko_en_us": "us_idiom_embedding_anchor_meaning.json",
            "ko_zh_cn": "cn_idiom_embedding_anchor_meaning.json",
            "ko_th_th": "th_idiom_embedding_anchor_meaning.json",
        }

        for locale, expected_name in expected_names.items():
            with self.subTest(locale=locale):
                path = LOCALE_REGISTRY[locale].rag_dataset_path
                self.assertEqual(path.name, expected_name)
                self.assertTrue(path.exists())

    def test_kure_defaults_match_embedding_model_summary(self) -> None:
        ja = PipelineConfig(locale="ko_ja", mock=True)
        us = PipelineConfig(locale="ko_en_us", mock=True)
        cn = PipelineConfig(locale="ko_zh_cn", mock=True)
        th = PipelineConfig(locale="ko_th_th", mock=True)

        self.assertEqual(ja.embedding_model, "nlpai-lab/KURE-v1")
        self.assertEqual(ja.idiom_top_k, 3)
        self.assertEqual(ja.annotation_top_k, 2)
        self.assertEqual(ja.annotation_score_threshold, 0.6)
        self.assertEqual(ja.score_threshold, 0.6)
        self.assertEqual(us.score_threshold, 0.6)
        self.assertEqual(cn.score_threshold, 0.6)
        self.assertEqual(th.score_threshold, 0.6)

    def test_mock_config_keeps_tests_from_downloading_kure_model(self) -> None:
        backend = create_embedding_backend(PipelineConfig(locale="ko_en_us", mock=True))

        self.assertIsInstance(backend, MockEmbeddingBackend)

    def test_kure_ready_context_is_rendered_from_context_text(self) -> None:
        # qdrant payload is flat (country/language are top-level, source_id used).
        item = {
            "source_id": "US_000002",
            "embedding_text": "easy way out, done and dusted, piece of cake",
            "context_text": "source phrase: Bob's your uncle\nanchor explanation: easy way out",
            "country": "US",
            "language": "en",
        }
        retriever = self._build_retriever([item], locale="ko_en_us", score_threshold=0.0)
        result = retriever.retrieve("easy way out", top_k=1)[0]

        self.assertEqual(result.item["source_id"], "US_000002")
        self.assertIn(result.item["match_type"], {"exact", "normalized", "partial", "semantic"})
        self.assertIn(result.item["lexical_evidence"], {True, False})
        context = IdiomRetriever.build_context([result])
        self.assertIn("source_id: US_000002", context)
        self.assertIn("anchor:", context)
        self.assertIn("matched_phrase:", context)
        self.assertIn("match_type:", context)
        self.assertIn("confidence:", context)
        self.assertIn("evidence_chunk:", context)
        self.assertIn("description:", context)
        self.assertIn("source phrase: Bob's your uncle", context)

    def test_build_context_keeps_only_lexical_high_when_semantic_low_is_present(self) -> None:
        lexical = RetrievalResult(
            item={
                "source_id": "jp-00112",
                "anchor": "easy way out",
                "matched_phrase": "easy way out",
                "match_type": "normalized",
                "confidence": "high",
                "lexical_evidence": True,
                "evidence_chunk": "this line is lexical high",
                "context_text": "source phrase: Bob's your uncle",
                "embedding_text": "easy way out",
            },
            score=1.0,
            similarity_score=0.0,
            anchor_boost=1.0,
            final_score=1.0,
        )
        semantic = RetrievalResult(
            item={
                "source_id": "jp-00999",
                "anchor": "",
                "matched_phrase": "",
                "match_type": "semantic",
                "confidence": "low",
                "lexical_evidence": False,
                "evidence_chunk": "semantic only evidence",
                "context_text": "semantic only",
                "embedding_text": "semantic only",
            },
            score=0.2,
            similarity_score=0.2,
            anchor_boost=0.0,
            final_score=0.2,
        )

        context = IdiomRetriever.build_context([lexical, semantic])

        self.assertIn("source_id: jp-00112", context)
        self.assertIn("match_type: normalized", context)
        self.assertIn("confidence: high", context)
        self.assertNotIn("jp-00999", context)
        self.assertNotIn("confidence: low", context)
        self.assertNotIn("semantic only", context)

    def test_build_context_returns_no_high_confidence_message_for_semantic_only_low_results(self) -> None:
        semantic = RetrievalResult(
            item={
                "source_id": "jp-00999",
                "anchor": "",
                "matched_phrase": "",
                "match_type": "semantic",
                "confidence": "low",
                "lexical_evidence": False,
                "evidence_chunk": "semantic only evidence",
                "context_text": "semantic only",
                "embedding_text": "semantic only",
            },
            score=0.2,
            similarity_score=0.2,
            anchor_boost=0.0,
            final_score=0.2,
        )

        context = IdiomRetriever.build_context([semantic])

        self.assertEqual(context, "")

    def test_build_context_excludes_partial_low_results_from_prompt_context(self) -> None:
        partial = RetrievalResult(
            item={
                "source_id": "jp-00113",
                "anchor": "?? ??",
                "matched_phrase": "?? ??",
                "match_type": "partial",
                "confidence": "low",
                "lexical_evidence": True,
                "evidence_chunk": "???? ?? ???",
                "context_text": "source phrase: ?? ??",
                "embedding_text": "?? ??",
            },
            score=0.9,
            similarity_score=0.0,
            anchor_boost=0.9,
            final_score=0.9,
        )

        context = IdiomRetriever.build_context([partial])

        self.assertEqual(context, "")

    def test_build_context_includes_normalized_high_for_ankle_hold(self) -> None:
        normalized = RetrievalResult(
            item={
                "source_id": "jp-00112",
                "anchor": "??? ??",
                "matched_phrase": "??? ??",
                "match_type": "normalized",
                "confidence": "high",
                "lexical_evidence": True,
                "evidence_chunk": "??? ??",
                "context_text": "source phrase: ??? ??",
                "embedding_text": "??? ??",
            },
            score=0.95,
            similarity_score=0.0,
            anchor_boost=0.95,
            final_score=0.95,
        )

        context = IdiomRetriever.build_context([normalized])

        self.assertIn("source_id: jp-00112", context)
        self.assertIn("anchor: ??? ??", context)
        self.assertIn("matched_phrase: ??? ??", context)
        self.assertIn("match_type: normalized", context)
        self.assertIn("confidence: high", context)

    def test_build_context_includes_normalized_high_for_hand_release(self) -> None:
        normalized = RetrievalResult(
            item={
                "source_id": "jp-expanded-00107",
                "anchor": "?? ??",
                "matched_phrase": "?? ??",
                "match_type": "normalized",
                "confidence": "high",
                "lexical_evidence": True,
                "evidence_chunk": "?? ??",
                "context_text": "source phrase: ?? ??",
                "embedding_text": "?? ??",
            },
            score=0.95,
            similarity_score=0.0,
            anchor_boost=0.95,
            final_score=0.95,
        )

        context = IdiomRetriever.build_context([normalized])

        self.assertIn("source_id: jp-expanded-00107", context)
        self.assertIn("anchor: ?? ??", context)
        self.assertIn("matched_phrase: ?? ??", context)
        self.assertIn("match_type: normalized", context)
        self.assertIn("confidence: high", context)

    def test_build_debug_context_shows_semantic_low_candidates(self) -> None:
        semantic = RetrievalResult(
            item={
                "source_id": "jp-00999",
                "anchor": "",
                "matched_phrase": "",
                "match_type": "semantic",
                "confidence": "low",
                "lexical_evidence": False,
                "evidence_chunk": "semantic only evidence",
                "context_text": "semantic only",
                "embedding_text": "semantic only",
            },
            score=0.2,
            similarity_score=0.2,
            anchor_boost=0.0,
            final_score=0.2,
        )

        debug_context = IdiomRetriever.build_debug_context([semantic])

        self.assertIn("[RAG-DEBUG] Korean-idiom reference matches", debug_context)
        self.assertIn("source_id: jp-00999", debug_context)
        self.assertIn("match_type: semantic", debug_context)
        self.assertIn("confidence: low", debug_context)
        self.assertIn("lexical_evidence: False", debug_context)

    def test_retrieve_prioritizes_lexical_match_before_semantic_only_results(self) -> None:
        items = [
            {
                "id": "jp-00112",
                "embedding_text": "발목을 잡다, 발목을 붙잡다. 남의 일을 방해하거나 발목을 잡아 진도를 늦추게 함",
                "context_text": "원문 표현: x\\n한국어 기준 표현: 발목을 잡다, 발목을 붙잡다",
            },
            {
                "id": "jp-00901",
                "embedding_text": "목이 빠지게 기다리다. 몹시 오래 기다리다",
                "context_text": "원문 표현: x\\n한국어 기준 표현: 목이 빠지게 기다리다",
            },
            {
                "id": "jp-00902",
                "embedding_text": "자라 보고 놀란 가슴. 한번 놀란 뒤에는 쉽게 겁을 먹는 상태",
                "context_text": "원문 표현: x\\n한국어 기준 표현: 자라 보고 놀란 가슴",
            },
        ]
        retriever = self._build_retriever(items, score_threshold=0.0)

        chunk = "이런 초라한 모습으로 그녀의 발목을 잡고 있는 것은 아닐까 하는 생각이 하루에도 수십 번씩 머릿속을 맴돌았다."
        results = retriever.retrieve(chunk, top_k=3)

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].item["source_id"], "jp-00112")
        self.assertIn(results[0].item["match_type"], {"exact", "normalized", "partial"})
        self.assertTrue(results[0].item["lexical_evidence"])
        if results[0].item["match_type"] in {"exact", "normalized"}:
            self.assertEqual(results[0].item["confidence"], "high")
        else:
            self.assertEqual(results[0].item["confidence"], "low")
        self.assertEqual(results[0].item["evidence_chunk"], chunk)
        self.assertEqual(results[0].item["anchor"], "발목을 잡다")
        if len(results) > 1:
            self.assertNotEqual(results[1].item["match_type"], "exact")
            self.assertIn(results[1].item["match_type"], {"semantic", "normalized", "partial"})

    def test_retrieve_returns_partial_match_for_particle_drop(self) -> None:
        partial = RetrievalResult(
            item={
                "source_id": "jp-00113",
                "anchor": "?? ??",
                "matched_phrase": "?? ??",
                "match_type": "partial",
                "confidence": "low",
                "lexical_evidence": True,
                "evidence_chunk": "???? ?? ???",
                "context_text": "source phrase: ?? ??",
                "embedding_text": "?? ??",
            },
            score=0.9,
            similarity_score=0.0,
            anchor_boost=0.9,
            final_score=0.9,
        )

        context = IdiomRetriever.build_context([partial])

        self.assertEqual(context, "")

    def test_search_keeps_partial_low_out_of_prompt_context(self) -> None:
        retriever = self._build_retriever(
            [
                {
                    "id": "jp-00113",
                    "embedding_text": "손에 쥐다, 손에 쥔 것, 손에 쥐고 있다",
                    "context_text": "원문 표현: x\n한국어 기준 표현: 손에 쥐다",
                },
                {
                    "id": "jp-00112",
                    "embedding_text": "발목을 잡다, 발목을 잡고 있다, 발목을 잡아 진도를 늦추다",
                    "context_text": "원문 표현: x\n한국어 기준 표현: 발목을 잡다",
                },
                {
                    "id": "jp-expanded-00107",
                    "embedding_text": "손을 놓다, 손을 놓지 않다, 끝까지 손을 놓지 않는다",
                    "context_text": "원문 표현: x\n한국어 기준 표현: 손을 놓다",
                },
                {
                    "id": "jp-00999",
                    "embedding_text": "눈에 띄다, 눈에 띄는 변화, 확연히 눈에 띄다",
                    "context_text": "원문 표현: x\n한국어 기준 표현: 눈에 띄다",
                },
            ],
            score_threshold=0.0,
        )

        query = "강현우는 오른손에 쥐인 야구공의 실밥을 거칠게 쓸어내렸다. 발목을 잡고 있던 문제는 사라졌고, 그는 끝까지 손을 놓지 않았다. 눈에 띄는 변화도 있었다."
        results = retriever.retrieve(query, top_k=4)
        context = IdiomRetriever.build_context(results)

        partial = next(
            row for row in results
            if row.item["anchor"] == "손에 쥐다" or row.item["source_id"] == "jp-00113"
        )
        if partial.item["match_type"] == "partial":
            self.assertEqual(partial.item["confidence"], "low")
        self.assertNotIn("손에 쥐다", context)
        self.assertNotIn("jp-00113", context)

        self.assertIn("발목을 잡다", context)
        self.assertIn("손을 놓다", context)
        self.assertIn("눈에 띄다", context)
        self.assertIn("confidence: high", context)

    def test_retrieve_does_not_lexically_match_semantic_neighbor_only(self) -> None:
        items = [
            {
                "id": "jp-00999",
                "embedding_text": "어깨가 가볍다. 심리적으로 가벼운 상태",
                "context_text": "원문 표현: x\\n한국어 기준 표현: 어깨가 가볍다",
            }
        ]
        retriever = self._build_retriever(items, score_threshold=0.0)

        chunk = "오늘 공 던지는 거 보니까 어깨 좀 무거워 보이던데, 괜찮아?"
        results = retriever.retrieve(chunk, top_k=1)

        if results:
            self.assertEqual(results[0].item["source_id"], "jp-00999")
            self.assertEqual(results[0].item["match_type"], "semantic")
            self.assertFalse(results[0].item["lexical_evidence"])
            self.assertEqual(results[0].item["confidence"], "low")
            self.assertEqual(results[0].item["matched_phrase"], "")
            self.assertEqual(results[0].item["anchor"], "")
            self.assertEqual(results[0].item["evidence_chunk"], chunk)

    def test_retrieve_deduplicates_same_anchor_family_across_source_ids(self) -> None:
        items = [
            {
                "id": "jp-10001",
                "embedding_text": "속이 좁다. 마음이 너그럽지 못하다",
                "context_text": "원문 표현: x\\n한국어 기준 표현: 속이 좁다",
            },
            {
                "id": "jp-10002",
                "embedding_text": "속이 좁다. 사람을 쉽게 용서하지 못하다",
                "context_text": "원문 표현: x\\n한국어 기준 표현: 속이 좁다",
            },
        ]
        retriever = self._build_retriever(items, score_threshold=0.0)

        chunk = "그 사람은 왜 그렇게 속이 좁다며 사람들 사이에 소문이 났다."
        results = retriever.retrieve(chunk, top_k=3)

        lexical = [row for row in results if row.item["match_type"] != "semantic"]
        self.assertEqual(len(lexical), 1)
        self.assertEqual(lexical[0].item["confidence"], "high")
        self.assertTrue(lexical[0].item["lexical_evidence"])
        self.assertEqual(lexical[0].item["representative_anchor"], "속이 좁다")


if __name__ == "__main__":
    unittest.main()
