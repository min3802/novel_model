from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .project_paths import cultural_review_prompt_root, package_project_root


@dataclass(frozen=True, slots=True)
class LocaleResources:
    locale: str
    source_language: str
    target_language: str
    rag_dataset_path: Path
    review_prompt_path: Path
    translator_system_prompt: str
    reviewer_system_prompt: str


PROJECT_ROOT = package_project_root(Path(__file__))
EMBEDDING_RAG_DIR = PROJECT_ROOT / "data" / "legacy_idiom_rag" / "raw_enriched"
REVIEW_PROMPT_PATH = cultural_review_prompt_root(Path(__file__)) / "BASE_REVIEW_PROMPT.md"


KO_JA = LocaleResources(
    locale="ko_ja",
    source_language="Korean",
    target_language="Japanese",
    rag_dataset_path=EMBEDDING_RAG_DIR / "jp_idiom_embedding_anchor_meaning.json",
    review_prompt_path=REVIEW_PROMPT_PATH,
    translator_system_prompt=(
        "You are a Korean-to-Japanese localization translator. "
        "The input may contain Korean idioms or culture-bound expressions. "
        "Use retrieved references as soft guidance and produce natural Japanese. "
        "Prefer functionally equivalent Japanese over literal translation when needed. "
        "Return JSON only."
    ),
    reviewer_system_prompt=(
        "You are a Japanese localization reviewer. "
        "Review a Japanese translation generated from a Korean source. Return JSON only."
    ),
)

KO_EN_US = LocaleResources(
    locale="ko_en_us",
    source_language="Korean",
    target_language="English (US)",
    rag_dataset_path=EMBEDDING_RAG_DIR / "us_idiom_embedding_anchor_meaning.json",
    review_prompt_path=REVIEW_PROMPT_PATH,
    translator_system_prompt=(
        "You are a Korean-to-US-English localization translator. "
        "The input may contain Korean idioms or culture-bound expressions. "
        "Use retrieved references as soft guidance and produce natural US English. "
        "Prefer functionally equivalent US English over literal translation when needed. "
        "Return JSON only."
    ),
    reviewer_system_prompt=(
        "You are a US English localization reviewer. "
        "Review a US English translation generated from a Korean source. Return JSON only."
    ),
)

KO_ZH_CN = LocaleResources(
    locale="ko_zh_cn",
    source_language="Korean",
    target_language="Simplified Chinese",
    rag_dataset_path=EMBEDDING_RAG_DIR / "cn_idiom_embedding_anchor_meaning.json",
    review_prompt_path=REVIEW_PROMPT_PATH,
    translator_system_prompt=(
        "You are a Korean-to-Simplified-Chinese localization translator. "
        "The input may contain Korean idioms or culture-bound expressions. "
        "Use retrieved references as soft guidance and produce natural Simplified Chinese. "
        "Prefer functionally equivalent Simplified Chinese over literal translation when needed. "
        "Return JSON only."
    ),
    reviewer_system_prompt=(
        "You are a Simplified Chinese localization reviewer. "
        "Review a Simplified Chinese translation generated from a Korean source. Return JSON only."
    ),
)

KO_TH_TH = LocaleResources(
    locale="ko_th_th",
    source_language="Korean",
    target_language="Thai",
    rag_dataset_path=EMBEDDING_RAG_DIR / "th_idiom_embedding_anchor_meaning.json",
    review_prompt_path=REVIEW_PROMPT_PATH,
    translator_system_prompt=(
        "You are a Korean-to-Thai localization translator. "
        "The input may contain Korean idioms or culture-bound expressions. "
        "Use retrieved references as soft guidance and produce natural Thai. "
        "Prefer functionally equivalent Thai over literal translation when needed. "
        "Return JSON only."
    ),
    reviewer_system_prompt=(
        "You are a Thai localization reviewer. "
        "Review a Thai translation generated from a Korean source. Return JSON only."
    ),
)


LOCALE_REGISTRY: dict[str, LocaleResources] = {
    KO_JA.locale: KO_JA,
    KO_EN_US.locale: KO_EN_US,
    KO_ZH_CN.locale: KO_ZH_CN,
    KO_TH_TH.locale: KO_TH_TH,
}
