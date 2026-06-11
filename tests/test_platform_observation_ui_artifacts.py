from __future__ import annotations

import json
import unittest
from pathlib import Path


PROCESSED = Path("data/localization_guide/platform_observation/processed")


class PlatformObservationUiArtifactsTest(unittest.TestCase):
    def _load(self, name: str):
        return json.loads((PROCESSED / name).read_text(encoding="utf-8"))

    def test_ui_projection_artifacts_exist_with_card_ready_fields(self) -> None:
        required = [
            "raw_records_normalized.json",
            "label_dictionary.json",
            "market_tag_snapshot.json",
            "platform_tag_profiles.json",
            "rank_band_profiles.json",
            "cooccurrence_patterns.json",
        ]
        for name in required:
            self.assertTrue((PROCESSED / name).exists(), name)

        dictionary = self._load("label_dictionary.json")
        label = next(item for item in dictionary["labels"] if item["label_ko"] == "이세계 전생")
        self.assertEqual(label["canonical_label_id"], "isekai_reincarnation")
        self.assertEqual(label["category"], "plot_device")
        self.assertIn("異世界転生", label["raw_variants"])

        snapshots = self._load("market_tag_snapshot.json")
        japan = next(item for item in snapshots if item["market"] == "Japan")
        isekai = next(item for item in japan["labels"] if item["label_ko"] == "이세계 전생")
        self.assertIn("platform_coverage", isekai)
        self.assertIn("rank_band_distribution", isekai)
        self.assertIn("weighted_score", isekai)

        profiles = self._load("platform_tag_profiles.json")
        japan_profile = next(item for item in profiles if item["market"] == "Japan")
        self.assertTrue(japan_profile["platform_profiles"])
        self.assertIn("summary_sentence", japan_profile["platform_profiles"][0])

        rank_profiles = self._load("rank_band_profiles.json")
        japan_bands = next(item for item in rank_profiles if item["market"] == "Japan")["rank_bands"]
        self.assertTrue(any(band["rank_band"] == "top_10" for band in japan_bands))

        pairs = self._load("cooccurrence_patterns.json")
        japan_pairs = next(item for item in pairs if item["market"] == "Japan")["pairs"]
        self.assertTrue(japan_pairs)
        self.assertIn("jaccard", japan_pairs[0])
        self.assertIn("lift", japan_pairs[0])
        self.assertNotIn("와 ", japan_pairs[0]["display_sentence"])
        self.assertNotIn("는 같은", japan_pairs[0]["display_sentence"])

    def test_normalized_records_include_rank_band_and_metric_keys(self) -> None:
        rows = self._load("raw_records_normalized.json")
        row = rows[0]
        self.assertIn("rank_band", row)
        self.assertIn("labels_raw", row)
        self.assertIn("synopsis_present", row)
        self.assertIn("available_metric_keys", row)


if __name__ == "__main__":
    unittest.main()
