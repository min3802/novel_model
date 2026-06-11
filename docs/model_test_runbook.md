# Model Test Runbook

Last updated: 2026-06-08

This runbook captures the current model-test workflow for this repository, using the local `.env` file and the current sparse guide baseline.

Important runtime note:
- The Windows `python` on this machine does not have `python-dotenv` installed.
- Use `C:\Users\kwonm\anaconda3\python.exe` for the live model-test runner and HTML export when you want `.env` loading to work reliably.

## 1. Required `.env` values

The test runner loads `.env` automatically.

Minimum values for live OpenAI-backed cases:

```env
OPENAI_API_KEY=...
WLIGHTER_MOCK_MODE=false
```

Notes:
- `scripts/model_test_case_runner.py` calls `load_dotenv(ROOT / ".env")` itself.
- Leave `--mock` off for live runs.
- Use `--mock` only for plumbing checks that should not call the API.
- If `python scripts\model_test_case_runner.py ...` fails with `ModuleNotFoundError: No module named 'dotenv'`, rerun the same command with `C:\Users\kwonm\anaconda3\python.exe`.

## 2. List the available model test cases

```powershell
python scripts\model_test_case_runner.py --list
```

## 3. Quick mock-only smoke checks

Use these when you only want local plumbing validation:

```powershell
python scripts\model_test_case_runner.py --case TST-GDE-001 --mock
python scripts\module_smoke.py --case all
```

## 4. Live model checks with `.env`

Run the live cases without `--mock` so the runner can use the API key from `.env`:

```powershell
python scripts\model_test_case_runner.py --case TST-TRANS-001 --case TST-CHAT-001
python scripts\model_test_case_runner.py --case TST-GDE-001
```

If you also want image cases:

```powershell
python scripts\model_test_case_runner.py --case TST-IMG-001 --case TST-IMG-002 --include-images
```

## 5. Current sparse guide baseline

The current guide/HTML baseline uses a realistic sparse payload:

- title: one work title
- genre: one genre
- synopsis: one short synopsis

The checked-in baseline files are:

```txt
docs/live_policy_localization_payload.json
docs/live_policy_localization_response.json
docs/live_policy_final_localization_report.html
```

## 6. Regenerate the final HTML

First refresh the guide response from the saved payload, then export the HTML:

```powershell
@'
import json
from pathlib import Path

from backend.services.guide_service import guide

payload_path = Path("docs/live_policy_localization_payload.json")
response_path = Path("docs/live_policy_localization_response.json")

payload = json.loads(payload_path.read_text(encoding="utf-8"))
response = guide(payload)
response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps({
    "mode": response.get("mode"),
    "policyCards": len(response.get("policyAttentionCards") or []),
    "title": response.get("title"),
}, ensure_ascii=False, indent=2))
'@ | python -

python scripts\export_live_policy_localization_html.py
```

The exporter refreshes:

```txt
docs/live_policy_intermediate_html_report.html
docs/live_policy_intermediate_policy_cards.html
docs/live_policy_final_localization_report.html
docs/live_policy_localization_smoke_summary.json
```

If the payload/response files contain escaped or broken text, rewrite `docs/live_policy_localization_payload.json` first, then regenerate the response and HTML with the same payload.

## 7. What to verify

- `python -m unittest tests.test_title_genre_synopsis_flow`
- `python -m unittest tests.test_regulation_policy_analysis tests.test_context_pack_analysis tests.test_guide_context_pack_briefing`
- `python scripts\export_live_policy_localization_html.py`
- Check that the final HTML reflects the sparse title + genre + synopsis baseline without overclaiming inferred signals.
- Confirm the saved payload/response/HTML files still contain the expected Korean text after regeneration.
