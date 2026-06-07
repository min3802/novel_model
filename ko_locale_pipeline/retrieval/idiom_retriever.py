from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from ..config import PipelineConfig
from .retriever import (
    ChunkingMixin,
    EmbeddingBackend,
    RetrievalResult,
    build_search_text,
    create_embedding_backend,
    l2_normalize,
    make_qdrant_client,
)

class IdiomRetriever(ChunkingMixin):
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.backend: EmbeddingBackend = create_embedding_backend(config)
        # qdrant 백엔드: 쿼리 임베딩만 필요하고, 벡터/문서는 qdrant가 보관한다.
        self._use_qdrant = not config.mock  # mock=테스트(JSON+가짜임베딩), 아니면 qdrant+KURE
        if self._use_qdrant:
            self._client = make_qdrant_client(config)
            self._collection = config.resolved_idiom_collection()
            return
        # ---- 레거시 JSON + numpy 경로 (mock=True 테스트 전용) ----
        self.dataset_path = config.resolved_rag_dataset_path()
        self.cache_dir = config.resolved_embedding_cache_dir()
        self.items = self._load_items(self.dataset_path)
        self.search_texts = [build_search_text(item) for item in self.items]
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

    def retrieve(self, query: str, top_k: int | None = None,
                 return_k: int | None = None) -> list[RetrievalResult]:
        """쿼리 문자열을 받아 청킹+임베딩 후 검색. (단독 사용/하위호환용)

        top_k    : (A) 문장(청크) 1개당 가져올 후보 수. 기본 config.idiom_top_k
        return_k : (B) 통합 후 최종 반환 상한.       기본 config.idiom_return_k
        pipeline처럼 쿼리를 미리 임베딩해 공유하는 경우에는 search()를 직접 쓴다.
        """
        chunks = self._chunk_query(query)
        chunk_vectors = self.backend.embed(chunks)
        return self.search(chunks, chunk_vectors, top_k, return_k)

    def search(self, chunks, chunk_vectors, top_k: int | None = None,
               return_k: int | None = None) -> list[RetrievalResult]:
        """미리 만들어진 (chunks, vectors)로 검색만 수행한다. (임베딩 공유 경로)"""
        top_k = top_k if top_k is not None else self.config.idiom_top_k
        return_k = return_k if return_k is not None else self.config.idiom_return_k
        if self._use_qdrant:
            return self._retrieve_qdrant(chunks, chunk_vectors, top_k, return_k)


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

        top_indices = np.argsort(best_final)[::-1][:return_k]
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

    def _retrieve_qdrant(
        self, chunks: list[str], chunk_vectors: np.ndarray, top_k: int, return_k: int
    ) -> list[RetrievalResult]:
        """qdrant 컬렉션에서 청크별로 검색하고, payload 단위로 최고 점수만 취합한다.

        - payload는 평면 구조 그대로 RetrievalResult.item 에 담는다.
        - anchor_boost는 시맨틱 점수만 쓰므로 항상 0.0.
        """
        best: dict[str, tuple[float, dict]] = {}
        for chunk_vec in chunk_vectors:
            hits = self._client.query_points(
                collection_name=self._collection,
                query=chunk_vec.tolist(),
                limit=top_k,
                with_payload=True,
                score_threshold=self.config.score_threshold,
            ).points
            for h in hits:
                payload = dict(h.payload or {})
                key = str(payload.get("source_id") or h.id)
                if key not in best or h.score > best[key][0]:
                    best[key] = (float(h.score), payload)

        ranked = sorted(best.values(), key=lambda x: x[0], reverse=True)[:return_k]
        return [
            RetrievalResult(
                item=payload,
                score=score,
                similarity_score=score,
                anchor_boost=0.0,
                final_score=score,
            )
            for score, payload in ranked
        ]

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
                # LLM 에 넘길 정보만 선별: 번역에 실질 도움되는 context/scene/tone 만.
                # (id, country, language, original_meaning, 검색 점수는 노이즈/중복이라 제외)
                blocks.append(
                    "\n".join(
                        [
                            f"{index}. context: {context_text.strip()}",
                            f"   scene: {', '.join(item.get('scene', []) or [])}",
                            f"   tone: {', '.join(item.get('tone', []) or [])}",
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
