import unittest

from ko_locale_pipeline.config import PipelineConfig
from ko_locale_pipeline.context_extractor import ContextExtractor
from ko_locale_pipeline.ontology import compact_memory_context, create_empty_memory, merge_extraction


class WorkMemoryTest(unittest.TestCase):
    def test_mock_extractor_finds_cultural_term_candidates(self):
        extractor = ContextExtractor(PipelineConfig(mock=True))
        result = extractor.extract("김첨지는 아내가 말한 설렁탕 생각에 발걸음을 재촉했다.")

        self.assertTrue(any(row["source"] == "설렁탕" for row in result.terms))
        self.assertIn("설렁탕", result.ragQueries)

    def test_merge_extraction_keeps_suggested_memory_context(self):
        memory = create_empty_memory(7, title="테스트 작품")
        merged = merge_extraction(
            memory,
            {
                "characters": [
                    {
                        "name": "김첨지",
                        "role": "주인공",
                        "traits": ["인력거꾼"],
                        "aliases": [],
                        "confidence": 0.8,
                        "status": "suggested",
                        "evidence": ["김첨지는"],
                    }
                ],
                "terms": [
                    {
                        "source": "설렁탕",
                        "type": "cultural_term",
                        "meaning": "한국 음식",
                        "policy": "음차 유지 검토",
                        "recommendedTranslation": "seolleongtang",
                        "confidence": 0.8,
                        "status": "suggested",
                        "evidence": ["설렁탕"],
                    }
                ],
            },
        )

        context = compact_memory_context(merged)
        self.assertIn("김첨지", context)
        self.assertIn("설렁탕", context)
        self.assertIn("suggested", context)


if __name__ == "__main__":
    unittest.main()
