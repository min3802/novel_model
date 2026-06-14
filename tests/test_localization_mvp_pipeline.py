from __future__ import annotations

import unittest

from app.guide.localization_mvp_pipeline import build_localization_guide_mvp, build_policy_checkpoints
from app.guide.cultural_localization import _tokens
from app.guide.work_analysis import analyze_work
from backend.services.guide_service import guide


class LocalizationGuideMvpPipelineTests(unittest.TestCase):
    def test_cultural_tokenizer_keeps_korean_terms(self) -> None:
        self.assertIn('예비군', _tokens('예비군 한국 군복'))
        self.assertIn('한국', _tokens('예비군 한국 군복'))

    def test_work_analyzer_extracts_elements_and_cautions(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "title": '예비군 8년차는 비상소집을 거부한다',
                "genre": '현대 판타지',
                "synopsis": '서울에서 전역 후 살아가던 주인공이 예비군 비상소집과 괴물 습격에 휘말린다. 폭력 가능성이 있다.',
            }
        )

        self.assertEqual(work["mode"], "detailed")
        self.assertEqual(work["targetCountry"], "US")
        self.assertIn('예비군', work["confirmedElements"])
        self.assertIn('군 복무', work["confirmedElements"])
        self.assertIn('현대 한국 배경', work["confirmedElements"])
        self.assertIn('군사/국가 시스템', work["contentCautions"])
        self.assertIn('잔혹 묘사', work["contentCautions"])


    def test_work_analyzer_keeps_raw_input_signals_separate_from_confirmed_elements(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "title": '러브 앤 블러드',
                "genre": '현대 로맨스 / 작가물 / 혐관 로맨스 / 상처 치유',
                "synopsis": '상처를 숨긴 작가가 계약 관계로 얽힌 상대와 혐관 로맨스를 시작한다. 과거 살인 사건과 트라우마가 두 사람의 감정 성장을 흔든다.',
                "declaredSignals": [
                    '작가와 작가',
                    '계약관계',
                    '혐관에서 로맨스',
                    '전애인 트라우마',
                    '상처녀',
                    '성장형 로맨스',
                    '감정 치유',
                    '멜로 과외',
                ],
            }
        )

        elements = work["confirmedElements"]
        self.assertIn('작가물', elements)
        self.assertIn('계약 관계', elements)
        self.assertIn('혐관 로맨스', elements)
        self.assertIn('상처 치유', elements)
        self.assertNotIn('작가와 작가', elements)
        self.assertNotIn('혐관에서 로맨스', elements)
        self.assertIn('작가와 작가', work["supportingInputSignals"])
        self.assertIn('멜로 과외', work["additionalInputSignals"])

    def test_modern_romance_genre_does_not_imply_korean_setting(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "genre": '현대 로맨스',
                "title": "Love Contract",
            }
        )

        self.assertEqual(work["mode"], "baseline")
        self.assertIn('로맨스 관계', work["confirmedElements"])
        self.assertNotIn('현대 한국 배경', work["confirmedElements"])

    def test_age_rating_and_sexual_violence_are_separate_cautions(self) -> None:
        work = analyze_work(
            {
                "targetCountry": "US",
                "title": '어두운 밤',
                "genre": '스릴러',
                "synopsis": 'R15 등급으로 검토 중이며 성폭력 피해와 폭력 사건을 다룬다.',
            }
        )

        self.assertIn('연령 등급 표시', work["contentCautions"])
        self.assertIn('성폭력 소재', work["contentCautions"])
        self.assertIn('잔혹 묘사', work["contentCautions"])
        self.assertNotIn('성적 묘사', work["contentCautions"])

    def test_mvp_pipeline_builds_culture_policy_metadata_report(self) -> None:
        result = build_localization_guide_mvp(
            {
                "targetCountry": "US",
                "title": '예비군 8년차는 비상소집을 거부한다',
                "genre": '현대 판타지',
                "synopsis": '서울에서 전역 후 살아가던 주인공이 예비군 비상소집과 괴물 습격에 휘말린다.',
            }
        )

        self.assertEqual(result["pipelineVersion"], "localization_guide_mvp_v1")
        self.assertEqual(result["guideKind"], "metadata_culture_policy_localization_guide")
        self.assertIn("workProfile", result)
        self.assertIn("marketContext", result)
        self.assertIn("culturalLocalization", result)
        self.assertIn("policyCheck", result)
        self.assertIn("metadataPositioning", result)
        self.assertIn("finalGuard", result)
        self.assertTrue(result["localizationGuideMvp"]["cultureNotes"])
        self.assertTrue(result["localizationGuideMvp"]["metadataDirections"])
        self.assertIn("no_story_rewrite_instruction", result["finalGuard"]["overclaimPrevention"])
        self.assertTrue(
            any('성공 가능성' in item or '독자 선호' in item for item in result["localizationGuideMvp"]["limitations"])
        )

    def test_policy_checkpoints_use_work_cautions_not_raw_synopsis(self) -> None:
        payload = {
            "targetCountry": "Japan",
            "title": '평범한 공녀',
            "genre": '로맨스 판타지',
            "synopsis": '성적 묘사와 잔혹 묘사가 짙어 R18 표시를 검토해야 한다.',
        }
        work = analyze_work(payload)
        policy = build_policy_checkpoints(payload, work)

        self.assertEqual(policy["matchedFrom"], "work_profile.contentCautions")
        self.assertEqual(policy["contentCautions"], work["contentCautions"])
        self.assertTrue(policy["policyCheckpoints"])
        self.assertTrue(
            all(card["match_source"] == "direct_input" for card in policy["policyCheckpoints"]),
            '새 정책 체크는 원문 전체가 아니라 Work Analyzer의 contentCautions를 직접 입력으로 사용해야 한다.',
        )
        self.assertTrue(all("checkpoint" in card for card in policy["policyCheckpoints"]))
        self.assertTrue(
            any(card["card_title"] == '폭력/잔혹 묘사 수위 확인' for card in policy["policyCheckpoints"])
        )

    def test_culture_notes_avoid_unrelated_rag_but_keep_general_korean_source_guidance(self) -> None:
        result = build_localization_guide_mvp(
            {
                "targetCountry": "US",
                "title": '러브 앤 블러드',
                "genre": '현대 로맨스 / 작가물 / 혐관 로맨스 / 상처 치유',
                "synopsis": (
                    '상처를 숨긴 작가가 계약 관계로 얽힌 상대와 혐관 로맨스를 시작한다. '
                    '두 사람은 서로의 글과 감정을 배우며 오해를 풀고 성장한다. '
                    '출판사와 소설 작업을 둘러싼 갈등은 있지만 별도 제도나 의례 설명이 필요한 소재는 없다.'
                ),
            }
        )

        self.assertEqual(result["reportMode"], "detailed")
        notes = result["culturalLocalization"]["cultureNotes"]
        self.assertTrue(notes)
        self.assertEqual(notes[0]["element"], '한국어 원문 관계 표현')
        self.assertFalse(
            any(note["element"] in {'한국 군복 패턴 구분', '학생 서열 문화', '교복 소비 서열 문화'} for note in notes)
        )
        self.assertEqual(result["culturalLocalization"]["evidence"]["kcultureCardCount"], 0)

    def test_guide_service_uses_new_criteria_flow_by_default(self) -> None:
        result = guide(
            {
                "targetCountry": "Japan",
                "title": "?????? ???????? ??? ?????",
                "genre": "??????????",
                "synopsis": "????????????? ????? ?????????????????????.",
            }
        )

        self.assertIn("recommendedCountries", result)
        self.assertIn("translation_profile", result)
        self.assertIn("summary_text", result)
        self.assertIn("htmlReport", result)
        self.assertIn('번역 전 현지화 기준서', result["htmlReport"])
        self.assertIn(result["generationMode"], {"recommended_country_selected", "manual_country_after_recommendation"})
        self.assertEqual(result["mode"], "country_genre_guide")
        self.assertNotIn("Localization Guide MVP", result["htmlReport"])
        self.assertNotIn("reportMode:", result["htmlReport"])
        self.assertIn('번역 전 현지화 기준서', result["htmlReport"])

    def test_guide_service_preserves_legacy_path_when_requested(self) -> None:
        result = guide(
            {
                "legacyGuide": True,
                "targetCountry": "Japan",
                "title": '버림받은 공녀는 다시 웃지 않는다',
                "genre": '로맨스 판타지',
                "synopsis": '가문에서 버림받은 공녀가 회귀해 자신의 자리를 되찾는다.',
            }
        )

        self.assertIn("contextPackBriefing", result)
        self.assertIn("policyAttentionCards", result)
        self.assertNotIn("pipelineVersion", result)


if __name__ == "__main__":
    unittest.main()
