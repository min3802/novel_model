from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.translation import PipelineConfig
from app.translation.retrieval.annotation_retriever import AnnotationRetriever, build_annotation_search_text
from app.translation.retrieval.retriever import IdiomRetriever
from scripts.build_k_culture_rag import build_annotation_dataset, make_annotation_card


class KCultureRagTests(unittest.TestCase):
    def test_k_culture_row_becomes_annotation_card(self) -> None:
        row = {
            "DescriptionID": 3,
            "Description": "삼복더위를 이기기 위해 한국인들은 삼계탕 등 원기 회복을 돕는 음식을 먹는다.",
            "ScenarioBody": "민지는 초복이라 삼계탕을 먹어야 한다고 말했다.",
            "MCQA": {
                "Question": "무엇을 중요하게 여기는가?",
                "Choices": "A. 여름철 보양식",
                "Answer": "A",
                "Explanation": "삼복과 삼계탕은 여름철 보양식 전통과 관련된다.",
            },
            "Type": "1",
            "Category": "Food and Drinks",
        }

        card = make_annotation_card(row)

        self.assertEqual(card["id"], "KCULTURE_0003")
        self.assertNotIn("source", card)
        self.assertIn("embedding_text", card)
        self.assertIn("context_text", card)
        self.assertIn("metadata", card)
        self.assertIn("삼계탕", card["trigger_terms"])
        self.assertEqual(card["metadata"]["category"], "Food and Drinks")
        self.assertIn("삼복더위 / 삼계탕 관련 한국 문화 맥락", card["context_text"])
        self.assertIn("음식 자체보다", card["context_text"])
        self.assertIn("음식명만 옮기지 말고", card["context_text"])
        self.assertNotIn("정답", card["context_text"])
        self.assertNotIn("오답", card["context_text"])
        self.assertNotIn("weak_terms", card)
        self.assertNotIn("scenario", card)
        self.assertNotIn("annotation_hint", card)

    def test_generated_k_culture_dataset_is_searchable_by_annotation_retriever(self) -> None:
        config = PipelineConfig(locale="ko_en_us", mock=True, idiom_top_k=5, annotation_score_threshold=0.0)
        retriever = AnnotationRetriever(config)

        results = retriever.retrieve("초복이라 삼계탕을 먹고 몸보신했다.", top_k=5)

        self.assertTrue(results)
        self.assertTrue(any(str(row.item.get("id", "")).startswith("KCULTURE_") for row in results))
        self.assertTrue(all(row.trigger_boost == 0.0 for row in results))
        self.assertTrue(all(row.final_score == row.similarity_score for row in results))

    def test_default_annotation_dataset_uses_reviewed_documents(self) -> None:
        config = PipelineConfig(locale="ko_en_us", mock=True, idiom_top_k=5)
        self.assertEqual(config.resolved_annotation_dataset_path().name, "kculture_rag_documents_reviewed.json")
        retriever = AnnotationRetriever(config)

        self.assertEqual(len(retriever.items), 494)
        first = retriever.items[0]
        self.assertEqual(set(first.keys()), {"id", "embedding_text", "context_text", "metadata"})
        self.assertIn("한국 야구장 응원 문화", first["embedding_text"])

    def test_reviewed_schema_uses_embedding_text_without_lexical_boost(self) -> None:
        item = {
            "id": "KCULTURE_TEST",
            "embedding_text": "새 차를 산 뒤 막걸리를 뿌려 무사고를 기원하는 한국 풍습이다.",
            "context_text": "주석 설명: 새 차 막걸리 의식 설명.\n번역 가이드: 목적을 전달한다.",
            "metadata": {"keyword_ko": "새 차 막걸리 의식", "category": "Traditions and Rituals"},
        }

        self.assertEqual(build_annotation_search_text(item), item["embedding_text"])
        self.assertEqual(AnnotationRetriever._trigger_match_boost(item, "새 차 막걸리 의식을 했다."), 0.0)
        self.assertEqual(AnnotationRetriever._trigger_match_boost(item, "막걸리를 차에 뿌렸다."), 0.0)

    def test_translation_rag_stays_separate_from_k_culture_annotations(self) -> None:
        retriever = IdiomRetriever(PipelineConfig(locale="ko_en_us", mock=True, idiom_top_k=5))

        self.assertTrue(retriever.items)
        self.assertFalse(any(row.get("source_type") == "k_culture_desc" for row in retriever.items))

    def test_build_annotation_dataset_writes_single_annotation_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "K-Culture_desc.json"
            source.write_text(
                json.dumps(
                    [
                        {
                            "DescriptionID": 12,
                            "Description": "한국에서는 아이스 아메리카노를 좋아하는 사람들을 일컬어 '얼죽아'라고 부른다.",
                            "ScenarioBody": "추운 날에도 민지는 얼죽아라며 아이스 아메리카노를 주문했다.",
                            "MCQA": {"Explanation": "추운 날에도 아이스 음료를 선호하는 표현이다."},
                            "Type": "1",
                            "Category": "Language",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = base / "out" / "k_culture_annotation_cards.json"
            report = build_annotation_dataset(source, output)

            self.assertEqual(report["k_culture_rows"], 1)
            self.assertEqual(report["annotation_cards"], 1)
            self.assertTrue(output.exists())
            card = json.loads(output.read_text(encoding="utf-8"))[0]
            self.assertEqual(card["id"], "KCULTURE_0012")
            self.assertIn("얼죽아", card["trigger_terms"])
            self.assertIn("얼죽아", card["metadata"]["keyword_ko"])
            self.assertIn("embedding_text", card)
            self.assertIn("context_text", card)

    def test_scenario_dialogue_does_not_become_trigger_term(self) -> None:
        row = {
            "DescriptionID": 22,
            "Description": "복날에는 더위를 이기기 위해 삼계탕 같은 보양식을 먹기도 한다.",
            "ScenarioBody": "일본 친구는 '도요우노 우시노 히'와 비슷하냐고 물었다.",
            "MCQA": {"Explanation": "복날 보양식 문화와 관련된다."},
            "Type": "1",
            "Category": "Food and Drinks",
        }

        card = make_annotation_card(row)

        self.assertNotIn("도요우노 우시노 히", card["trigger_terms"])
        self.assertNotIn("도요우노", " ".join(card["trigger_terms"]))
        self.assertNotIn("도요우노", json.dumps(card, ensure_ascii=False))
        self.assertIn("삼계탕", card["trigger_terms"])

    def test_translation_guides_are_category_specific(self) -> None:
        food_card = make_annotation_card(
            {
                "DescriptionID": 1,
                "Description": "복날에는 삼계탕을 먹는다.",
                "ScenarioBody": "",
                "MCQA": {},
                "Type": "1",
                "Category": "Food and Drinks",
            }
        )
        language_card = make_annotation_card(
            {
                "DescriptionID": 2,
                "Description": "얼죽아는 추운 날에도 아이스 아메리카노를 마시는 사람을 가리킨다.",
                "ScenarioBody": "",
                "MCQA": {},
                "Type": "1",
                "Category": "Language",
            }
        )

        self.assertIn("음식명만 옮기지 말고", food_card["context_text"])
        self.assertIn("말장난·줄임말·유행어", language_card["context_text"])
        self.assertNotEqual(food_card["context_text"], language_card["context_text"])


if __name__ == "__main__":
    unittest.main()
