# V3 Literary Package Graph-Compatible Orchestration

## Purpose

The v3 literary package pipeline now has one supported orchestration surface: the graph orchestrator over the stabilized v3 translation/QA/repair core. This document records the graph-only production contract. This is a structure contract, not a feature-fix plan.

Related merge-preparation contracts:

- `docs/translation_graph_merge_plan.md`
- `docs/translation_graph_node_contract.md`
- `docs/translation_annotation_endnotes_contract.md`

Graph mode is now the only v3 literary package orchestrator. `TRANSLATION_ORCHESTRATOR` is no longer a supported v3 runtime selector; setting it to `legacy` is ignored by the v3 entrypoint and does not restore a legacy v3 execution path. Graph failures must not silently fall back to a non-graph v3 path.

`/api/translate` defaults missing `mode`/`pipeline` to `v3_literary_package`, so Django/API callers may omit the selector. If an internal caller chooses to be explicit, send `mode` or `pipeline` as `v3_literary_package`; `legacy_full` remains only as an explicit compatibility override.


## Runtime entrypoints and responsibility split

- API requests enter through `backend/services/translation_service.py`, which normalizes the request/response contract, hydrates work memory/glossary context, shapes `deliveryStatus`, and applies persistence metadata.
- `TranslationPipeline.run_v3_literary_package()` in `app/translation/translation_pipeline.py` is the shared v3 entrypoint and always calls graph orchestration.
- `build_v3_graph_literary_package()` in `app/translation/v3_graph_orchestrator.py` is the only v3 literary package runtime entrypoint used by `TranslationPipeline`.
- `app/translation/v3_literary_package.py` owns the established v3 translation, QA, repair, rationale, glossary-aware support logic, and stable helpers that graph mode reuses.
- `app/translation/v3_graph_orchestrator.py` owns graph-mode orchestration: `StateGraph`/compatible execution, node trace, annotation/endnote branch, integrity routing, graph-level source-copy/prose-residue clean retry, and final state cleanup before package construction.
- `scripts/run_webnovel_batch_eval.py` owns batch orchestration, `--limit` / `--episode-nos`, raw response/report/translation output, and counting persistence-missing only for saved `deliverable` or `qa_warning` responses.

## Node list and responsibilities

1. `normalize_input`
   - Normalizes source text, target locale/country fields, mode, ids, title, genre, persistence flag, and glossary-capture flag into `normalizedRequest`.

2. `load_work_memory`
   - Uses request-provided work memory when present and normalizes it into the existing v3 `WorkMemory` shape.
   - Records `workMemorySource`, fallback reason, and approved glossary count.
   - The current service-level RDB hydration policy remains outside this adapter and is preserved by the service boundary.

3. `prepare_translation_context`
   - Calls existing v3 idiom detection, deterministic source analysis, RAG packet builder, and guideline builder.
   - Keeps RAG/work memory as evidence and consistency support, not a forced rewrite layer.

4. `run_literary_translation`
   - A graph-visible node boundary for the literary translation step.
   - The actual call remains delegated into `run_qa_and_repair` via `run_translation_loop` so the established retry/repair ordering is not split prematurely.

5. `deterministic_precheck`
   - Runs deterministic/critic-compatible checks against the current draft candidate and records issue candidates.
   - Does not edit `finalTranslation` and does not finalize `deliveryStatus`.

6. Parallel reviewer fan-out
   - `review_voice`: character voice, dialogue tone, register consistency.
   - `review_naturalness`: Japanese fluency, literalness, rhythm, web-novel style.
   - `review_cultural`: cultural explanation and reader-endnote candidates without conflicting with annotation nodes.
   - `review_glossary`: approved glossary, temporary name map/name residue, terminology consistency.
   - `review_integrity`: source copy, prose/Hangul residue, bracket/system UI blocks, empty output, and integrity/safety candidates.
   - Reviewers produce findings only: no `finalTranslation` edits and no final `deliveryStatus` decisions.

7. `aggregate_review`
   - Merges reviewer findings, deduplicates issue candidates, records severity, and produces a repair strategy hint.
   - Does not edit `finalTranslation`; does not create safety blocks from integrity-only signals.
   - It is the only fan-out merge point for `review_voice`, `review_naturalness`, `review_cultural`, `review_glossary`, and `review_integrity`; reviewer findings and reviewer trace rows are append/reducer-style payloads and must not overwrite one another across parallel branches.

8. `repair_or_accept`
   - The only graph node authorized to modify `finalTranslation`.
   - Calls the existing `run_translation_loop` / stabilized QA-repair logic, including deterministic patches, clean full translator retry, strict one-shot final clean fallback after source-copy/bulk-residue clean retry failure, bracket-preserving repair, name/glossary repair, and system UI label patch limits.

9. `final_integrity_check`
   - Final defense before packaging: empty output, source copy, residual Hangul/prose, bracket/system UI integrity, safety-vs-integrity status separation, and readerEndnotes/finalTranslation separation.
   - Does not edit `finalTranslation`; it can finalize `deliveryStatus`.

10. `build_translation_package`
   - Builds the same `V3LiteraryPackageResult` contract: final translation, delivery status, QA issues, rationale, author review cards, and internal metadata.

7. `persist_result` / `skip_persist`
   - Hook-compatible node for persistence.
   - Runs only when requested, the package is not blocked (`blocked_translation_safety` or `blocked_translation_integrity`), and final translation is non-empty.
   - Current production service persistence remains the authoritative integration point.

8. `capture_glossary_candidates` / `skip_capture`
   - Hook-compatible node for glossary candidate capture.
   - Runs only when requested, work id and locale are available, and the package is not blocked (`blocked_translation_safety` or `blocked_translation_integrity`).
   - Current production service capture remains the authoritative integration point.

## Current graph-mode flow

```text
START
-> normalize_input
├─ translation flow
│  -> load_work_memory
│  -> prepare_translation_context
│  -> run_literary_translation
│  -> run_qa_and_repair
└─ annotation flow
   -> chunk_source_text
   -> detect_annotation_candidates
   -> retrieve_korean_culture_context
   -> write_reader_endnotes
   -> filter_rank_endnotes
translation flow + annotation flow
-> align_endnotes_to_final_translation
-> build_translation_package
-> should_persist?
   yes -> persist_result
   no  -> skip_persist
-> should_capture_glossary?
   yes -> capture_glossary_candidates
   no  -> skip_capture
-> END
```

The phase-1 implementation uses a real LangGraph `StateGraph` when the installed dependency is available. After `normalize_input`, the graph fans out into the protected translation flow and the annotation/endnote flow, then fans in at `align_endnotes_to_final_translation` before package construction.

## Reader endnotes

Graph mode returns `readerEndnotes` as a structured field. Empty notes are returned as `[]`.

`finalTranslation` remains pure translated prose; reader endnotes are not appended to it by the graph orchestrator. A frontend/download layer may choose to render or append them later.

Current annotation nodes are adapter/stub nodes:

- `chunk_source_text`
- `detect_annotation_candidates`
- `retrieve_korean_culture_context`
- `write_reader_endnotes`
- `filter_rank_endnotes`
- `align_endnotes_to_final_translation`

They do not mutate `finalTranslation` and normally do not change `deliveryStatus`.


## Graph-mode Hangul residue and block policy

Graph mode separates safety failures from target-language integrity failures:

- `blocked_translation_safety` is reserved for true provider/policy safety signals such as a model safety refusal or explicit policy block. Hangul residue, glossary mismatch, bracket mismatch, or system UI localization issues must not be promoted to a safety block by themselves.
- `hangul_residue_integrity` means Japanese output still contains Korean/Hangul text. It is an integrity issue, not a safety issue.
- `blocked_translation_integrity` / `translation_integrity_failed` is used when output cannot be delivered because target-language integrity still fails after repair/retry.

Graph mode handles Hangul residue by category:

- `source_copy`: target output is effectively copied Korean source or bulk Korean prose; graph mode keeps the clean full translator retry path.
- `name_residue`: true person/place/organization/proper-noun residue. This is conservative: prefer approved glossary/name-map or entity-memory category evidence, or a strong Korean-name pattern such as surname+given-name or known name + particle. A Japanese particle after any 2-4 Hangul token is not sufficient by itself.
- `genre_term_residue` / `prose_residue`: ordinary nouns, genre terms, dungeon/system terminology outside bracket UI, or a mostly Japanese sentence with a few Korean nouns left in place. Korean noun + Japanese particle is generally treated as small prose/genre-term residue unless name evidence exists.
- `system_ui_residue`: short Hangul label inside bracket/system UI blocks; this remains limited to bracket/system UI patching and must not rewrite general prose.

General Korean prose residue is not deterministically word-patched. Bulk prose residue triggers one graph-only full retranslation retry with a Japanese-only contract, bracket/system UI preservation, web-novel tone preservation, and an explicit ban on appending `readerEndnotes` to `finalTranslation`. If that clean retry output is still source copy or bulk prose residue, graph mode discards the candidate and may run exactly one stricter clean final fallback. The fallback is still full-translation, Japanese-only, bracket/order preserving, and cannot return Korean source copy as `finalTranslation`.

Small general prose or genre-term residue is also not deterministically word-patched. When source-copy signals are absent, target-script ratio remains high, residual Hangul ratio/count/span count are low, the residue is not a bracket/system UI label, and the issue is not true name residue, `repair_or_accept` may run a targeted LLM repair over only the affected sentence or short local paragraph while preserving unrelated text. This can run directly for a small residue candidate or after a clean retry leaves only a small residue candidate.

After the full retranslation retry, graph mode reruns the critic/validator path. A clean retry can return `deliverable`; minor non-blocking issues can return `qa_warning`; clean retry source-copy/bulk-residue failure can trigger the one-shot strict fallback; persistent source copy or bulk Hangul prose residue after that fallback returns `blocked_translation_integrity`, not `blocked_translation_safety`. If only small general prose residue remains after the clean retry, graph mode attempts targeted LLM repair once, then revalidates the full `finalTranslation`; failure remains an integrity warning/block according to deliverability and is never promoted to a safety block.

The small prose/genre-term residue path is a generic integrity recovery path, not an episode-specific patch. Episode 17 is only a regression case; no episode number, sentence, name, or word-specific deterministic mapping is allowed.

Delivery status policy:

- `deliverable`: translation can be returned and persisted when requested.
- `qa_warning`: translation can be returned with QA issues and persisted when requested.
- `blocked_translation_safety`: true safety/provider/policy refusal; `finalTranslation` is cleared and persistence can be skipped.
- `blocked_translation_integrity`: target-language integrity failure after repair/retry; `finalTranslation` is cleared and persistence can be skipped.

Blocked delivery statuses may intentionally skip persistence and have no `savedTranslationId`. Batch evaluation should treat missing persistence as an error only for `deliverable` / `qa_warning` responses when saving was requested.

## Graph trace

Graph mode stores node-level trace rows under `internal.graphTrace`.

Each trace row includes:

- `node`
- `status`
- `started`
- `finished`
- `skipped`
- node-specific counts or status fields such as `qaIssueCount`, `readerEndnotesCount`, `savedTranslationId`, and `glossarySavedCount`
- repair/integrity fields on graph QA rows: `hangulResidueSpanCount`, `hangulResidueCategory`, `fullRetranslationRetryAttempted`, `fullRetranslationRetrySucceeded`, `smallProseResidueDetected`, `smallGenreTermResidueDetected`, `nameResidueFalsePositiveAvoided`, `targetedRepairAttempted`, `targetedRepairSucceeded`, `targetedRepairFailedReason`, residual Hangul before/after counts and ratios, `targetedRepairAffectedSpanCount`, strict fallback fields (`strictCleanFallbackAttempted`, `strictCleanFallbackSucceeded`, failure/discard reason, source-copy flag, ratios, debug artifact paths, and `finalFallbackAttemptCount`), `failureCategory`, and `finalDeliveryStatus`
- reviewer fan-out fields: `graphReviewTrace` rows retain per-reviewer `reviewerType`, `issueCount`, `maxSeverity`, `repairRequired`, `finalTranslationChanged=false`, and `deliveryStatusChanged=false`; `reviewFindings` contains the merged finding list; `aggregateReview` contains deduplicated issue candidates plus reviewer summaries and issue counts.

The trace intentionally avoids full source text and secrets.

## Graph-only v3 routing

- `TranslationPipeline.run_v3_literary_package()` always calls `build_v3_graph_literary_package()` and records `internal.graphOrchestrator.executionFrame`.
- `TRANSLATION_ORCHESTRATOR=legacy` is removed as a v3 escape hatch and is ignored by this v3 entrypoint.
- Other modes (`legacy_full`, `direct_only`, `qa_only`, v2 modes) are not routed through this graph adapter.
- Graph execution does not silently fall back to a non-graph v3 path if the graph adapter fails.

## Why repair remains centralized

Reviewer fan-out is now explicit, but glossary repair, source-residue repair, bracket preservation, Hangul residue handling, sign-label guards, judge state, and clean retry remain order-sensitive. For this phase they stay centralized inside `repair_or_accept`, which wraps the established `run_translation_loop` behavior instead of letting reviewer nodes edit translation text.



## Batch eval outputs and source management

`run_webnovel_batch_eval.py` writes summaries, raw API responses, and translated text under the selected report directory (`reports/batch_eval` by default). These files are generated evaluation artifacts and are not source-managed project inputs. Keep durable fixtures under `test_inputs/` or explicit docs samples instead.

The batch runner supports `--episode-nos` for sparse episode selection in addition to `--limit`. Use `--episode-nos` for first-pass targeted regression checks (for example a single small-residue regression episode) instead of repeating `limit20`. When `--save-results` is enabled, missing persistence is an error only for `deliverable` and `qa_warning`; blocked translation statuses may legitimately skip persistence and `savedTranslationId`.

## LangGraph merge points

The following graph-compatible nodes are intentionally replaceable when integrating with a teammate's LangGraph implementation:

- `load_work_memory`
- `prepare_translation_context`
- `run_literary_translation`
- `run_qa_and_repair`
- `persist_result`
- `capture_glossary_candidates`

A future LangGraph `StateGraph` can reuse the `TranslationGraphState` keys and node function names directly, or wrap these functions as LangGraph node callables.
