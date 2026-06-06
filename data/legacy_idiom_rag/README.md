# Legacy Idiom RAG Working Data

These files are historical and generated idiom-RAG artifacts kept for traceability and regeneration scripts.

- `raw_enriched/`: legacy enriched idiom references.
- `normalized/`: full normalized output location for `scripts/normalize_rag_references.py`.
- `normalized_sample/`: small sample normalized outputs.
- `seed/`: generated MVP seed/draft terms.
- `usable_candidates/`: filtered high-confidence candidates from `scripts/export_usable_rag_subset.py`.

Runtime note: the current locale retriever defaults to `ko_anchored_idiom_results_final/`, while K-culture annotation retrieval uses `data/annotation_rag/`.
