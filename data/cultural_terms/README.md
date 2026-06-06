# Cultural term lexicon data

This directory is for small curated Korean cultural-term lexicons used by
`CulturalLexicon`.

Expected row shape:

```json
{
  "id": "ko_wedding_cash_gift",
  "term_ko": "축의금",
  "terms": ["축의금", "축의금 봉투"],
  "aliases": ["부조금"],
  "category": ["wedding", "money"],
  "core_explanation": "...",
  "annotation_points": ["..."],
  "source_type": "curated",
  "review_status": "draft",
  "confidence": "medium"
}
```

This is exact/alias matching data, not embedding-search data.

Files shaped like this should **not** live here:

```json
{
  "id": "KCULTURE_0001",
  "embedding_text": "...",
  "context_text": "...",
  "metadata": {}
}
```

Those belong in `data/annotation_rag/`.
