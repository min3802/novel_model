# Workspace cleanup report

Date: 2026-06-05

## Removed as generated/temporary

```txt
frontend/.next/
frontend/tsconfig.tsbuildinfo
.pytest_cache/
__pycache__/ and nested Python bytecode caches
.omc/
frontend/.omc/
??.zip
```

`??.zip` was a large temporary archive containing copies of project/reference/generated files.

## Moved out of root

```txt
page ??? ???/      -> docs/reference_assets/page_images/
??? ??? ???/    -> docs/reference_assets/debug_pages/
checkout.html           -> docs/reference_assets/legacy_static/checkout.html
logo.png                -> docs/reference_assets/legacy_static/logo.png
```

These are reference/static legacy assets, not runtime code paths.

## Kept in root intentionally

```txt
ko_anchored_idiom_results_final/
```

This directory is no longer read by the default runtime after the KURE migration. It is still kept as a regeneration/source-reference input for `scripts/normalize_rag_references.py`; do not delete it unless the normalization workflow is retired or migrated.

## Kept intentionally

```txt
frontend/node_modules/   # needed for immediate local Next.js execution
data/                   # RAG, localization guide, embedding/runtime data
.omx/                   # OMX handoff/session state
.env                    # local credentials/config; ignored
.claude/, .vscode/      # local tool/editor settings
```

## .gitignore hardening

Added ignore entries for:

```txt
frontend/*.tsbuildinfo
.omc/
frontend/.omc/
```

## Validation after cleanup

Passed before final generated-artifact removal:

```txt
python -B -m py_compile api_server.py backend/store/memory_store.py backend/services/translation_service.py backend/services/cover_plan_service.py backend/services/guide_service.py backend/services/image_service.py
python -B -m unittest tests.test_translation_consistency_glossary tests.test_work_memory tests.test_model_acceptance_from_docs tests.test_platform_trend_advisor tests.test_platform_trend_guide tests.test_platform_trend_collector tests.test_k_culture_rag tests.test_retriever_anchor_priority
npm run typecheck
npm run build
```

Results:

```txt
Python selected suite: 42 tests OK
Next typecheck OK
Next production build OK
```

After build validation, `frontend/.next/`, `frontend/tsconfig.tsbuildinfo`, and new `__pycache__/` directories were removed again to leave the workspace clean.

## 2026-06-05 post-KURE cleanup addendum

Removed after switching retrieval to `nlpai-lab/KURE-v1`:

```txt
data/embedding_cache/*   # stale OpenAI text-embedding cache; KURE will regenerate cache entries
frontend/.next/
__pycache__/
ko_locale_pipeline/__pycache__/
tests/__pycache__/
```

Also removed the now-unused `ANCHOR_RESULTS_DIR` constant from `ko_locale_pipeline/locales.py`.
