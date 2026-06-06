# Annotation RAG data

This directory is the canonical home for embedding-search documents used by
`AnnotationRetriever`.

## Current canonical file

```txt
kculture_rag_documents_reviewed.json
```

Expected row shape:

```json
{
  "id": "KCULTURE_0001",
  "embedding_text": "text to embed and search",
  "context_text": "context passed to the translation/inspection model",
  "metadata": {
    "culture_id": "KCULTURE_0001",
    "category": "...",
    "culture_type_ko": "...",
    "keyword_ko": "..."
  }
}
```

Use `embedding_text` for vector search. Use `context_text` as model context.

Do not put this file under `data/cultural_terms/`; that directory has a
different schema and purpose.
