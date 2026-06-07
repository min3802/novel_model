from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.translation import TranslationPipeline, PipelineConfig
from app.translation.core.locales import LOCALE_REGISTRY
from app.translation.retrieval.retriever import IdiomRetriever, MockEmbeddingBackend, build_search_text, create_embedding_backend


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

    def _build_retriever(
        self,
        items: list[dict],
        locale: str = "ko_ja",
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

        result = pipeline.run("this is two birds one stone")
        row = result.retrievals[0]

        self.assertIn("similarity_score", row)
        self.assertIn("anchor_boost", row)
        self.assertIn("final_score", row)
        self.assertAlmostEqual(row["final_score"], row["similarity_score"] + row["anchor_boost"], places=6)
        self.assertEqual(result.final_translation, "[MOCK English (US)] this is two birds one stone")

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
        # qdrant payload는 평면 구조(country/language가 최상위, source_id 사용).
        item = {
            "source_id": "US_000002",
            "embedding_text": "이렇게 하면 끝, 그거면 됐지, 식은 죽 먹기. 어렵지 않게 끝난다.",
            "context_text": "원문 표현: Bob's your uncle\n한국어 기준 표현: 이렇게 하면 끝",
            "country": "US",
            "language": "en",
        }
        retriever = self._build_retriever([item], locale="ko_en_us", score_threshold=0.0)
        result = retriever.retrieve("이렇게 하면 끝", top_k=1)[0]

        self.assertEqual(result.anchor_boost, 0.0)
        context = IdiomRetriever.build_context([result])
        # context_text 는 LLM 에 넘어가야 한다.
        self.assertIn("원문 표현: Bob's your uncle", context)
        # 노이즈/중복 필드(country, source_id, 검색 점수)는 LLM 프롬프트에서 제외됨.
        self.assertNotIn("country", context)
        self.assertNotIn("US_000002", context)
        self.assertNotIn("similarity_score", context)


if __name__ == "__main__":
    unittest.main()
