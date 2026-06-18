from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.services.content_service import get_content_repository
from backend.services.glossary_service import get_glossary_repository

_ENV_IMPORT_BACKUP = os.environ.copy()
import scripts.run_webnovel_batch_eval as batch_eval
from scripts.run_webnovel_batch_eval import run_batch_eval
os.environ.clear()
os.environ.update(_ENV_IMPORT_BACKUP)


def _write_episode(path: Path, title: str, body: str) -> None:
    path.write_text(f"{title}\n{body}\n", encoding="utf-8")


class WebNovelBatchEvalTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = os.environ.copy()

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)
        get_content_repository(refresh=True)
        get_glossary_repository(refresh=True)

    def test_dry_run_writes_plan_without_api_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            candidate_text = "리아는 북부대공 카이든 에른스트를 보았다. 그녀는 그를 검은 늑대라고 불렀다."
            _write_episode(input_dir / "001.txt", "Series Title", f"Episode 1\n{candidate_text}")
            _write_episode(input_dir / "002.txt", "Series Title", "Episode 2\n" + "가" * 8001)
            _write_episode(input_dir / "003.txt", "Series Title", f"Episode 3\n{candidate_text}")

            report = run_batch_eval(
                input_dir=input_dir,
                report_dir=report_dir,
                dry_run=True,
                save_results=True,
                capture_glossary_candidates=True,
                limit=3,
            )

            summary_path = report_dir / "latest_summary.json"
            md_path = report_dir / "latest_summary.md"
            self.assertTrue(summary_path.exists())
            self.assertTrue(md_path.exists())
            self.assertEqual(report["dry_run"], True)
            self.assertEqual(report["total_episodes"], 3)
            self.assertEqual(report["succeeded"], 0)
            self.assertEqual(report["failed"], 1)
            self.assertEqual(report["blocked"], 0)
            self.assertTrue(all(row["status"] in {"planned", "validation_error"} for row in report["per_episode"]))
            self.assertEqual(len(list((report_dir / "raw").glob("*.json"))), 0)

    def test_episode_nos_selects_only_requested_episode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            _write_episode(input_dir / "016.txt", "Series Title", "Episode 16\n" + "\ub2e4\uc74c \ubb38\uc7a5")
            _write_episode(input_dir / "017.txt", "Series Title", "Episode 17\n" + "\uc774 \ud68c\ucc28\ub9cc \uc2e4\ud589")
            _write_episode(input_dir / "018.txt", "Series Title", "Episode 18\n" + "\ub2e4\ub978 \ubb38\uc7a5")

            report = run_batch_eval(
                input_dir=input_dir,
                report_dir=report_dir,
                dry_run=True,
                episode_nos=[17],
            )

            self.assertEqual(report["episode_nos"], [17])
            self.assertEqual(report["total_episodes"], 1)
            self.assertEqual([row["episode_no"] for row in report["per_episode"]], [17])
            self.assertEqual(report["per_episode"][0]["status"], "planned")
            self.assertEqual(report["effective_limit"], 1)

    def test_work_id_reuses_existing_work_and_seeds_approved_glossary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            _write_episode(input_dir / "001.txt", "Series Title", "Episode 1\n낙원동에서 철수를 만났다.")
            os.environ["WLIGHTER_MOCK_MODE"] = "true"
            calls: list[tuple[str, str, dict | None]] = []

            def fake_request_json(method, base_url, path, *, json_body=None, timeout=60):
                calls.append((method, path, json_body))
                if path in {"/api/content/repository-status", "/api/glossary/repository-status"}:
                    return {"_http_status": 200, "ok": True, "backend": "fake"}
                if method == "GET" and path == "/api/works/42":
                    return {"_http_status": 200, "ok": True, "item": {"work_id": 42}}
                if method == "POST" and path == "/api/works":
                    raise AssertionError("must not create a work when --work-id is provided")
                if method == "POST" and path == "/api/works/42/glossary/entries":
                    return {"_http_status": 200, "ok": True, "entry": {"id": len([c for c in calls if c[1].endswith('/glossary/entries')])}}
                if method == "GET" and path.startswith("/api/works/42/episodes?"):
                    return {"_http_status": 200, "ok": True, "items": []}
                if method == "POST" and path == "/api/works/42/episodes":
                    return {"_http_status": 201, "ok": True, "item": {"episode_id": 11, "episode_no": 1}}
                if method == "POST" and path == "/api/translate":
                    return {"_http_status": 200, "ok": True, "deliveryStatus": "deliverable", "finalTranslation": "ナクウォンドンでチョルスに会った。", "metadata": {}, "internal": {"glossaryCandidateCapture": {"enabled": False}}}
                if method == "GET" and path.startswith("/api/works/42/glossary/candidates?"):
                    return {"_http_status": 200, "ok": True, "items": []}
                raise AssertionError(f"unexpected request {method} {path}")

            with patch.object(batch_eval, "_request_json", side_effect=fake_request_json):
                report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    base_url="http://fake",
                    work_id=42,
                    seed_approved_glossary=True,
                    limit=1,
                )

            glossary_posts = [body for method, path, body in calls if method == "POST" and path == "/api/works/42/glossary/entries"]
            self.assertEqual(report["work_id"], 42)
            self.assertEqual(report["workIdentitySource"], "cli_work_id")
            self.assertEqual(report["seedApprovedGlossary"]["seededCount"], len(batch_eval.SEED_APPROVED_GLOSSARY))
            self.assertEqual(len(glossary_posts), len(batch_eval.SEED_APPROVED_GLOSSARY))
            self.assertTrue(all(body["status"] == "approved" and body["priority"] == "hard" for body in glossary_posts))
            self.assertFalse(any(method == "POST" and path == "/api/works" for method, path, _body in calls))

    def test_work_key_reuses_registry_work_across_report_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            registry_path = tmp_path / "work_identity_registry.json"
            input_dir.mkdir()
            _write_episode(input_dir / "001.txt", "Series Title", "Episode 1\n차민혁이 말했다.")
            os.environ["WLIGHTER_MOCK_MODE"] = "true"
            created = {"count": 0}

            def fake_request_json(method, base_url, path, *, json_body=None, timeout=60):
                if path in {"/api/content/repository-status", "/api/glossary/repository-status"}:
                    return {"_http_status": 200, "ok": True, "backend": "fake"}
                if method == "GET" and path == "/api/works/7":
                    return {"_http_status": 200, "ok": True, "item": {"work_id": 7}}
                if method == "POST" and path == "/api/works":
                    created["count"] += 1
                    return {"_http_status": 201, "ok": True, "item": {"work_id": 7}}
                if method == "GET" and path.startswith("/api/works/7/episodes?"):
                    return {"_http_status": 200, "ok": True, "items": []}
                if method == "POST" and path == "/api/works/7/episodes":
                    return {"_http_status": 201, "ok": True, "item": {"episode_id": 17, "episode_no": 1}}
                if method == "POST" and path == "/api/translate":
                    return {"_http_status": 200, "ok": True, "deliveryStatus": "deliverable", "finalTranslation": "チャ・ミンヒョクが言った。", "metadata": {}, "internal": {"glossaryCandidateCapture": {"enabled": False}}}
                if method == "GET" and path.startswith("/api/works/7/glossary/candidates?"):
                    return {"_http_status": 200, "ok": True, "items": []}
                raise AssertionError(f"unexpected request {method} {path}")

            with patch.object(batch_eval, "_request_json", side_effect=fake_request_json):
                first = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=tmp_path / "report-a",
                    base_url="http://fake",
                    work_key="batch_eval_novel_ko_ja",
                    work_identity_registry=registry_path,
                    limit=1,
                )
                second = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=tmp_path / "report-b",
                    base_url="http://fake",
                    work_key="batch_eval_novel_ko_ja",
                    work_identity_registry=registry_path,
                    limit=1,
                )

            self.assertEqual(first["work_id"], 7)
            self.assertEqual(second["work_id"], 7)
            self.assertEqual(first["workIdentitySource"], "work_key_registry_created")
            self.assertEqual(second["workIdentitySource"], "work_key_registry_reuse")
            self.assertTrue(registry_path.exists())
            self.assertEqual(created["count"], 1)

    def test_debug_capture_payload_is_opt_in_and_report_scoped(self) -> None:
        base_kwargs = {
            "source_text": "\uc9e7\uc740 \uc6d0\ubb38",
            "target_country": "JP",
            "work_id": 1,
            "episode_id": 2,
            "save_results": True,
            "capture_glossary_candidates": True,
            "genre": "fantasy",
            "pen_name": "tester",
            "title": "Episode",
        }

        disabled = batch_eval._build_translation_payload(**base_kwargs)
        enabled = batch_eval._build_translation_payload(
            **base_kwargs,
            debug_capture_model_outputs=True,
            debug_artifact_dir=Path("reports") / "batch_eval" / "debug" / "episode_017",
        )

        self.assertNotIn("debugCaptureModelOutputs", disabled)
        self.assertNotIn("canonicalWorkKey", disabled)
        self.assertTrue(enabled["debugCaptureModelOutputs"])
        self.assertNotIn("canonicalWorkKey", enabled)
        self.assertIn("reports", enabled["debugArtifactDir"])
        self.assertIn("episode_017", enabled["debugArtifactDir"])

    def test_mock_run_continues_after_validation_error_and_supports_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            candidate_text = "리아는 북부대공 카이든 에른스트를 보았다. 그녀는 그를 검은 늑대라고 불렀다."
            _write_episode(input_dir / "001.txt", "Series Title", f"Episode 1\n{candidate_text}")
            _write_episode(input_dir / "002.txt", "Series Title", "Episode 2\n" + "가" * 8001)
            _write_episode(input_dir / "003.txt", "Series Title", f"Episode 3\n{candidate_text}")

            os.environ["CONTENT_STORE_BACKEND"] = "memory"
            os.environ["GLOSSARY_STORE_BACKEND"] = "memory"
            os.environ["WLIGHTER_MOCK_MODE"] = "true"

            report = run_batch_eval(
                input_dir=input_dir,
                report_dir=report_dir,
                save_results=True,
                capture_glossary_candidates=True,
                skip_existing=True,
                limit=3,
            )

            self.assertFalse(report["dry_run"])
            self.assertEqual(report["total_episodes"], 3)
            self.assertEqual(report["failed"], 1)
            self.assertGreaterEqual(report["succeeded"], 2)
            self.assertEqual(report["deliverable_count"] + report["qa_warning_count"], report["succeeded"])
            self.assertGreaterEqual(report["total_pending_glossary_candidates"], 0)

            per_episode = {row["episode_no"]: row for row in report["per_episode"]}
            self.assertEqual(per_episode[2]["status"], "validation_error")
            self.assertEqual(per_episode[2]["errorCode"], "text_too_long")
            self.assertEqual(per_episode[1]["status"], "deliverable")
            self.assertIsInstance(per_episode[1]["saved_translation_id"], int)
            self.assertGreaterEqual(per_episode[1]["glossary_candidate_capture"]["savedCount"], 0)
            self.assertTrue((report_dir / "translations" / "001.txt").exists())
            self.assertTrue((report_dir / "raw" / "001.json").exists())
            self.assertTrue((report_dir / "raw" / "002.json").exists())

            first_work_id = report["work_id"]
            second_report = run_batch_eval(
                input_dir=input_dir,
                report_dir=report_dir,
                save_results=True,
                capture_glossary_candidates=True,
                skip_existing=True,
                limit=3,
            )
            self.assertEqual(second_report["work_id"], first_work_id)
            self.assertGreaterEqual(second_report["skipped_existing"], 2)

    def test_reuses_existing_episode_but_reruns_translation_without_skip_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            candidate_text = "박 팀장이 문밖에서 재촉하고 있었다. 그는 마른세수를 했다."
            _write_episode(input_dir / "001.txt", "Series Title", f"Episode 1\n{candidate_text}")

            os.environ["CONTENT_STORE_BACKEND"] = "memory"
            os.environ["GLOSSARY_STORE_BACKEND"] = "memory"
            os.environ["WLIGHTER_MOCK_MODE"] = "true"

            with batch_eval._started_server(mock_mode=True) as base_url:
                first_report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=True,
                    limit=1,
                    base_url=base_url,
                )
                first_row = first_report["per_episode"][0]
                first_episode_id = first_row["episode_id"]
                first_translation_id = first_row["saved_translation_id"]

                second_report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=True,
                    skip_existing=False,
                    limit=1,
                    base_url=base_url,
                )
                second_row = second_report["per_episode"][0]

                self.assertEqual(second_report["work_id"], first_report["work_id"])
                self.assertEqual(second_row["episode_id"], first_episode_id)
                self.assertEqual(second_row["episode_reuse_status"], "reused")
                self.assertEqual(second_row["episode_warnings"], [])
                self.assertIsInstance(second_row["saved_translation_id"], int)
                self.assertNotEqual(second_row["saved_translation_id"], first_translation_id)
                self.assertEqual(second_report["skipped_existing"], 0)
                self.assertEqual(second_report["episode_reused"], 1)

                third_report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=True,
                    skip_existing=True,
                    limit=1,
                    base_url=base_url,
                )
                third_row = third_report["per_episode"][0]

                self.assertEqual(third_report["work_id"], first_report["work_id"])
                self.assertEqual(third_report["skipped_existing"], 1)
                self.assertEqual(third_row["status"], "skipped_existing")
                self.assertEqual(third_row["episode_id"], first_episode_id)
                self.assertEqual(third_row["saved_translation_id"], second_row["saved_translation_id"])

    def test_reused_episode_source_mismatch_is_warning_not_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            _write_episode(input_dir / "001.txt", "Series Title", "첫 번째 원문")

            os.environ["CONTENT_STORE_BACKEND"] = "memory"
            os.environ["GLOSSARY_STORE_BACKEND"] = "memory"
            os.environ["WLIGHTER_MOCK_MODE"] = "true"

            with batch_eval._started_server(mock_mode=True) as base_url:
                first_report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=True,
                    limit=1,
                    base_url=base_url,
                )
                _write_episode(input_dir / "001.txt", "Changed Title", "두 번째 원문")

                second_report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=True,
                    limit=1,
                    base_url=base_url,
                )
                row = second_report["per_episode"][0]

                self.assertEqual(row["episode_id"], first_report["per_episode"][0]["episode_id"])
                self.assertEqual(row["episode_reuse_status"], "reused")
                self.assertIn("source_text_hash_mismatch", row["episode_warnings"])
                self.assertIn("title_mismatch", row["episode_warnings"])
                self.assertEqual(second_report["source_mismatch_warnings"], 1)
                self.assertEqual(second_report["failed"], 0)

                updated_report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=True,
                    limit=1,
                    base_url=base_url,
                    update_existing_episodes=True,
                )
                updated_row = updated_report["per_episode"][0]
                self.assertIn("existing_episode_updated", updated_row["episode_warnings"])
                self.assertEqual(updated_report["episode_updated"], 1)

    def test_blocked_integrity_without_saved_translation_is_not_persistence_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            _write_episode(input_dir / "001.txt", "Series Title", "Episode 1\n" + "\ud575\uc2ec \uade0\uc5f4\ubb38")
            os.environ["WLIGHTER_MOCK_MODE"] = "true"

            def fake_request_json(method, base_url, path, *, json_body=None, timeout=60):
                if path in {"/api/content/repository-status", "/api/glossary/repository-status"}:
                    return {"_http_status": 200, "ok": True, "backend": "fake"}
                if method == "POST" and path == "/api/works":
                    return {"_http_status": 201, "ok": True, "item": {"work_id": 1}}
                if method == "GET" and path.startswith("/api/works/1/episodes?"):
                    return {"_http_status": 200, "ok": True, "items": []}
                if method == "POST" and path == "/api/works/1/episodes":
                    return {"_http_status": 201, "ok": True, "item": {"episode_id": 11, "episode_no": 1}}
                if method == "POST" and path == "/api/translate":
                    return {
                        "_http_status": 200,
                        "ok": True,
                        "deliveryStatus": "blocked_translation_integrity",
                        "finalTranslation": "",
                        "metadata": {"translationPersisted": False},
                        "qaIssues": [{"code": "hangul_residue_integrity", "priority": "P1"}],
                    }
                raise AssertionError(f"unexpected request {method} {path}")

            with patch.object(batch_eval, "_request_json", side_effect=fake_request_json):
                report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=True,
                    limit=1,
                    base_url="http://fake",
                )

            row = report["per_episode"][0]
            self.assertEqual(report["failed"], 0)
            self.assertEqual(report["blocked"], 1)
            self.assertEqual(row["status"], "integrity_blocked")
            self.assertEqual(row["delivery_status"], "blocked_translation_integrity")
            self.assertIsNone(row["errorCode"])
            self.assertIsNone(row["saved_translation_id"])

    def test_translation_timeout_records_failed_episode_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "input"
            report_dir = tmp_path / "report"
            input_dir.mkdir()
            candidate_text = "由ъ븘??遺곷??怨?移댁씠???먮Ⅸ?ㅽ듃瑜?蹂댁븯?? 洹몃???洹몃? 寃? ?묐??쇨퀬 遺덈???"
            _write_episode(input_dir / "001.txt", "Series Title", f"Episode 1\n{candidate_text}")
            _write_episode(input_dir / "002.txt", "Series Title", f"Episode 2\n{candidate_text}")

            os.environ["CONTENT_STORE_BACKEND"] = "memory"
            os.environ["GLOSSARY_STORE_BACKEND"] = "memory"
            os.environ["WLIGHTER_MOCK_MODE"] = "true"

            original_request_json = batch_eval._request_json
            failures_left = {"count": 1}

            def flaky_request_json(method, base_url, path, *, json_body=None, timeout=60):
                if path == "/api/translate" and failures_left["count"]:
                    failures_left["count"] -= 1
                    raise TimeoutError("timed out")
                return original_request_json(method, base_url, path, json_body=json_body, timeout=timeout)

            with patch.object(batch_eval, "_request_json", side_effect=flaky_request_json):
                report = run_batch_eval(
                    input_dir=input_dir,
                    report_dir=report_dir,
                    save_results=False,
                    capture_glossary_candidates=True,
                    limit=2,
                    request_timeout=600,
                )

            self.assertEqual(report["request_timeout_seconds"], 600)
            self.assertEqual(report["total_episodes"], 2)
            self.assertEqual(report["failed"], 1)
            self.assertGreaterEqual(report["succeeded"], 1)
            per_episode = {row["episode_no"]: row for row in report["per_episode"]}
            self.assertEqual(per_episode[1]["status"], "failed")
            self.assertEqual(per_episode[1]["errorCode"], "translation_timeout")
            self.assertEqual(per_episode[1]["error"], "Translation request timed out after 600 seconds")
            self.assertIn(per_episode[2]["status"], {"success", "deliverable", "qa_warning"})
            raw_failed = (report_dir / "raw" / "001.json").read_text(encoding="utf-8")
            self.assertIn("translation_timeout", raw_failed)
            self.assertNotIn("Traceback", raw_failed)


if __name__ == "__main__":
    unittest.main()
