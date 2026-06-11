
import unittest

from app.guide.platform_trend_guide import (
    build_collection_profiles,
    build_country_profiles,
    build_prompt_payload,
    render_markdown,
)


def sample_data():
    return {
        "generated_at": "2026-06-05T00:00:00Z",
        "collections": {
            "rr": [
                {
                    "country": "US/global English",
                    "platform": "Royal Road",
                    "collection": "Trending",
                    "ranking_basis": "platform_trending_order",
                    "rank": 1,
                    "title": "System Adventurer",
                    "genres": ["Original"],
                    "genre": "Original",
                    "tags": ["LitRPG", "Progression", "Adventure", "Male Lead"],
                    "status": "ONGOING",
                    "synopsis": "A hero gains skills and levels through dungeon trials.",
                    "public_metrics": {"views": 100, "followers": 10},
                    "source_url": "https://example.test/rr",
                }
            ],
            "tapas": [
                {
                    "country": "US/global English",
                    "platform": "Tapas",
                    "collection": "Novels popular menu subtab 24",
                    "ranking_basis": "platform_popular_novel_order",
                    "rank": 1,
                    "title": "Duke Contract",
                    "genres": ["Romance Fantasy"],
                    "genre": "Romance Fantasy",
                    "tags": [],
                    "status": "COMPLETED",
                    "synopsis": "A noble contract romance creates emotional stakes.",
                    "public_metrics": {"views": 200, "likes": 20},
                    "source_url": "https://example.test/tapas",
                }
            ],
        },
        "rag_documents": [
            {
                "id": "doc-1",
                "embedding_text": "Royal Road LitRPG",
                "context_text": "Rank 1 System Adventurer",
                "metadata": {"platform": "Royal Road", "collection": "Trending", "rank": 1},
            }
        ],
    }


class PlatformTrendGuideTests(unittest.TestCase):
    def test_collection_profiles_summarize_genres_tags_and_metrics(self):
        profiles = build_collection_profiles(sample_data())
        rr = next(profile for profile in profiles if profile.platform == "Royal Road")

        self.assertEqual(rr.item_count, 1)
        self.assertIn(("Original", 1), rr.top_genres)
        self.assertIn(("LitRPG", 1), rr.top_tags)
        self.assertEqual(rr.metric_coverage["views"], 1)

    def test_country_profile_derives_localization_guidance(self):
        countries = build_country_profiles(build_collection_profiles(sample_data()))
        us = countries[0]
        joined = " ".join(us.localization_signals + us.adaptation_guidance)

        self.assertIn("System/progression", joined)
        self.assertIn("relationship", joined.lower())
        self.assertIn("platform-specific", " ".join(us.caution_points))

    def test_markdown_contains_required_sections(self):
        markdown = render_markdown(sample_data())

        self.assertIn("# Platform Trend Localization Guide Draft", markdown)
        self.assertIn("## Method", markdown)
        self.assertIn("## Country and Platform Notes", markdown)
        self.assertIn("Royal Road - Trending", markdown)

    def test_prompt_payload_limits_claims_and_includes_evidence_sample(self):
        payload = build_prompt_payload(sample_data())

        self.assertEqual(payload["role"], "localization_guide_generator")
        self.assertIn("Do not claim national readership certainty", payload["safety_policy"]["claim_limit"])
        self.assertIn("Royal Road::Trending", payload["evidence_documents_sample"])
        self.assertIn("adaptation_checklist", payload["required_output_sections"])

    def test_japanese_market_tags_derive_isekai_and_romance_signals(self):
        data = {
            "generated_at": "2026-06-05T00:00:00Z",
            "collections": {
                "syosetu": [
                    {
                        "country": "Japan",
                        "platform": "Shosetsuka ni Naro / Yomou",
                        "collection": "Weekly ranking",
                        "ranking_basis": "weekly_ranking_order",
                        "rank": 1,
                        "title": "JP sample",
                        "genres": ["\u7570\u4e16\u754c\u3014\u604b\u611b\u3015"],
                        "genre": "\u7570\u4e16\u754c\u3014\u604b\u611b\u3015",
                        "tags": [
                            "\u7570\u4e16\u754c\u8ee2\u751f",
                            "\u5973\u4e3b\u4eba\u516c",
                            "\u6b8b\u9177\u306a\u63cf\u5199\u3042\u308a",
                        ],
                        "status": "\u9023\u8f09\u4e2d",
                        "synopsis": "sample",
                        "public_metrics": {"weekly_points": 1000},
                        "source_url": "https://example.test/jp",
                    }
                ]
            },
            "rag_documents": [],
        }

        country = build_country_profiles(build_collection_profiles(data))[0]
        signals = " ".join(country.localization_signals)

        self.assertIn("Isekai/reincarnation", signals)
        self.assertIn("Relationship-forward", signals)
        self.assertIn("Content-intensity", signals)


if __name__ == "__main__":
    unittest.main()

