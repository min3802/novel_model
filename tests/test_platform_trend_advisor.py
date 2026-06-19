
import unittest

import api_server
from app.guide.platform_trend_advisor import build_localization_advice, rank_countries
from app.guide.platform_trend_guide import load_trend_data


class PlatformTrendAdvisorTests(unittest.TestCase):
    def test_without_synopsis_and_country_returns_selection_options(self):
        result = build_localization_advice({"genre": '로판'})

        self.assertEqual(result["mode"], "needs_country_and_genre_selection")
        self.assertTrue(result["requiresSelection"])
        self.assertIn("countries", result["availableOptions"])
        self.assertGreaterEqual(len(result["availableOptions"]["countries"]), 2)
        self.assertIn("genres", result["availableOptions"])

    def test_without_synopsis_uses_selected_country_and_genre(self):
        result = build_localization_advice({"targetCountry": '미국', "genre": "LitRPG"})

        self.assertEqual(result["mode"], "country_genre_guide")
        self.assertEqual(result["targetCountry"], "US/global English")
        self.assertFalse(result["requiresSelection"])
        self.assertIn("market_trend_fit", result["sections"])
        self.assertIn("evidence_used", result["sections"])
        self.assertTrue(result["evidenceUsed"])
        self.assertIn("requiredOutputSections", result["modelPromptPayload"])
        self.assertEqual(result["generationMode"], "manual_country_without_synopsis")
        self.assertIn("translation_profile", result)
        self.assertIn("summary_text", result)
        self.assertIn("available_countries", result)

    def test_with_synopsis_recommends_country_before_generation(self):
        synopsis = '회귀한 악녀가 공작과 계약 결혼을 맺고 가문 권력을 되찾는 로맨스 판타지'
        result = build_localization_advice({"genre": '로판', "synopsis": synopsis})

        self.assertEqual(result["mode"], "synopsis_country_recommendation")
        self.assertTrue(result["requiresSelection"])
        self.assertEqual(result["title"], '추천 국가를 먼저 확인해 주세요')
        self.assertIn("recommended_country", result)
        self.assertIn("recommendation_reasons", result)
        self.assertIn("limitation_notice", result)
        self.assertIn("available_countries", result)
        self.assertTrue(result["recommendedCountries"])
        self.assertIn(result["recommended_country"], {rec["country"] for rec in result["recommendedCountries"]})

    def test_with_synopsis_and_selected_country_generates_guide(self):
        synopsis = '회귀한 악녀가 공작과 계약 결혼을 맺고 가문 권력을 되찾는 로맨스 판타지'
        result = build_localization_advice({"genre": '로판', "synopsis": synopsis, "targetCountry": "Japan"})

        self.assertEqual(result["mode"], "country_genre_guide")
        self.assertIn(result["generationMode"], {"recommended_country_selected", "manual_country_after_recommendation"})
        self.assertFalse(result["requiresSelection"])
        self.assertIn("translation_profile", result)
        self.assertIn("summary_text", result)
        self.assertIn("guide_html", result)
        self.assertIn(result["recommended_country"], {"Japan", "China", "US/global English", "Thailand"})
        self.assertIn(result["targetCountry"], {"Japan", "China", "US/global English", "Thailand"})
        self.assertIn("title_synopsis_localization", result["sections"])
        self.assertIn("evidence_used", result["sections"])
        self.assertIn('번역 전 현지화 기준서', result["htmlReport"])

    def test_rank_countries_uses_genre_and_synopsis_evidence(self):
        data = load_trend_data()
        recs = rank_countries(data, genre="LitRPG", synopsis='시스템 스킬 던전 레벨업 성장')

        self.assertGreaterEqual(len(recs), 2)
        self.assertEqual(recs[0].country, "US/global English")
        self.assertGreater(recs[0].score, 0)
        self.assertTrue(recs[0].evidence)

    def test_api_guide_preserves_required_legacy_html_sections(self):
        result = api_server.guide({"legacyGuide": True, "targetCountry": '미국', "genre": '판타지'})

        self.assertIn('제목/시놉시스', result["htmlReport"])
        self.assertIn('문화', result["htmlReport"])
        self.assertIn('플랫폼', result["htmlReport"])
        self.assertIn("modelPromptPayload", result)

    def test_final_guide_html_stays_korean_and_country_centric(self):
        result = build_localization_advice(
            {
                "targetCountry": '미국',
                "genre": "로맨스",
                "synopsis": "두 사람이 사랑을 시작하는 현대 로맨스 이야기다.",
            }
        )

        html = result["htmlReport"]
        self.assertIn("선택 국가 요약", html)
        self.assertIn("플랫폼 트렌드 참고", html)
        self.assertNotIn("current platform trends", html)
        self.assertNotIn("추천 국가 후보", html)
        self.assertNotIn("미국는", html)
        self.assertNotIn("일본는", html)
        self.assertNotIn("회귀·전생·이세계 축", html)


if __name__ == "__main__":
    unittest.main()

