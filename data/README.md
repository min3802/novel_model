# Data Directory Map

This folder separates active runtime data from historical/generated working data.

## Active runtime data

- `annotation_rag/`: semantic RAG documents used by `AnnotationRetriever`.
- `cultural_terms/`: exact/alias Korean cultural-term lexicon used by `CulturalLexicon`.
- `embedding_cache/`: generated embedding cache. Safe to regenerate, but clearing it can cost API time/money.
- `localization_guide/`: localization-guide modules and platform-observation assets used by the guide API/tests.
- `ontology/`: per-work translation memory/glossary JSON used by `ko_locale_pipeline.ontology`.

## Legacy / working data

- `legacy_idiom_rag/`: legacy idiom RAG source/normalization/filtering artifacts. These are not the default runtime RAG dataset; the current locale retriever defaults to `ko_anchored_idiom_results_final/`.
