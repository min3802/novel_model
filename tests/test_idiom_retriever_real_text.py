from __future__ import annotations

import unittest

from app.translation.retrieval.idiom_retriever import IdiomRetriever
from app.translation.retrieval.retriever import RetrievalResult


class IdiomRetrieverRealTextTests(unittest.TestCase):
    def test_partial_low_result_stays_out_of_prompt_context(self) -> None:
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

    def test_normalized_high_results_stay_in_prompt_context(self) -> None:
        normalized_ankle = RetrievalResult(
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
        normalized_hand = RetrievalResult(
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

        context = IdiomRetriever.build_context([normalized_ankle, normalized_hand])

        self.assertIn("source_id: jp-00112", context)
        self.assertIn("anchor: ??? ??", context)
        self.assertIn("matched_phrase: ??? ??", context)
        self.assertIn("source_id: jp-expanded-00107", context)
        self.assertIn("anchor: ?? ??", context)
        self.assertIn("matched_phrase: ?? ??", context)
        self.assertIn("match_type: normalized", context)
        self.assertIn("confidence: high", context)

    def test_semantic_low_result_stays_out_of_prompt_context(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
