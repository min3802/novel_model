from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .infra.locales import KO_JA, LOCALE_REGISTRY, LocaleResources
from .infra.project_paths import package_project_root


@dataclass(slots=True)
class PipelineConfig:
    locale: str = KO_JA.locale
    resources: LocaleResources | None = None
    rag_dataset_path: Path | None = None
    annotation_dataset_path: Path | None = None
    cultural_terms_path: Path | None = None
    inspection_prompt_path: Path | None = None
    embedding_model: str = "nlpai-lab/KURE-v1"
    translation_model: str = "gpt-4.1-mini"
    review_model: str = "gpt-4.1-mini"
    # 검색 개수 (2단계로 분리)
    #  *_top_k    : (A) 쿼리(문장) 1개당 qdrant 에서 가져올 후보 수 — 문장별 검색 깊이
    #  *_return_k : (B) 모든 문장 결과를 통합한 뒤 번역에 넘길 최종 상한
    idiom_top_k: int = 3
    idiom_return_k: int = 15
    # 검색 threshold (idiom·annotation 동일하게 0.6으로 통일)
    score_threshold: float = 0.6
    annotation_top_k: int = 2
    annotation_return_k: int = 10
    annotation_score_threshold: float = 0.6
    mock: bool = False
    embedding_cache_dir: Path | None = None
    # --- 청킹 전략 선택 (A/B 실험용) -----------------------------------
    # "paragraph": 줄바꿈 기준으로 묶는다.
    # "sentence" : Kiwi(kiwipiepy)로 문장 단위 분리 후 각 문장을 그대로 검색.
    # 현재 기본값은 "sentence" (Kiwi 문장 단위). kiwipiepy 미설치 시 paragraph로 폴백.
    chunk_strategy: str = "sentence"
    # --- qdrant 설정 ---------------------------------------------------
    # mock=False면 qdrant 검색, mock=True면 레거시 JSON 경로(테스트용).
    # TODO: 도커 서버로 전환 시 이 경로 대신 url 방식으로 교체.
    #   예) QdrantClient(url="http://localhost:6333")
    #   서버 전환 시 코드 한 줄 변경 + 컬렉션 데이터 서버에 재적재 필요.
    qdrant_path: str = "qdrant_local"

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
        return package_project_root(Path(__file__)) / "data" / "annotation_rag" / "kculture_rag_documents_reviewed.json"

    def resolved_cultural_terms_path(self) -> Path:
        if self.cultural_terms_path is not None:
            return Path(self.cultural_terms_path)
        return package_project_root(Path(__file__)) / "data" / "cultural_terms" / "ko_cultural_terms.json"

    def resolved_inspection_prompt_path(self) -> Path:
        return Path(self.inspection_prompt_path or self.resolved_resources().inspection_prompt_path)

    def resolved_embedding_cache_dir(self) -> Path:
        if self.embedding_cache_dir is not None:
            return Path(self.embedding_cache_dir)
        return package_project_root(Path(__file__)) / "data" / "embedding_cache"

    # locale → idiom(번역용) qdrant 컬렉션 이름 매핑.
    _IDIOM_COLLECTION_BY_LOCALE = {
        "ko_ja": "idiom_jp",
        "ko_en_us": "idiom_us",
        "ko_zh_cn": "idiom_cn",
        "ko_th_th": "idiom_th",
    }

    def resolved_idiom_collection(self) -> str:
        try:
            return self._IDIOM_COLLECTION_BY_LOCALE[self.locale]
        except KeyError as exc:
            raise KeyError(f"No idiom collection mapped for locale: {self.locale}") from exc

    def resolved_annotation_collection(self) -> str:
        # 한국 문화 주석은 locale과 무관하게 항상 kculture 컬렉션을 사용한다.
        return "kculture"

    def resolved_qdrant_path(self) -> Path:
        # 상대경로면 프로젝트 루트 기준으로 해석한다.
        path = Path(self.qdrant_path)
        if path.is_absolute():
            return path
        return package_project_root(Path(__file__)) / path
