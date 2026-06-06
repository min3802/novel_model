# Normalized RAG Reference Schema

This schema is a translation-decision card format for Korean-source localization RAG.
It preserves the existing raw datasets and creates normalized files under `data/legacy_idiom_rag/normalized/`.

## Why this shape

The legacy idiom datasets are useful for retrieval, but field meanings differ by file and many rows are not directly shaped for translation prompts. The normalized schema makes each hit answer:

- what Korean source expression this row can match,
- what target-language expression it recommends,
- which strategy to apply,
- why and when to use it,
- what to avoid,
- how reliable/reviewed the row is.

## MVP JSON shape

```json
{
  "id": "ko_en_us_US_000002_식은죽먹기",
  "locale": "ko_en_us",
  "category": "idiom",
  "source_expression": "식은 죽 먹기",
  "source_aliases": ["이렇게 하면 끝", "그거면 됐지"],
  "target_expression": "Bob's your uncle",
  "target_explanation": "어렵지 않게 끝난다, 그렇게 하면 된다.",
  "strategy": "idiom",
  "reason": "가벼운 대사나 설명에서 어떤 절차가 손쉽게 마무리되거나 해결될 때 참고할 수 있다.",
  "example_source": "",
  "example_translation": "Splendid. Okay. Bob's your uncle. Right. Let's have a look at it.",
  "warnings": ["직역하면 어색하므로 한국어의 자연스러운 관용으로 바꿔야 한다."],
  "tags": ["대사", "해결", "구어체"],
  "confidence": 0.96,
  "source_type": "legacy_import",
  "review_status": "legacy_import",
  "quality_flags": [],
  "legacy": {
    "source_file": "ko_anchored_idiom_results_final/us_idiom_references_ko_anchored.json",
    "legacy_id": "US_000002"
  }
}
```

## Required fields

| Field | Meaning |
| --- | --- |
| `id` | Stable normalized row id. |
| `locale` | Source-target locale, e.g. `ko_en_us`, `ko_ja`, `ko_zh_cn`, `ko_th_th`. |
| `category` | Initial category. MVP defaults to `idiom`; later: `cultural_term`, `honorific`, `genre_term`. |
| `source_expression` | Korean expression to match from the user's source text. |
| `source_aliases` | Other Korean expressions that should retrieve the same card. |
| `target_expression` | Target-language expression/reference. |
| `target_explanation` | Korean explanation of target meaning. |
| `strategy` | Translation strategy: `idiom`, `paraphrase`, `literal`, `transliterate`, etc. |
| `reason` | Why/when this reference is useful. |
| `example_source` | Korean source example, blank if unavailable. |
| `example_translation` | Target-language example. |
| `warnings` | Things to avoid. |
| `tags` | Scene/tone/category tags for filtering and reranking. |
| `confidence` | 0.0-1.0 confidence; legacy `fit_score` maps to this. |
| `source_type` | Provenance, e.g. `legacy_import`, `llm_draft`, `curated`, `user_confirmed`. |
| `review_status` | Review gate: `draft`, `needs_review`, `legacy_import`, `reviewed`, `curated`, `deprecated`. |
| `quality_flags` | Heuristic quality warnings. Rows with blocking flags should be reviewed before strong use. |
| `legacy` | Original source metadata for traceability. |

## Legacy mapping

| Legacy field | Normalized field |
| --- | --- |
| `ko_anchor_expression[0]` | `source_expression` preferred |
| `ko_expression[0]` | `source_expression` fallback |
| remaining `ko_anchor_expression` + `ko_expression` | `source_aliases` |
| `expression` | `target_expression` |
| `meaning` | `target_explanation` |
| `translation_strategy` | `strategy` |
| missing `translation_strategy` | `paraphrase` fallback |
| `usage` | `reason` |
| `caution` | `warnings[0]` |
| `examples` / `examples_original` | `example_translation` |
| `scene` + `tone` | `tags` |
| `fit_score` | `confidence = fit_score / 100` |
| missing `fit_score` | `confidence = 0.5` |

## Quality flags

The normalizer does not delete noisy legacy rows. Instead it marks rows that should not be used as strong translation-decision cards until reviewed.

| Flag | Meaning |
| --- | --- |
| `missing_ko_anchor` | The row only has generated/legacy `ko_expression` candidates and no anchored Korean expression. |
| `low_confidence` | `confidence < 0.7`; usually missing or weak legacy `fit_score`. |
| `source_expression_may_be_machine_translated` | The Korean source candidate looks like a generated glossary label rather than a natural source expression. |
| `missing_translation_strategy` | No explicit legacy strategy. |
| `missing_example` | No usable target-language example. |

Rows with `missing_ko_anchor` or `source_expression_may_be_machine_translated` are assigned:

```json
"review_status": "needs_review"
```

This is intentionally conservative. The row remains available for inspection but should not be prioritized in production retrieval.

## Use policy

For translation prompt priority:

```text
project memory confirmed
> user translation memory
> curated RAG
> reviewed RAG
> legacy_import RAG
> needs_review RAG
> LLM general judgment
```

`draft` rows should not be used strongly until reviewed.

## Repository location

Legacy idiom RAG working files are grouped under `data/legacy_idiom_rag/` so they do not look like the active runtime cultural-term RAG:

- `raw_enriched/`: legacy enriched source files.
- `normalized/`: full normalized output from `scripts/normalize_rag_references.py` when generated.
- `normalized_sample/`: small checked sample outputs.
- `seed/`: generated MVP seed drafts.
- `usable_candidates/`: filtered high-confidence candidate exports.
`needs_review` rows should be excluded by default unless an internal review workflow is active.

## K-Culture annotation RAG

`scripts/build_k_culture_rag.py` converts `K-Culture_desc.json` rows into source-side cultural annotation cards under `data/annotation_rag/`.

These cards are intentionally separate from translation-expression RAG. Existing locale RAG files remain idiom/expression reference datasets, while K-Culture cards are used to decide whether a Korean cultural detail deserves an inline explanation, first-occurrence note, or no annotation.

Input rows are expected to contain:

- `DescriptionID`
- `Description`
- `ScenarioBody`
- `MCQA`
- `Type`
- `Category`

The generated cards use annotation-specific fields:

- `trigger_terms`
- `cultural_explanation`
- `scenario`
- `annotation_hint`
- `when_to_annotate`
- `avoid_overexplaining`
- `source_category`

Generated K-Culture cards use:

```json
{
  "kind": "cultural_annotation",
  "source_type": "k_culture_desc",
  "review_status": "reviewed"
}
```

The pipeline uses two separate retrieval layers:

- `DenseRetriever`: translation-expression RAG from `ko_anchored_idiom_results_final/*_ko_anchored.json`
- `AnnotationRetriever`: cultural annotation RAG from `data/annotation_rag/k_culture_annotation_cards.json`

Regenerate with:

```powershell
python scripts\build_k_culture_rag.py --input C:\Users\kwonm\Downloads\K-Culture_desc.json
```
