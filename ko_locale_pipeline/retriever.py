from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np

from .config import PipelineConfig
from .openai_client import get_openai_client


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def build_search_text(item: dict[str, Any]) -> str:
    embedding_text = item.get("embedding_text")
    if isinstance(embedding_text, str) and embedding_text.strip():
        return embedding_text.strip()

    chunks: list[str] = []

    for field in ("ko_anchor_expression", "ko_expression"):
        values = item.get(field) or []
        if isinstance(values, list):
            cleaned = [str(value).strip() for value in values if str(value).strip()]
            if cleaned:
                chunks.append(f"{field}: {' | '.join(cleaned)}")

    if not chunks:
        value = item.get("meaning")
        if isinstance(value, str) and value.strip():
            chunks.append(f"meaning: {value.strip()}")

    return "\n".join(chunks)


@dataclass(slots=True)
class RetrievalResult:
    item: dict[str, Any]
    score: float
    similarity_score: float
    anchor_boost: float
    final_score: float


class EmbeddingBackend(Protocol):
    def embed(self, texts: Iterable[str]) -> np.ndarray: ...


class MockEmbeddingBackend:
    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed(self, texts: Iterable[str]) -> np.ndarray:
        rows = [self._embed_text(text) for text in texts]
        return l2_normalize(np.vstack(rows).astype(np.float32))

    def _embed_text(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, dtype=np.float32)
        compact = (text or "").strip()
        if not compact:
            return vector
        grams = [compact[index:index + 3] for index in range(max(1, len(compact) - 2))]
        for gram in grams:
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        return vector


class OpenAIEmbeddingBackend:
    def __init__(self, model: str, batch_size: int = 64):
        self.model = model
        self.batch_size = batch_size

    def embed(self, texts: Iterable[str]) -> np.ndarray:
        client = get_openai_client()
        vectors: list[list[float]] = []
        batch: list[str] = []
        for text in texts:
            batch.append(text)
            if len(batch) >= self.batch_size:
                vectors.extend(self._embed_batch(client, batch))
                batch = []
        if batch:
            vectors.extend(self._embed_batch(client, batch))
        return l2_normalize(np.array(vectors, dtype=np.float32))

    def _embed_batch(self, client, batch: list[str]) -> list[list[float]]:
        response = client.embeddings.create(model=self.model, input=batch)
        return [row.embedding for row in response.data]


class SentenceTransformerEmbeddingBackend:
    """Local Hugging Face sentence-transformers backend for KURE-style models."""

    def __init__(self, model: str, batch_size: int = 64):
        self.model = model
        self.batch_size = batch_size
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised only without optional dependency in live mode.
            raise RuntimeError(
                "KURE embedding requires the optional 'sentence-transformers' package. "
                "Install project requirements before running live retrieval."
            ) from exc
        self.encoder = SentenceTransformer(model)

    def embed(self, texts: Iterable[str]) -> np.ndarray:
        rows = list(texts)
        if not rows:
            return np.zeros((0, 0), dtype=np.float32)
        vectors = self.encoder.encode(
            rows,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


def create_embedding_backend(config: PipelineConfig) -> EmbeddingBackend:
    if config.mock:
        return MockEmbeddingBackend()
    if config.embedding_model.startswith("text-embedding-"):
        return OpenAIEmbeddingBackend(config.embedding_model)
    return SentenceTransformerEmbeddingBackend(config.embedding_model)


class DenseRetriever:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.dataset_path = config.resolved_rag_dataset_path()
        self.cache_dir = config.resolved_embedding_cache_dir()
        self.items = self._load_items(self.dataset_path)
        self.search_texts = [build_search_text(item) for item in self.items]
        self.backend: EmbeddingBackend = create_embedding_backend(config)
        self.matrix = self._load_or_create_index()

    @staticmethod
    def _load_items(dataset_path: Path) -> list[dict[str, Any]]:
        if not dataset_path.exists():
            raise FileNotFoundError(f"RAG dataset not found: {dataset_path}")
        data = json.loads(dataset_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"RAG dataset must be a JSON list: {dataset_path}")
        return data

    def _cache_paths(self) -> tuple[Path, Path]:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.sha256(
            f"{self.dataset_path.resolve()}::{self.config.embedding_model}::{self.config.locale}::anchor-first-v1".encode("utf-8")
        ).hexdigest()[:16]
        return (
            self.cache_dir / f"{cache_key}.npy",
            self.cache_dir / f"{cache_key}.meta.json",
        )

    def _load_or_create_index(self) -> np.ndarray:
        if self.config.mock:
            return self.backend.embed(self.search_texts)

        matrix_path, meta_path = self._cache_paths()
        current_meta = {
            "dataset_path": str(self.dataset_path.resolve()),
            "dataset_mtime_ns": self.dataset_path.stat().st_mtime_ns,
            "embedding_model": self.config.embedding_model,
            "record_count": len(self.items),
            "locale": self.config.locale,
            "search_strategy": "anchor-first-v1",
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
    def _split_into_chunks(text: str, max_chars: int = 300, min_chars: int = 10) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) >= min_chars]
        if not lines:
            return [text]
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current_len + len(line) > max_chars and current:
                chunks.append(" ".join(current))
                current = [line]
                current_len = len(line)
            else:
                current.append(line)
                current_len += len(line)
        if current:
            chunks.append(" ".join(current))
        return chunks or [text]

    def retrieve(self, query: str, top_k: int = 3) -> list[RetrievalResult]:
        chunks = self._split_into_chunks(query)
        chunk_vectors = self.backend.embed(chunks)  # 배치 1회 호출

        n = len(self.items)
        best_sim = np.full(n, -np.inf, dtype=np.float32)
        best_boost = np.zeros(n, dtype=np.float32)
        best_final = np.full(n, -np.inf, dtype=np.float32)

        for chunk, chunk_vec in zip(chunks, chunk_vectors):
            sim = self.matrix @ chunk_vec
            boosts = np.array(
                [self._lexical_match_boost(item, chunk) for item in self.items],
                dtype=np.float32,
            )
            finals = sim + boosts
            improved = finals > best_final
            best_sim = np.where(improved, sim, best_sim)
            best_boost = np.where(improved, boosts, best_boost)
            best_final = np.where(improved, finals, best_final)

        top_indices = np.argsort(best_final)[::-1][:top_k]
        results = []
        for index in top_indices:
            if best_final[index] < self.config.score_threshold:
                break
            results.append(
                RetrievalResult(
                    item=self.items[index],
                    score=float(best_final[index]),
                    similarity_score=float(best_sim[index]),
                    anchor_boost=float(best_boost[index]),
                    final_score=float(best_final[index]),
                )
            )
        return results

    @staticmethod
    def _normalize_match_text(text: str) -> str:
        return re.sub(r"[\W_]+", "", text).casefold()

    @classmethod
    def _has_exact_phrase_match(cls, query: str, phrases: list[str]) -> bool:
        normalized_query = cls._normalize_match_text(query)
        for phrase in phrases:
            normalized_phrase = cls._normalize_match_text(str(phrase))
            if normalized_phrase and normalized_phrase in normalized_query:
                return True
        return False

    @classmethod
    def _lexical_match_boost(cls, item: dict[str, Any], query: str) -> float:
        # The KURE-ready embedding_text/context_text datasets intentionally rely
        # on semantic score only. Legacy ko_anchor_expression rows keep the old
        # exact-match boost for backwards-compatible tests and custom datasets.
        if item.get("embedding_text") and item.get("context_text"):
            return 0.0

        anchor_phrases = [str(value).strip() for value in item.get("ko_anchor_expression") or [] if str(value).strip()]
        if cls._has_exact_phrase_match(query, anchor_phrases):
            return 1.0

        expression_phrases = [str(value).strip() for value in item.get("ko_expression") or [] if str(value).strip()]
        if cls._has_exact_phrase_match(query, expression_phrases):
            return 0.35

        return 0.0

    @staticmethod
    def build_context(results: list[RetrievalResult]) -> str:
        if not results:
            return "[RAG] no reference matches"

        blocks: list[str] = ["[RAG] Korean-idiom reference matches"]
        for index, result in enumerate(results, start=1):
            item = result.item
            context_text = item.get("context_text")
            if isinstance(context_text, str) and context_text.strip():
                blocks.append(
                    "\n".join(
                        [
                            f"{index}. id: {item.get('id', '')}",
                            f"   context: {context_text.strip()}",
                            f"   metadata: {json.dumps(item.get('metadata', {}), ensure_ascii=False)}",
                            f"   similarity_score: {result.similarity_score:.4f}",
                            f"   anchor_boost: {result.anchor_boost:.4f}",
                            f"   final_score: {result.final_score:.4f}",
                        ]
                    )
                )
                continue
            blocks.append(
                "\n".join(
                    [
                        f"{index}. id: {item.get('id', '')}",
                        f"   ko_anchor: {', '.join(item.get('ko_anchor_expression', []) or [])}",
                        f"   ko_candidates: {', '.join(item.get('ko_expression', []) or [])}",
                        f"   target_reference: {item.get('expression', '')}",
                        f"   meaning: {item.get('meaning', '')}",
                        f"   usage: {item.get('usage', '')}",
                        f"   strategy: {item.get('translation_strategy', '')}",
                        f"   caution: {item.get('caution', '')}",
                        f"   similarity_score: {result.similarity_score:.4f}",
                        f"   anchor_boost: {result.anchor_boost:.4f}",
                        f"   final_score: {result.final_score:.4f}",
                    ]
                )
            )
        return "\n".join(blocks)
