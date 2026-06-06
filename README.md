# w.LiGHTER API + Next.js Workflow

This workspace now targets the API/model pipeline plus the Next.js frontend.
The old Streamlit prototype has been removed to avoid confusion.

## Active surfaces

```txt
api_server.py                         # standard-library JSON API server
frontend/                             # Next.js frontend
ko_locale_pipeline/                   # translation/RAG/model pipeline
data/localization_guide/              # platform trend collection + guide generation
scripts/                              # data collection / generation utilities
tests/                                # API/model/pipeline tests
```

## Current localization-guide flow

`/api/guide` supports three modes:

1. No synopsis and no country: return country/genre selection options.
2. No synopsis but country+genre selected: generate a country/genre-based guide.
3. Synopsis provided: recommend best-fit countries from platform trend data, then generate a guide.

Trend evidence is stored under:

```txt
data/localization_guide/platform_observation/platform_trends_current.json
data/localization_guide/platform_observation/platform_trend_localization_guide.md
data/localization_guide/platform_observation/platform_trend_guide_prompt.json
```

## Run API server

```bash
python api_server.py
```

## Run Next.js frontend

```bash
cd frontend
npm run dev
```

## Python verification

```bash
python -m unittest discover -s tests
```

## Test model modules without web

You do not need to start the Next.js frontend for model/module checks.
Use the direct Python smoke runner:

```bash
python scripts/module_smoke.py --case all
python scripts/module_smoke.py --case terminology
python scripts/module_smoke.py --case translate --locale ko_en_us
```

Default mode is mock/offline. Add `--live` only when you intentionally want
configured external model/API calls.

## Mock vs live testing

Mock mode is kept only for plumbing checks: imports, API contracts, pipeline
data flow, and deterministic CI/local tests. Mock outputs live in
`ko_locale_pipeline/mock_adapters.py`; environment mode detection lives in
`ko_locale_pipeline/runtime.py`.

Actual translation/localization quality should be checked with live model runs:

```bash
python scripts/module_smoke.py --case translate --live
python scripts/run_live_model_smoke.py
```

Focused guide/pipeline checks:

```bash
python -m unittest tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_model_acceptance_from_docs tests.test_model_feature_backlog tests.test_k_culture_rag
```

## Notes

- Streamlit is no longer an active product surface.
- Do not add new Streamlit pages/tests.
- Use API + Next.js + model pipeline files for future work.
