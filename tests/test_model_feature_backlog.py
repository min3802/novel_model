from __future__ import annotations

import os
import unittest

import api_server
from backend.services.translation_service import COUNTRY_TO_LOCALE
from backend.store import memory_store as store
from ko_locale_pipeline.consistency_checker import check_translation_consistency


COUNTRY_JAPAN = next(country for country, locale in COUNTRY_TO_LOCALE.items() if locale == "ko_ja")


def reset_api_state() -> None:
    store._works.clear()
    store._episodes.clear()
    store._translation_versions.clear()
    store._chat_messages.clear()
    store._cover_plans.clear()
    store._generated_assets.clear()
    store._localization_guides.clear()
    store._next_work_id = 1
    store._next_episode_id = 1
    store._next_translation_id = 1
    store._next_chat_id = 1
    store._next_cover_plan_id = 1
    store._next_asset_id = 1
    store._next_guide_id = 1


class ModelFeatureBacklogTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["WLIGHTER_MOCK_MODE"] = "true"
        reset_api_state()

    def _work_episode(self) -> tuple[dict, dict]:
        work = api_server.work_create(
            {
                "title": "\ube44 \uc624\ub294 \uace8\ubaa9",
                "genre": "\ud604\ub300 \ud310\ud0c0\uc9c0",
                "desc": "\ube44\ubc00\uc744 \uac00\uc9c4 \uc8fc\uc778\uacf5\uc758 \uc774\uc57c\uae30",
            }
        )
        episode = api_server.episode_create(
            work["id"],
            {
                "title": "1\ud654",
                "body": "\uae40\ucca0\uc218\ub294 \ube44 \ub0b4\ub9ac\ub294 \uace8\ubaa9\uc5d0\uc11c \ub0a1\uc740 \ubd80\uc801\uc744 \ubc1c\uacac\ud588\ub2e4.",
            },
        )
        return work, episode

    def test_translation_versions_are_saved_and_capped_at_three(self) -> None:
        work, episode = self._work_episode()

        versions = []
        for _ in range(4):
            result = api_server.translate(
                {
                    "workId": work["id"],
                    "episodeId": episode["id"],
                    "targetCountry": COUNTRY_JAPAN,
                    "sourceText": episode["body"],
                }
            )
            versions.append(result["translationVersion"])

        stored = api_server.translation_versions_list(work["id"], episode["id"], "ko_ja")

        self.assertEqual(len(stored), 3)
        self.assertEqual([row["version_no"] for row in stored], [2, 3, 4])
        self.assertEqual(versions[-1]["autoRemovedVersions"][0]["version_no"], 1)

    def test_consistency_checker_reports_terminology_mismatch(self) -> None:
        work, _episode = self._work_episode()
        source_text = "Kim Cheonsu stepped into the rainy street."
        memory = {
            "workId": work["id"],
            "title": work["title"],
            "terms": [
                {
                    "source": "Kim Cheonsu",
                    "target": "Kim Cheonsu-sama",
                    "locale": "ko_ja",
                    "status": "confirmed",
                }
            ],
        }
        result = check_translation_consistency(
            source_text=source_text,
            translated_text="He stepped into the rainy street.",
            locale="ko_ja",
            memory=memory,
        )

        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["issues"][0]["type"], "terminology_mismatch")
        self.assertEqual(result["issues"][0]["severity"], "HIGH")

    def test_chat_suggestion_can_be_applied_to_translation_version(self) -> None:
        work, episode = self._work_episode()
        result = api_server.translate(
            {
                "workId": work["id"],
                "episodeId": episode["id"],
                "targetCountry": COUNTRY_JAPAN,
                "sourceText": episode["body"],
            }
        )
        tid = result["translationVersion"]["id"]

        api_server.translation_chat_add(
            tid,
            {"role": "user", "content": "\ubb38\uc7a5\uc744 \ub354 \uc790\uc5f0\uc2a4\ub7fd\uac8c \ubc14\uafd4\uc918"},
        )
        proposed = "\uae40\ucca0\uc218\ub294 \ube57\uc18d \uace8\ubaa9\uc5d0\uc11c \uc624\ub798\ub41c \ubd80\uc801\uc744 \ubc1c\uacac\ud588\ub2e4."
        updated = api_server.apply_chat_suggestion(
            tid,
            {
                "proposedTranslation": proposed,
                "changeSummary": "\ubb38\uc7a5 \ud750\ub984\uc744 \uc790\uc5f0\uc2a4\ub7fd\uac8c \uc870\uc815",
            },
        )

        self.assertEqual(updated["finalTranslation"], proposed)
        self.assertEqual(len(api_server.translation_chat_list(tid)), 1)
        self.assertIn("appliedChatSuggestions", updated)

    def test_cover_plan_uses_selected_episodes_and_returns_concepts(self) -> None:
        work, first = self._work_episode()
        second = api_server.episode_create(
            work["id"],
            {
                "title": "2\ud654",
                "body": "\uae40\ucca0\uc218\ub294 \ubd80\uc801\uc758 \uc8fc\uc778\uc744 \ucc3e\uae30 \uc704\ud574 \uc624\ub798\ub41c \uc2dc\uc7a5\uc73c\ub85c \ud5a5\ud588\ub2e4.",
            },
        )

        plan = api_server.cover_plan(
            work["id"],
            {
                "episodeIds": [first["id"], second["id"]],
                "preferences": {
                    "mustInclude": ["\ube44 \ub0b4\ub9ac\ub294 \uace8\ubaa9"],
                    "tone": ["\ubbf8\uc2a4\ud130\ub9ac", "\uc11c\uc815\uc801"],
                    "extraPrompt": "\uc81c\ubaa9 \uacf5\uac04\uc744 \ub113\uac8c \ub0a8\uaca8\uc918",
                },
            },
        )

        self.assertEqual(plan["episodeIds"], [first["id"], second["id"]])
        self.assertEqual(len(plan["episodeSummaries"]), 2)
        self.assertEqual(len(plan["concepts"]), 3)
        self.assertEqual(plan["recommendedConceptId"], "commercial_thumbnail")
        self.assertIn("imagePrompt", plan["prompt"])


if __name__ == "__main__":
    unittest.main()
