from __future__ import annotations

import importlib
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ServerBackedRequirementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["WLIGHTER_MOCK_MODE"] = "true"

    def setUp(self) -> None:
        import backend.store.memory_store as memory_store
        import api_server

        importlib.reload(memory_store)
        self.api_server = importlib.reload(api_server)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.api_server.ApiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=10) as res:
                body = json.loads(res.read().decode("utf-8") or "{}")
                if "/episodes" in path and isinstance(body, dict):
                    item = body.get("item")
                    if isinstance(item, dict):
                        body.setdefault("episode", item)
                        body.setdefault("id", item.get("episode_id"))
                        body.setdefault("title", item.get("title"))
                        body.setdefault("body", item.get("original_text"))
                        body.setdefault("episodes", body.get("items"))
                return body
        except HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8") or "{}")
            raise AssertionError(f"{method} {path} failed: {exc.code} {body}") from exc

    def request_binary(self, method: str, path: str) -> tuple[bytes, dict[str, str]]:
        req = Request(f"{self.base_url}{path}", method=method)
        try:
            with urlopen(req, timeout=10) as res:
                headers = {key: value for key, value in res.headers.items()}
                return res.read(), headers
        except HTTPError as exc:
            body = exc.read().decode("utf-8") or ""
            raise AssertionError(f"{method} {path} failed: {exc.code} {body}") from exc

    def create_work(self) -> dict[str, Any]:
        result = self.request("POST", "/api/works", {"title": "Demo Work", "genre": "LitRPG"})
        item = dict(result.get("item") or result)
        if "id" not in item and "work_id" in item:
            item["id"] = item["work_id"]
        return item

    def create_guide_work(self) -> dict[str, Any]:
        import backend.store.memory_store as memory_store

        return memory_store.work_create({"title": "Demo Work", "genre": "LitRPG"})

    def test_localization_guides_are_server_backed_list_detail_delete(self) -> None:
        summary_before = self.request("GET", "/api/dashboard-summary")
        self.assertEqual(summary_before["guideCount"], 0)

        guide = self.request("POST", "/api/guide", {"targetCountry": "US", "genre": "LitRPG"})
        record = guide.get("guideRecord")
        self.assertIsInstance(record, dict)
        guide_id = record["id"]

        summary_after = self.request("GET", "/api/dashboard-summary")
        self.assertEqual(summary_after["guideCount"], 1)

        listing = self.request("GET", "/api/localization-guides")
        self.assertEqual([row["id"] for row in listing["guides"]], [guide_id])

        detail = self.request("GET", f"/api/localization-guides/{guide_id}")
        self.assertEqual(detail["guide"]["id"], guide_id)
        self.assertIn("guide", detail["guide"])

        deleted = self.request("DELETE", f"/api/localization-guides/{guide_id}")
        self.assertEqual(deleted, {"ok": True})
        self.assertEqual(self.request("GET", "/api/localization-guides")["guides"], [])
        self.assertEqual(self.request("GET", "/api/dashboard-summary")["guideCount"], 0)

    def test_localization_guide_pdf_download_is_generated_on_demand(self) -> None:
        work = self.create_guide_work()
        guide = self.request(
            "POST",
            "/api/guide",
            {"workId": work["id"], "title": work["title"], "targetCountry": "US", "genre": "LitRPG", "synopsis": "A hero enters a dungeon."},
        )
        record = guide.get("guideRecord")
        self.assertIsInstance(record, dict)
        guide_id = record["id"]

        pdf_bytes, headers = self.request_binary("GET", f"/api/localization-guides/{guide_id}/pdf")
        self.assertEqual(headers.get("Content-Type"), "application/pdf")
        self.assertIn(b"%PDF", pdf_bytes[:8])
        self.assertGreater(len(pdf_bytes), 1000)

    def test_localization_guides_enforce_per_work_limit_of_ten(self) -> None:
        work = self.create_guide_work()
        created_ids: list[int] = []

        for index in range(11):
            guide = self.request(
                "POST",
                "/api/guide",
                {
                    "workId": work["id"],
                    "title": work["title"],
                    "targetCountry": "US",
                    "genre": "LitRPG",
                    "synopsis": f"A hero enters dungeon floor {index + 1}.",
                },
            )
            record = guide.get("guideRecord")
            self.assertIsInstance(record, dict)
            created_ids.append(record["id"])

        self.assertIn("storageNotice", guide)
        self.assertEqual(guide["storageNotice"]["guideLimit"], 10)
        self.assertEqual(len(guide["storageNotice"]["removedGuideIds"]), 1)

        listing = self.request("GET", f"/api/localization-guides?workId={work['id']}")
        listed_ids = [row["id"] for row in listing["guides"]]
        self.assertEqual(len(listed_ids), 10)
        self.assertNotIn(created_ids[0], listed_ids)
        self.assertEqual(listed_ids, sorted(created_ids[1:], reverse=True))

    def test_synopsis_only_returns_recommendation_without_persisting(self) -> None:
        summary_before = self.request("GET", "/api/dashboard-summary")
        self.assertEqual(summary_before["guideCount"], 0)

        result = self.request("POST", "/api/guide", {"genre": "LitRPG", "synopsis": "A reborn hero enters a dungeon and grows stronger."})
        self.assertTrue(result["requiresSelection"])
        self.assertEqual(result["mode"], "synopsis_country_recommendation")
        self.assertNotIn("guideRecord", result)
        self.assertEqual(self.request("GET", "/api/dashboard-summary")["guideCount"], 0)

    def test_generated_assets_are_server_backed_list_detail_delete(self) -> None:
        work = self.create_guide_work()
        result = self.request(
            "POST",
            "/api/generate-cover-image",
            {"workId": work["id"], "workTitle": "Demo Work", "targetCountry": "US", "genre": "LitRPG",
             "episodes": ["주인공이 던전에서 각성하는 장면으로 1화가 시작된다."]},
        )
        self.assertEqual(result["type"], "mock_image")
        record = result.get("assetRecord")
        self.assertIsInstance(record, dict)
        asset_id = record["id"]

        listing = self.request("GET", f"/api/generated-assets?kind=cover&workId={work['id']}")
        self.assertEqual([row["id"] for row in listing["assets"]], [asset_id])

        detail = self.request("GET", f"/api/generated-assets/{asset_id}")
        self.assertEqual(detail["asset"]["id"], asset_id)
        self.assertEqual(detail["asset"]["kind"], "cover")
        self.assertEqual(detail["asset"]["work_id"], work["id"])

        deleted = self.request("DELETE", f"/api/generated-assets/{asset_id}")
        self.assertEqual(deleted, {"ok": True})
        self.assertEqual(self.request("GET", "/api/generated-assets?kind=cover")["assets"], [])

    def test_episode_update_and_delete_are_server_backed(self) -> None:
        work = self.create_work()
        episode = self.request(
            "POST",
            f"/api/works/{work['id']}/episodes",
            {"title": "Episode 1", "originalText": "Original source body"},
        )
        episode_item = episode["item"]
        updated = self.request(
            "PUT",
            f"/api/works/{work['id']}/episodes/{episode_item['episode_id']}",
            {"title": "Episode 1 revised", "originalText": "Updated source body"},
        )
        self.assertEqual(updated["item"]["title"], "Episode 1 revised")
        self.assertEqual(updated["item"]["original_text"], "Updated source body")

        detail = self.request("GET", f"/api/works/{work['id']}/episodes/{episode_item['episode_id']}")
        self.assertEqual(detail["item"]["title"], "Episode 1 revised")

        deleted = self.request("DELETE", f"/api/works/{work['id']}/episodes/{episode_item['episode_id']}")
        self.assertTrue(deleted["ok"])
        archived_items = self.request("GET", f"/api/works/{work['id']}/episodes")["items"]
        self.assertEqual(len(archived_items), 1)
        self.assertEqual(archived_items[0]["episode_id"], episode_item["episode_id"])
        self.assertEqual(archived_items[0]["status"], "archived")


if __name__ == "__main__":
    unittest.main()
