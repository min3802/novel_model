
import unittest

from backend.store import memory_store as store


class EpisodeAndArtifactManagementTests(unittest.TestCase):
    def setUp(self):
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

    def test_episode_update_and_delete_cascades_translation_chat(self):
        work = store.work_create({"title": "Story", "genre": "fantasy"})
        episode = store.episode_create(work["id"], {"title": "Ep 1", "body": "?????."})
        updated = store.episode_update(work["id"], episode["id"], {"title": "Ep 1 revised", "body": "?? ?????."})
        self.assertEqual(updated["title"], "Ep 1 revised")
        version = store.save_translation_version(
            work_id=work["id"],
            episode_id=episode["id"],
            country="??",
            locale="ko_ja",
            source_text=updated["body"],
            final_translation="translated",
            review_summary="summary",
            workflow={},
            memory=None,
        )
        store.translation_chat_add(version["id"], {"role": "user", "content": "fix"})
        self.assertEqual(len(store.translation_chat_list(version["id"])), 1)
        store.episode_delete(work["id"], episode["id"])
        self.assertEqual(store.episodes_list(work["id"]), [])
        self.assertEqual(store.translation_versions_list(work["id"], episode["id"]), [])
        with self.assertRaises(ValueError):
            store.translation_chat_list(version["id"])

    def test_generated_assets_and_guides_are_server_managed(self):
        work = store.work_create({"title": "Story", "genre": "fantasy"})
        cover = store.save_generated_asset("cover", {"workId": work["id"], "prompt": "cover"}, {"type": "mock_image"})
        relation = store.save_generated_asset("relation", {"workId": work["id"], "prompt": "relation"}, {"type": "mock_image"})
        self.assertEqual([row["id"] for row in store.generated_assets_list(kind="cover", work_id=work["id"])], [cover["id"]])
        store.generated_asset_delete(relation["id"])
        self.assertEqual(len(store.generated_assets_list(kind="relation", work_id=work["id"])), 0)

        guide = store.save_localization_guide({"workId": work["id"]}, {"title": "Guide", "country": "??", "genre": "fantasy"})
        self.assertEqual(store.localization_guide_get(guide["id"])["title"], "Guide")
        self.assertEqual(len(store.localization_guides_list(work_id=work["id"])), 1)
        store.localization_guide_delete(guide["id"])
        self.assertEqual(store.localization_guides_list(work_id=work["id"]), [])

    def test_localization_guides_are_limited_per_work(self):
        work = store.work_create({"title": "Story", "genre": "fantasy"})
        created = []
        for index in range(6):
            created.append(
                store.save_localization_guide(
                    {"workId": work["id"]},
                    {"title": f"Guide {index}", "country": "US", "genre": "fantasy", "guide_html": f"<p>{index}</p>"},
                )
            )

        guides = store.localization_guides_list(work_id=work["id"])
        self.assertEqual(len(guides), 5)
        self.assertEqual([row["guide"]["title"] for row in guides], [f"Guide {index}" for index in range(5, 0, -1)])
        self.assertIn("storage_notice", created[-1])
        self.assertEqual(created[-1]["storage_notice"]["guideLimit"], 5)


if __name__ == "__main__":
    unittest.main()
