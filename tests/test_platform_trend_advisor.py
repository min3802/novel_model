
import unittest

import api_server
from app.guide.platform_trend_advisor import build_localization_advice, rank_countries
from app.guide.platform_trend_guide import load_trend_data


class PlatformTrendAdvisorTests(unittest.TestCase):
    def test_without_synopsis_and_country_returns_selection_options(self):
        result = build_localization_advice({"genre": "\ub85c\ud310"})

        self.assertEqual(result["mode"], "needs_country_and_genre_selection")
        self.assertTrue(result["requiresSelection"])
        self.assertIn("countries", result["availableOptions"])
        self.assertGreaterEqual(len(result["availableOptions"]["countries"]), 2)
        self.assertIn("genres", result["availableOptions"])

    def test_without_synopsis_uses_selected_country_and_genre(self):
        result = build_localization_advice({"targetCountry": "\ubbf8\uad6d", "genre": "LitRPG"})

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
        synopsis = "\ud68c\uadc0\ud55c \uc545\ub140\uac00 \uacf5\uc791\uacfc \uacc4\uc57d \uacb0\ud63c\uc744 \ub9fa\uace0 \uac00\ubb38 \uad8c\ub825\uc744 \ub418\ucc3e\ub294 \ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0"
        result = build_localization_advice({"genre": "\ub85c\ud310", "synopsis": synopsis})

        self.assertEqual(result["mode"], "synopsis_country_recommendation")
        self.assertTrue(result["requiresSelection"])
        self.assertEqual(result["title"], "추천 국가를 먼저 확인해 주세요")
        self.assertIn("recommended_country", result)
        self.assertIn("recommendation_reasons", result)
        self.assertIn("limitation_notice", result)
        self.assertIn("available_countries", result)
        self.assertTrue(result["recommendedCountries"])
        self.assertIn(result["recommended_country"], {rec["country"] for rec in result["recommendedCountries"]})

    def test_with_synopsis_and_selected_country_generates_guide(self):
        synopsis = "\ud68c\uadc0\ud55c \uc545\ub140\uac00 \uacf5\uc791\uacfc \uacc4\uc57d \uacb0\ud63c\uc744 \ub9fa\uace0 \uac00\ubb38 \uad8c\ub825\uc744 \ub418\ucc3e\ub294 \ub85c\ub9e8\uc2a4 \ud310\ud0c0\uc9c0"
        result = build_localization_advice({"genre": "\ub85c\ud310", "synopsis": synopsis, "targetCountry": "Japan"})

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
        self.assertIn("번역 전 현지화 기준서", result["htmlReport"])

    def test_rank_countries_uses_genre_and_synopsis_evidence(self):
        data = load_trend_data()
        recs = rank_countries(data, genre="LitRPG", synopsis="\uc2dc\uc2a4\ud15c \uc2a4\ud0ac \ub358\uc804 \ub808\ubca8\uc5c5 \uc131\uc7a5")

        self.assertGreaterEqual(len(recs), 2)
        self.assertEqual(recs[0].country, "US/global English")
        self.assertGreater(recs[0].score, 0)
        self.assertTrue(recs[0].evidence)

    def test_api_guide_preserves_required_legacy_html_sections(self):
        result = api_server.guide({"legacyGuide": True, "targetCountry": "\ubbf8\uad6d", "genre": "\ud310\ud0c0\uc9c0"})

        self.assertIn("\uc81c\ubaa9/\uc2dc\ub189\uc2dc\uc2a4", result["htmlReport"])
        self.assertIn("\ubb38\ud654", result["htmlReport"])
        self.assertIn("\ud50c\ub7ab\ud3fc", result["htmlReport"])
        self.assertIn("modelPromptPayload", result)


if __name__ == "__main__":
    unittest.main()

