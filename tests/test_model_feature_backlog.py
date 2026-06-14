from __future__ import annotations

import os
import unittest

import api_server
from backend.services.translation_service import COUNTRY_TO_LOCALE
from backend.store import memory_store as store
from app.translation.text_processing.consistency_checker import check_translation_consistency


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
                "title": '비 오는 골목',
                "genre": '현대 판타지',
                "desc": '비밀을 가진 주인공의 이야기',
            }
        )
        episode = api_server.episode_create(
            work["id"],
            {
                "title": '1화',
                "body": '김철수는 비 내리는 골목에서 낡은 부적을 발견했다.',
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
            {"role": "user", "content": '문장을 더 자연스럽게 바꿔줘'},
        )
        proposed = '김철수는 빗속 골목에서 오래된 부적을 발견했다.'
        updated = api_server.apply_chat_suggestion(
            tid,
            {
                "proposedTranslation": proposed,
                "changeSummary": '문장 흐름을 자연스럽게 조정',
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
                "title": '2화',
                "body": '김철수는 부적의 주인을 찾기 위해 오래된 시장으로 향했다.',
            },
        )

        plan = api_server.cover_plan(
            work["id"],
            {
                "episodeIds": [first["id"], second["id"]],
                "preferences": {
                    "mustInclude": ['비 내리는 골목'],
                    "tone": ['미스터리', '서정적'],
                    "extraPrompt": '제목 공간을 넓게 남겨줘',
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
