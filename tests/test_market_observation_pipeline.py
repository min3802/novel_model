import unittest
from unittest.mock import Mock

from scripts.platform_trends.analysis import build_rag, build_summary, legacy_dataset
from scripts.platform_trends.collectors.royalroad import collect as collect_royalroad
from scripts.platform_trends.schema import MarketRawRecord, MarketTrendTarget


class FakeResponse:
    def __init__(self, text=""):
        self.text = text
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        return None


class MarketObservationPipelineTests(unittest.TestCase):
    def test_royalroad_collector_emits_minimal_market_schema(self):
        html = """
        <div class="fiction-list-item row">
          <h2 class="fiction-title"><a href="/fiction/1/test-title">Test Title</a></h2>
          <span class="label bg-blue-hoki">Original</span><span class="label bg-blue-hoki">ONGOING</span>
          <a class="fiction-tag">Progression</a><a class="fiction-tag">Magic</a>
          <div class="stats">
            <span>1,234 Followers</span><span>456 Pages</span><span>78,900 Views</span><span>12 Chapters</span>
            <div aria-label="Rating: 4.25 out of 5"></div>
          </div>
          <div id="description-1"><p>Public synopsis only.</p></div>
        </div>
        """
        session = Mock()
        session.get.return_value = FakeResponse(text=html)
        target = MarketTrendTarget("US", "English", "en", "Royal Road", "weekly_popular", "https://example.test", 1, "english")

        rows = collect_royalroad(target, session=session)
        row = rows[0].to_dict()

        self.assertEqual(set(row), {"market", "language_market", "raw_language", "platform", "signal_type", "rank", "title", "labels", "synopsis", "public_metrics"})
        self.assertEqual(row["signal_type"], "weekly_popular")
        self.assertEqual(row["labels"], ["Original", "ONGOING", "Progression", "Magic"])
        self.assertEqual(row["public_metrics"]["views"], 78900)
        self.assertNotIn("source_url", row)
        self.assertNotIn("authors", row)

    def test_summary_and_rag_use_aggregate_market_observations_only(self):
        payload = {
            "market": "US",
            "language_market": "English",
            "raw_language": "en",
            "platform": "Royal Road",
            "signal_type": "weekly_popular",
            "target_limit": 100,
            "records": [
                MarketRawRecord("US", "English", "en", "Royal Road", "weekly_popular", 1, "A", ["Fantasy", "LitRPG"], "A system skill dungeon story.", {"views": 10}).to_dict(),
                MarketRawRecord("US", "English", "en", "Royal Road", "weekly_popular", 2, "B", ["Fantasy"], "Another level up quest.", {}).to_dict(),
            ],
        }

        summary = build_summary([payload])
        rag = build_rag(summary)

        item = summary["summaries"][0]
        self.assertEqual(item["sample_size"], 2)
        self.assertEqual(item["top_labels"][0], {"label": "Fantasy", "count": 2})
        self.assertTrue(any(row["motif"] == "성장/레벨업/시스템" for row in item["motif_distribution"]))
        self.assertEqual(len(rag["documents"]), 1)
        self.assertIn("개별 작품 추천", rag["documents"][0]["context_text"])
        self.assertNotIn("source_url", rag["documents"][0]["metadata"])

    def test_legacy_dataset_keeps_existing_guide_shape_without_urls(self):
        payload = {
            "market": "Japan",
            "language_market": "Japanese",
            "raw_language": "ja",
            "platform": "Syosetu",
            "signal_type": "weekly_ranking",
            "target_limit": 100,
            "records": [MarketRawRecord("Japan", "Japanese", "ja", "Syosetu", "weekly_ranking", 1, "A", ["異世界"], "公開あらすじ", {"weekly_points": 1}).to_dict()],
        }
        summary = build_summary([payload])
        rag = build_rag(summary)
        legacy = legacy_dataset([payload], summary, rag)

        rows = legacy["collections"]["syosetu_weekly_ranking"]
        self.assertEqual(rows[0]["country"], "Japan")
        self.assertEqual(rows[0]["collection"], "weekly_ranking")
        self.assertNotIn("source_url", rows[0])
        self.assertIn("market_observation_summary", legacy)


if __name__ == "__main__":
    unittest.main()
