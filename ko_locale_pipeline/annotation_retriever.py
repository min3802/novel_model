from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import PipelineConfig
from .retriever import create_embedding_backend, l2_normalize


def _clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def build_annotation_search_text(item: dict[str, Any]) -> str:
    value = item.get("embedding_text")
    if isinstance(value, str) and value.strip():
        return value.strip()

    # Backward-compatible fallback for older annotation card shapes.
    chunks: list[str] = []
    for field in ("semantic_keywords", "cultural_explanation", "scenario", "when_to_annotate"):
        legacy_value = item.get(field)
        if isinstance(legacy_value, list):
            cleaned = _clean_list(legacy_value)
            if cleaned:
                chunks.append(f"{field}: {' | '.join(cleaned)}")
        elif isinstance(legacy_value, str) and legacy_value.strip():
            chunks.append(f"{field}: {legacy_value.strip()}")
    return "\n".join(chunks)


@dataclass(slots=True)
class AnnotationResult:
    item: dict[str, Any]
    score: float
    similarity_score: float
    trigger_boost: float
    final_score: float


class AnnotationRetriever:
    """Retriever for Korean cultural annotation/note candidates.

    Unlike the translation RAG retriever, this does not recommend target-language
    equivalents. It retrieves source-side cultural context that may deserve an
    inline explanation, first-occurrence note, or no annotation depending on the
    target reader and source context.
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.dataset_path = config.resolved_annotation_dataset_path()
        self.cache_dir = config.resolved_embedding_cache_dir()
        self.items = self._load_items(self.dataset_path)
        self.search_texts = [build_annotation_search_text(item) for item in self.items]
        self.backend = create_embedding_backend(config)
        self.matrix = self._load_or_create_index()

    @staticmethod
    def _load_items(dataset_path: Path) -> list[dict[str, Any]]:
        if not dataset_path.exists():
            return []
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"Annotation RAG dataset must be a JSON list: {dataset_path}")
        return [row for row in data if isinstance(row, dict)]

    def _cache_paths(self) -> tuple[Path, Path]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.sha256(
            f"{self.dataset_path.resolve()}::{self.config.embedding_model}::annotation-rag-v1".encode("utf-8")
        ).hexdigest()[:16]
        return self.cache_dir / f"{cache_key}.npy", self.cache_dir / f"{cache_key}.meta.json"

    def _load_or_create_index(self) -> np.ndarray:
        if not self.items:
            return np.zeros((0, 1), dtype=np.float32)
        if self.config.mock:
            return self.backend.embed(self.search_texts)

        matrix_path, meta_path = self._cache_paths()
        current_meta = {
            "dataset_path": str(self.dataset_path.resolve()),
            "dataset_mtime_ns": self.dataset_path.stat().st_mtime_ns,
            "embedding_model": self.config.embedding_model,
            "record_count": len(self.items),
            "search_strategy": "annotation-rag-v1",
        }
        if matrix_path.exists() and meta_path.exists():
            cached_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if cached_meta == current_meta:
                return np.load(matrix_path)

        matrix = self.backend.embed(self.search_texts)
        np.save(matrix_path, matrix)
        meta_path.write_text(json.dumps(current_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return matrix

    @staticmethod
    def _normalize_match_text(text: str) -> str:
        return re.sub(r"[\W_]+", "", text).casefold()

    @classmethod
    def _trigger_match_boost(cls, item: dict[str, Any], query: str) -> float:
        """Deprecated compatibility hook.

        Reviewed annotation RAG now relies on embedding_text similarity only.
        Keep the method returning 0.0 so older callers/tests do not break while
        avoiding hidden lexical boosts in production ranking.
        """
        return 0.0

    def retrieve(self, query: str, top_k: int | None = None) -> list[AnnotationResult]:
        if not self.items:
            return []
        limit = top_k or self.config.annotation_top_k
        query_vec = self.backend.embed([query.strip() or " "])[0]
        if self.matrix.shape[1] != query_vec.shape[0]:
            query_vec = l2_normalize(query_vec.reshape(1, -1))[0]
        sim = self.matrix @ query_vec
        boosts = np.zeros(len(self.items), dtype=np.float32)
        final = sim
        top_indices = np.argsort(final)[::-1][:limit]

        results: list[AnnotationResult] = []
        for index in top_indices:
            if final[index] < self.config.annotation_score_threshold:
                break
            results.append(
                AnnotationResult(
                    item=self.items[index],
                    score=float(final[index]),
                    similarity_score=float(sim[index]),
                    trigger_boost=float(boosts[index]),
                    final_score=float(final[index]),
                )
            )
        return results

    @staticmethod
    def build_context(results: list[AnnotationResult]) -> str:
        if not results:
            return "[ANNOTATION_RAG] no cultural annotation candidates matched"

        blocks = ["[ANNOTATION_RAG] Korean cultural annotation candidates"]
        for index, result in enumerate(results, start=1):
            item = result.item
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            blocks.append(
                "\n".join(
                    [
                        f"{index}. id: {item.get('id', '')}",
                        f"   keyword: {metadata.get('keyword_ko', '')}",
                        f"   category: {metadata.get('category', '')}",
                        f"   culture_type: {metadata.get('culture_type_ko', '')}",
                        f"   trigger_terms: {', '.join(_clean_list(item.get('trigger_terms')))}",
                        f"   context: {item.get('context_text', '')}",
                        f"   similarity_score: {result.similarity_score:.4f}",
                        f"   trigger_boost: {result.trigger_boost:.4f}",
                        f"   final_score: {result.final_score:.4f}",
                    ]
                )
            )
        return "\n".join(blocks)
