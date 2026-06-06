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
prompts/
scripts/
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
data/legacy_idiom_rag/normalized_sample/
data/legacy_idiom_rag/usable_candidates/
data/legacy_idiom_rag/seed/
data/localization_guide/platform_observation/
data/localization_guide/platform_trend_advisor.py
data/localization_guide/platform_trend_guide.py
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
data/ontology/
data/localization_guide/raw/
data/legacy_idiom_rag/raw_enriched/*_references_enriched.json
docs/reference_assets/
docs/*_results.json
docs/*outputs_live*
ko_anchored_idiom_results_final/
notebooks/
```

## Cleanup note

`ko_locale_pipeline/ontology.py` is not removed in this baseline because the
current translation service and consistency checker still import it for work
memory/glossary behavior. Remove it only in a separate cleanup pass that either
retires or replaces those API paths.
