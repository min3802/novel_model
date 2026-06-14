from __future__ import annotations

import unittest

from backend.services.translation_service import format_review_summary


class ReviewSummaryFormattingTests(unittest.TestCase):
    def test_format_review_summary_uses_readable_korean_labels(self) -> None:
        workflow = {
            "inspection": {
                "summary": "전반적인 의미 전달은 잘 되었지만 일부 표현은 더 자연스럽게 다듬을 수 있습니다.",
                "issues": [
                    {
                        "severity": "HIGH",
                        "problem": "문장 톤이 원문의 긴장감을 충분히 살리지 못했습니다.",
                        "translated_span": "該当箇所の訳文",
                        "suggested": "より緊張感のある表現に調整してください。",
                    }
                ],
            },
            "draft": {
                "rationale": "일본 독자가 자연스럽게 읽을 수 있도록 문장 흐름과 어조를 조정했습니다."
            },
        }

        summary = format_review_summary(workflow)

        self.assertIn("1. 전체 검토 요약", summary)
        self.assertIn("2. 문제 번역 구간 및 제안", summary)
        self.assertIn("3. 문체/현지화 전략", summary)
        self.assertIn("최고 심각도: 높음", summary)
        self.assertIn("원본 심각도 코드: HIGH", summary)
        self.assertIn("번역 구간: 該当箇所の訳文", summary)
        self.assertIn("제안 표현: より緊張感のある表現に調整してください。", summary)
        self.assertNotIn("???", summary)
        self.assertFalse(summary.startswith("1. ?"))

    def test_format_review_summary_handles_empty_issues_with_clean_fallback(self) -> None:
        workflow = {
            "inspection": {"summary": "", "issues": []},
            "draft": {"rationale": ""},
        }

        summary = format_review_summary(workflow)

        self.assertIn("1. 전체 검토 요약", summary)
        self.assertIn("2. 문제 번역 구간 및 제안", summary)
        self.assertIn("3. 문체/현지화 전략", summary)
        self.assertIn("검토 요약이 비어 있지만", summary)
        self.assertIn("별도 수정이 필요한 문제 구간은 발견되지 않았습니다.", summary)
        self.assertIn("번역 근거 설명이 제공되지 않아도", summary)


if __name__ == "__main__":
    unittest.main()
