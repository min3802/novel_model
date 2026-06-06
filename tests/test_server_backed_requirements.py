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
                return json.loads(res.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8") or "{}")
            raise AssertionError(f"{method} {path} failed: {exc.code} {body}") from exc

    def create_work(self) -> dict[str, Any]:
        return self.request("POST", "/api/works", {"title": "Demo Work", "genre": "LitRPG"})

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

    def test_generated_assets_are_server_backed_list_detail_delete(self) -> None:
        work = self.create_work()
        result = self.request(
            "POST",
            "/api/generate-cover-image",
            {"workId": work["id"], "workTitle": "Demo Work", "targetCountry": "US", "genre": "LitRPG"},
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
            {"title": "Episode 1", "body": "Original source body"},
        )

        updated = self.request(
            "PUT",
            f"/api/works/{work['id']}/episodes/{episode['id']}",
            {"title": "Episode 1 revised", "body": "Updated source body"},
        )
        self.assertEqual(updated["title"], "Episode 1 revised")
        self.assertEqual(updated["body"], "Updated source body")

        detail = self.request("GET", f"/api/works/{work['id']}/episodes/{episode['id']}")
        self.assertEqual(detail["episode"]["title"], "Episode 1 revised")

        deleted = self.request("DELETE", f"/api/works/{work['id']}/episodes/{episode['id']}")
        self.assertEqual(deleted, {"ok": True})
        self.assertEqual(self.request("GET", f"/api/works/{work['id']}/episodes")["episodes"], [])


if __name__ == "__main__":
    unittest.main()
