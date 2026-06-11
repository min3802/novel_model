# Repository baseline manifest

Date: 2026-06-06

This repository baseline is scoped for team division around the active
w.LiGHTER model/API/Next.js workflow. It intentionally avoids committing local
credentials, agent session state, raw crawls, generated caches, and reference
screenshots.

## Active collaboration surface

Commit and review changes primarily under:

```txt
api_server.py
backend/
frontend/
ko_locale_pipeline/
  - terminology.py: noun/proper-noun consistency glossary
  - runtime.py: shared runtime mode detection
  - mock_adapters.py: deterministic test fakes kept out of production flow logic
prompts/
scripts/
  - module_smoke.py: direct model/module smoke runner without web
tests/
requirements.txt
README.md
```

## Runtime data kept in git

These are required by the current default pipeline or current guide flow:

```txt
data/annotation_rag/
data/cultural_terms/
data/legacy_idiom_rag/raw_enriched/*_embedding_anchor_meaning.json
data/localization_guide/platform_observation/platform_observation_poc.json
data/localization_guide/platform_observation/platform_trends_current.json
app/guide/platform_trend_advisor.py
app/guide/platform_trend_guide.py
```

## Handoff documents kept in git

Use these documents as the division baseline:

```txt
docs/next_omx_handoff.md
docs/k_culture_annotation_handoff.md
docs/model_code_test_guide.md
docs/model_test_handoff.md
docs/rag_normalized_schema.md
docs/workspace_cleanup_report.md
docs/repo_baseline_manifest.md
```

## Local-only / archive candidates

These are intentionally ignored for the initial collaboration baseline:

```txt
.env
.claude/
.omx/
.vscode/
__pycache__/
frontend/node_modules/
frontend/.next/
data/embedding_cache/
data/terminology/
data/localization_guide/raw/
data/localization_guide/platform_observation/platform_trend_guide_prompt.json
data/localization_guide/platform_observation/platform_trend_localization_guide.md
data/annotation_rag/k_culture_annotation_cards.json
data/annotation_rag/_k_culture_annotation_report.json
data/legacy_idiom_rag/normalized_sample/
data/legacy_idiom_rag/usable_candidates/
data/legacy_idiom_rag/seed/
data/legacy_idiom_rag/raw_enriched/*_references_enriched.json
docs/reference_assets/
docs/*_results.json
docs/*outputs_live*
docs/live_model_smoke_report.md
docs/mock_model_smoke_report.md
ko_anchored_idiom_results_final/
notebooks/
```

## Terminology consistency note

The collaboration baseline intentionally does not use the legacy broad memory
approach. Translation consistency is scoped to `ko_locale_pipeline/terminology.py`:
confirmed noun/proper-noun rows can be supplied as `terminology`/`terms` in a
translation request, rendered into the prompt, and checked after translation.
Verbs, adjectives, and normal sentence-level wording variation are not enforced.

