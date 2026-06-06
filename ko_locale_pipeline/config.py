from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .locales import KO_JA, LOCALE_REGISTRY, LocaleResources


@dataclass(slots=True)
class PipelineConfig:
    locale: str = KO_JA.locale
    resources: LocaleResources | None = None
    rag_dataset_path: Path | None = None
    annotation_dataset_path: Path | None = None
    cultural_terms_path: Path | None = None
    review_prompt_path: Path | None = None
    embedding_model: str = "nlpai-lab/KURE-v1"
    translation_model: str = "gpt-5.4-mini"
    review_model: str = "gpt-5.4-mini"
    top_k: int = 5
    score_threshold: float | None = None
    annotation_top_k: int = 5
    annotation_score_threshold: float = 0.55
    mock: bool = False
    embedding_cache_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.score_threshold is None:
            self.score_threshold = self.default_score_threshold(self.locale)

    @staticmethod
    def default_score_threshold(locale: str) -> float:
        if locale in {"ko_zh_cn", "ko_th_th"}:
            return 0.55
        return 0.60

    def resolved_resources(self) -> LocaleResources:
        if self.resources is not None:
            return self.resources
        if self.locale not in LOCALE_REGISTRY:
            raise KeyError(f"Unknown locale: {self.locale}")
        return LOCALE_REGISTRY[self.locale]

    def resolved_rag_dataset_path(self) -> Path:
        return Path(self.rag_dataset_path or self.resolved_resources().rag_dataset_path)

    def resolved_annotation_dataset_path(self) -> Path:
        if self.annotation_dataset_path is not None:
            return Path(self.annotation_dataset_path)
        return Path(__file__).resolve().parent.parent / "data" / "annotation_rag" / "kculture_rag_documents_reviewed.json"

    def resolved_cultural_terms_path(self) -> Path:
        if self.cultural_terms_path is not None:
            return Path(self.cultural_terms_path)
        return Path(__file__).resolve().parent.parent / "data" / "cultural_terms" / "ko_cultural_terms.json"

    def resolved_review_prompt_path(self) -> Path:
        return Path(self.review_prompt_path or self.resolved_resources().review_prompt_path)

    def resolved_embedding_cache_dir(self) -> Path:
        if self.embedding_cache_dir is not None:
            return Path(self.embedding_cache_dir)
        return Path(__file__).resolve().parent.parent / "data" / "embedding_cache"
