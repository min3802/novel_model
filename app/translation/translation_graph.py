from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.store.memory_store import _get_episode, work_get

from .agents.inspector import InspectionAgent
from .agents.translator import Translator
from .config import PipelineConfig
from .infra.country_locale import resolve_country_for_locale, resolve_locale_for_country
from .retrieval.annotation_retriever import AnnotationResult, AnnotationRetriever
from .retrieval.retriever import IdiomRetriever, RetrievalResult, embed_query
from .text_processing.korean_output import is_korean_source
from .text_processing.terminology import (
    extract_noun_terminology_candidates,
    merge_terminology,
    render_terminology_context,
)


class TranslationProfile(TypedDict, total=False):
    tone: str
    dialogue_style: str
    narration_style: str
    localization_level: str
    proper_noun_policy: str
    culture_policy: str
    do_not: list[str]
    profile_source: str


class SourceAnalysis(TypedDict, total=False):
    sentence_count: int
    dialogue_ratio: float
    scene_functions: list[str]
    emotions: list[str]
    idiom_candidates: list[str]
    cultural_elements: list[str]
    speech_hints: list[str]
    summary: str


class TranslationState(TypedDict, total=False):
    request_payload: dict[str, Any]
    source_text: str
    target_country: str
    target_locale: str
    target_language: str
    work_id: int | None
    episode_id: int | None
    synopsis: str
    genre: str
    work_title: str
    translation_memory: list[dict[str, Any]]
    base_memory_context: str
    retrieval_queries: list[str]
    context_extraction: dict[str, Any] | None
    blocked: bool
    block_reason: str
    translation_profile: TranslationProfile
    source_analysis: SourceAnalysis
    terminology_candidates: list[dict[str, Any]]
    active_terminology: list[dict[str, Any]]
    terminology_context: str
    support_context: dict[str, Any]
    retrieval_results: list[RetrievalResult]
    annotation_results: list[AnnotationResult]
    retrievals: list[dict[str, Any]]
    annotation_matches: list[dict[str, Any]]
    annotation_candidates: list[dict[str, Any]]
    draft: dict[str, Any]
    inspection: dict[str, Any]
    reviewed_translation: str
    workflow_result: Any


_EMOTION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("anxiety", ("불안", "초조", "걱정", "긴장", "두렵", "떨리", "식은땀")),
    ("anger", ("화", "짜증", "분노", "버럭", "열받", "성가시")),
    ("sadness", ("슬프", "눈물", "서러", "아프", "허탈")),
    ("joy", ("기쁘", "웃음", "환하", "설레", "즐겁")),
    ("embarrassment", ("부끄", "민망", "당황", "머쓱")),
    ("affection", ("사랑", "좋아", "그리워", "보고 싶")),
]

_CULTURAL_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("honorifics", ("님", "씨", "선생", "사장", "오빠", "언니", "형", "누나", "아저씨", "아줌마")),
    ("seasonal_customs", ("설날", "추석", "차례", "한복", "세뱃돈")),
    ("food_and_drink", ("김치", "떡", "떡볶이", "김밥", "소주", "막걸리")),
    ("military_or_school", ("군대", "예비군", "학원", "대학", "수능")),
]

_IDIOM_PATTERNS: list[str] = [
    "손에 땀",
    "눈이 번쩍",
    "입이 떡",
    "가슴이 철렁",
    "눈앞이 캄캄",
    "코웃음",
    "말문이 막히",
    "물 만난 고기",
    "눈치를 보다",
    "발이 묶",
    "귀가 솔깃",
    "발 벗고 나서",
    "속이 타",
    "얼굴이 화끈",
    "혀를 차",
]


def _node_error(node: str, exc: Exception) -> RuntimeError:
    return RuntimeError(f"[{node}] {exc}")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _split_sentences(text: str) -> list[str]:
    sentences = [row.strip() for row in re.split(r"(?<=[.!?…。！？])\s+|\n+", text) if row.strip()]
    return sentences or ([text.strip()] if text.strip() else [])


def _detect_emotions(text: str) -> list[str]:
    lowered = text or ""
    matches: list[str] = []
    for label, keywords in _EMOTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            matches.append(label)
    return matches


def _detect_cultural_elements(text: str) -> list[str]:
    lowered = text or ""
    matches: list[str] = []
    for label, keywords in _CULTURAL_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            matches.append(label)
    return matches


def _detect_idiom_candidates(text: str) -> list[str]:
    lowered = text or ""
    return [pattern for pattern in _IDIOM_PATTERNS if pattern in lowered]


def _detect_scene_functions(text: str) -> list[str]:
    lowered = text or ""
    scene_functions: list[str] = []
    if any(marker in lowered for marker in ("“", "”", '"', "「", "」", "『", "』", "—", "- ")):
        scene_functions.append("dialogue")
    if any(marker in lowered for marker in ("!", "ㅋㅋ", "ㅎㅎ", "…", "...")):
        scene_functions.append("emphasis")
    if any(marker in lowered for marker in ("생각", "문득", "떠올", "기억", "느꼈", "깨달", "되새")):
        scene_functions.append("reflection")
    if any(marker in lowered for marker in ("달려", "뛰", "잡", "때리", "밀치", "움직", "들어", "나가", "왔", "갔")):
        scene_functions.append("action")
    if any(marker in lowered for marker in ("설명", "즉", "말하자면", "요약", "배경", "사실")):
        scene_functions.append("exposition")
    if not scene_functions:
        scene_functions.append("narration")
    return list(dict.fromkeys(scene_functions))


def _detect_speech_hints(text: str) -> list[str]:
    lowered = text or ""
    hints: list[str] = []
    if any(marker in lowered for marker in ("요", "죠", "네요", "지요", "세요")):
        hints.append("polite")
    if any(marker in lowered for marker in ("다", "했다", "있다", "없다")):
        hints.append("narrative")
    if any(marker in lowered for marker in ("!", "!!")):
        hints.append("emphatic")
    if any(marker in lowered for marker in ("?", "??")):
        hints.append("interrogative")
    if any(marker in lowered for marker in ("ㅋㅋ", "ㅎㅎ")):
        hints.append("casual")
    return list(dict.fromkeys(hints))


def _genre_signal(*values: str) -> str:
    lowered = " ".join(value for value in values if value).lower()
    if any(token in lowered for token in ("로맨스", "romance", "러브", "연애")):
        return "warm and emotionally responsive"
    if any(token in lowered for token in ("스릴러", "thriller", "미스터리", "mystery", "추리")):
        return "tense and suspense-forward"
    if any(token in lowered for token in ("판타지", "fantasy", "이세계", "마법")):
        return "vivid and immersive"
    if any(token in lowered for token in ("사극", "historical", "시대", "궁")):
        return "formal and period-aware"
    if any(token in lowered for token in ("드라마", "slice", "일상", "현대", "contemporary")):
        return "natural and scene-focused"
    return "balanced and faithful"


def _build_translation_profile(*, synopsis: str, genre: str, work_title: str, target_locale: str) -> TranslationProfile:
    tone = _genre_signal(synopsis, genre, work_title)
    if target_locale == "ko_ja":
        dialogue_style = "compact and character-true"
        narration_style = "clean and readable with natural Japanese cadence"
        localization_level = "balanced"
        proper_noun_policy = "keep names stable and transliterate only when needed"
        culture_policy = "preserve Korean cultural cues and soften only if required for readability"
    elif target_locale == "ko_en_us":
        dialogue_style = "natural and idiomatic"
        narration_style = "smooth and literary while staying faithful"
        localization_level = "balanced"
        proper_noun_policy = "keep names and fixed terms consistent"
        culture_policy = "explain culture-bound details lightly when they would otherwise confuse readers"
    elif target_locale == "ko_zh_cn":
        dialogue_style = "clear and direct"
        narration_style = "natural and scene-focused"
        localization_level = "balanced"
        proper_noun_policy = "preserve proper nouns and glossary terms consistently"
        culture_policy = "keep culture-specific references readable without overexplaining"
    else:
        dialogue_style = "natural and character-specific"
        narration_style = "flowing and concise"
        localization_level = "balanced"
        proper_noun_policy = "preserve canonical names and established spellings"
        culture_policy = "localize only when it improves clarity without flattening the scene"

    if synopsis.strip():
        localization_level = "moderate" if len(synopsis.strip()) > 80 else localization_level

    return {
        "tone": tone,
        "dialogue_style": dialogue_style,
        "narration_style": narration_style,
        "localization_level": localization_level,
        "proper_noun_policy": proper_noun_policy,
        "culture_policy": culture_policy,
        "do_not": [
            "do not rewrite plot beats",
            "do not invent omitted information",
            "do not erase culturally meaningful signals",
            "do not flatten character voice into one register",
        ],
        "profile_source": "default_rule_based_profile_v1",
    }


def _build_source_analysis(source_text: str) -> SourceAnalysis:
    sentences = _split_sentences(source_text)
    dialogue_count = sum(1 for sentence in sentences if any(marker in sentence for marker in ("“", "”", '"', "「", "」", "『", "』", "—")))
    dialogue_ratio = (dialogue_count / len(sentences)) if sentences else 0.0
    scene_functions = _detect_scene_functions(source_text)
    emotions = _detect_emotions(source_text)
    idioms = _detect_idiom_candidates(source_text)
    cultural_elements = _detect_cultural_elements(source_text)
    speech_hints = _detect_speech_hints(source_text)
    summary_bits = [
        f"scene_functions={', '.join(scene_functions)}",
        f"emotions={', '.join(emotions) if emotions else 'none'}",
        f"idioms={len(idioms)}",
        f"culture={len(cultural_elements)}",
        f"speech={', '.join(speech_hints) if speech_hints else 'none'}",
    ]
    return {
        "sentence_count": len(sentences),
        "dialogue_ratio": round(dialogue_ratio, 3),
        "scene_functions": scene_functions,
        "emotions": emotions,
        "idiom_candidates": idioms,
        "cultural_elements": cultural_elements,
        "speech_hints": speech_hints,
        "summary": " / ".join(summary_bits),
    }


def _format_profile_context(profile: TranslationProfile) -> str:
    return "\n".join(
        [
            "[TRANSLATION_PROFILE]",
            f"- tone: {profile.get('tone', '')}",
            f"- dialogue_style: {profile.get('dialogue_style', '')}",
            f"- narration_style: {profile.get('narration_style', '')}",
            f"- localization_level: {profile.get('localization_level', '')}",
            f"- proper_noun_policy: {profile.get('proper_noun_policy', '')}",
            f"- culture_policy: {profile.get('culture_policy', '')}",
            f"- do_not: {', '.join(profile.get('do_not') or [])}",
        ]
    ).strip()


def _format_source_analysis_context(analysis: SourceAnalysis) -> str:
    return "\n".join(
        [
            "[SOURCE_ANALYSIS]",
            f"- summary: {analysis.get('summary', '')}",
            f"- scene_functions: {', '.join(analysis.get('scene_functions') or [])}",
            f"- emotions: {', '.join(analysis.get('emotions') or [])}",
            f"- idiom_candidates: {', '.join(analysis.get('idiom_candidates') or []) or 'none'}",
            f"- cultural_elements: {', '.join(analysis.get('cultural_elements') or []) or 'none'}",
            f"- speech_hints: {', '.join(analysis.get('speech_hints') or []) or 'none'}",
        ]
    ).strip()


def _format_support_context(state: TranslationState) -> str:
    pieces = [state.get("base_memory_context", "").strip()]
    profile = state.get("translation_profile") or {}
    analysis = state.get("source_analysis") or {}
    terminology_context = state.get("terminology_context", "").strip()
    support = state.get("support_context") or {}
    idiom_context = _clean(support.get("idiom_context"))

    if profile:
        pieces.append(_format_profile_context(profile))
    if analysis:
        pieces.append(_format_source_analysis_context(analysis))
    if terminology_context:
        pieces.append(terminology_context)
    if idiom_context:
        pieces.append(idiom_context)

    return "\n\n".join(piece for piece in pieces if piece).strip()


def _normalize_annotation_candidate(row: dict[str, Any]) -> dict[str, Any]:
    item = row.get("item") or {}
    final_score = row.get("final_score")
    note_needed = row.get("note_needed")
    if note_needed is None:
        note_needed = bool(final_score is not None and final_score >= 0.55)
    can_inline = row.get("can_inline")
    if can_inline is None:
        can_inline = bool(note_needed and len((item.get("context_text") or "").strip()) <= 60)
    return {
        "keyword": item.get("keyword_ko") or item.get("keyword") or "",
        "context_text": item.get("context_text") or "",
        "category": item.get("category") or [],
        "culture_type": item.get("culture_type") or "",
        "source_type": item.get("source_type") or "",
        "score": row.get("score"),
        "similarity_score": row.get("similarity_score"),
        "trigger_boost": row.get("trigger_boost"),
        "final_score": final_score,
        "note_needed": note_needed,
        "can_inline": can_inline,
        "no_note_needed": not bool(note_needed),
    }


def _blocked_state(state: TranslationState) -> TranslationState:
    return {
        "blocked": True,
        "block_reason": state.get("block_reason", ""),
    }


class TranslationGraph:
    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        retriever: IdiomRetriever | None = None,
        annotation_retriever: AnnotationRetriever | None = None,
        translator: Translator | None = None,
        inspector: InspectionAgent | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.resources = self.config.resolved_resources()
        self.retriever = retriever or IdiomRetriever(self.config)
        self.annotation_retriever = annotation_retriever or AnnotationRetriever(self.config)
        self.translator = translator or Translator(self.config)
        self.inspector = inspector or InspectionAgent(self.config)
        self._graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(TranslationState)
        builder.add_node("load_context", self.load_context)
        builder.add_node("prepare_translation_profile", self.prepare_translation_profile)
        builder.add_node("analyze_source", self.analyze_source)
        builder.add_node("retrieve_support_context", self.retrieve_support_context)
        builder.add_node("translate", self.translate)
        builder.add_node("inspect", self.inspect)
        builder.add_node("prepare_annotations", self.prepare_annotations)
        builder.add_node("finalize", self.finalize)

        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "prepare_translation_profile")
        builder.add_edge("prepare_translation_profile", "analyze_source")
        builder.add_edge("analyze_source", "retrieve_support_context")
        builder.add_edge("retrieve_support_context", "translate")
        builder.add_edge("translate", "inspect")
        builder.add_edge("inspect", "prepare_annotations")
        builder.add_edge("prepare_annotations", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile(name="translation_graph")

    def run_with_inspection(
        self,
        source_text: str,
        *,
        request_payload: dict[str, Any] | None = None,
        translation_memory: list[dict[str, Any]] | None = None,
        memory_context: str = "",
        retrieval_queries: list[str] | None = None,
        context_extraction: dict[str, Any] | None = None,
    ):
        payload = dict(request_payload or {})
        if source_text and not payload.get("sourceText"):
            payload["sourceText"] = source_text
        initial_state: TranslationState = {
            "request_payload": payload,
            "source_text": source_text,
            "translation_memory": list(translation_memory or []),
            "base_memory_context": memory_context or "",
            "retrieval_queries": list(retrieval_queries or []),
            "context_extraction": context_extraction,
        }
        state = self._graph.invoke(initial_state)
        workflow_result = state.get("workflow_result")
        if workflow_result is None:
            workflow_result = self.finalize(state)["workflow_result"]
        return workflow_result

    def load_context(self, state: TranslationState) -> TranslationState:
        try:
            payload = dict(state.get("request_payload") or {})
            source_text = _clean(payload.get("sourceText") or state.get("source_text"))
            target_country = _clean(
                payload.get("targetCountry")
                or payload.get("country")
                or state.get("target_country")
                or resolve_country_for_locale(self.config.locale)
            )
            if not target_country:
                target_country = self.config.locale
            target_locale = resolve_locale_for_country(target_country) or _clean(
                payload.get("targetLocale") or state.get("target_locale") or self.config.locale
            )
            if not target_locale:
                raise ValueError(f"unsupported targetCountry: {target_country}")
            if not source_text:
                raise ValueError("sourceText is required")

            work_id_raw = payload.get("workId", payload.get("work_id", state.get("work_id")))
            episode_id_raw = payload.get("episodeId", payload.get("episode_id", state.get("episode_id")))
            work_id = int(work_id_raw) if work_id_raw not in {None, ""} else None
            episode_id = int(episode_id_raw) if episode_id_raw not in {None, ""} else None

            if work_id is not None and not work_get(work_id):
                raise ValueError(f"work {work_id} not found")
            if work_id is not None and episode_id is not None and not _get_episode(work_id, episode_id):
                raise ValueError(f"episode {episode_id} not found for work {work_id}")

            payload.setdefault("sourceText", source_text)
            payload.setdefault("targetCountry", target_country)
            payload.setdefault("targetLocale", target_locale)
            payload.setdefault("targetLanguage", self.resources.target_language)

            return {
                "request_payload": payload,
                "source_text": source_text,
                "target_country": target_country,
                "target_locale": target_locale,
                "target_language": self.resources.target_language,
                "work_id": work_id,
                "episode_id": episode_id,
                "synopsis": _clean(payload.get("synopsis") or state.get("synopsis")),
                "genre": _clean(payload.get("genre") or state.get("genre")),
                "work_title": _clean(payload.get("title") or payload.get("workTitle") or state.get("work_title")),
                "translation_memory": list(payload.get("translationMemory") or state.get("translation_memory") or []),
                "retrieval_queries": list(payload.get("retrievalQueries") or state.get("retrieval_queries") or []),
                "context_extraction": payload.get("contextExtraction") or state.get("context_extraction"),
                "base_memory_context": _clean(payload.get("memoryContext") or state.get("base_memory_context")),
                "blocked": not is_korean_source(source_text),
                "block_reason": "non_korean_source" if not is_korean_source(source_text) else "",
            }
        except Exception as exc:
            raise _node_error("load_context", exc) from exc

    def prepare_translation_profile(self, state: TranslationState) -> TranslationState:
        try:
            if state.get("blocked"):
                return _blocked_state(state)
            profile = _build_translation_profile(
                synopsis=state.get("synopsis", ""),
                genre=state.get("genre", ""),
                work_title=state.get("work_title", ""),
                target_locale=state.get("target_locale", ""),
            )
            return {"translation_profile": profile}
        except Exception as exc:
            raise _node_error("prepare_translation_profile", exc) from exc

    def analyze_source(self, state: TranslationState) -> TranslationState:
        try:
            if state.get("blocked"):
                return _blocked_state(state)
            analysis = _build_source_analysis(state.get("source_text", ""))
            return {"source_analysis": analysis}
        except Exception as exc:
            raise _node_error("analyze_source", exc) from exc

    def retrieve_support_context(self, state: TranslationState) -> TranslationState:
        try:
            if state.get("blocked"):
                return _blocked_state(state)

            source_text = state.get("source_text", "")
            retrieval_queries = [query.strip() for query in state.get("retrieval_queries", []) if _clean(query)]
            retrieval_query = "\n".join([source_text, *retrieval_queries]).strip()
            query = retrieval_query or source_text

            chunks, chunk_vectors = embed_query(self.retriever.backend, self.retriever._chunk_query, query)
            with ThreadPoolExecutor(max_workers=2) as executor:
                annotation_future = executor.submit(self.annotation_retriever.search, chunks, chunk_vectors)
                idiom_future = executor.submit(self.retriever.search, chunks, chunk_vectors)
                annotation_results = annotation_future.result()
                retrieval_results = idiom_future.result()

            raw_terminology = (
                state.get("request_payload", {}).get("terminology")
                or state.get("request_payload", {}).get("terms")
                or state.get("request_payload", {}).get("glossary")
                or []
            )
            terminology_candidates = extract_noun_terminology_candidates(source_text)
            active_terminology = merge_terminology(raw_terminology, terminology_candidates)
            terminology_context = render_terminology_context(
                active_terminology,
                state.get("target_locale", ""),
                source_text=source_text,
            )

            retrieval_dicts = [self._retrieval_to_dict(row) for row in retrieval_results]
            annotation_dicts = [self._annotation_to_dict(row) for row in annotation_results]
            idiom_context = IdiomRetriever.build_context(retrieval_results)
            annotation_context = AnnotationRetriever.build_context(annotation_results)
            support_context = {
                "retrieval_query": query,
                "idiom_context": idiom_context,
                "annotation_context": annotation_context,
                "terminology_context": terminology_context,
            }

            return {
                "retrieval_results": retrieval_results,
                "annotation_results": annotation_results,
                "retrievals": retrieval_dicts,
                "annotation_matches": annotation_dicts,
                "terminology_candidates": terminology_candidates,
                "active_terminology": active_terminology,
                "terminology_context": terminology_context,
                "support_context": support_context,
                "context_extraction": {
                    **(state.get("context_extraction") or {}),
                    "terminologyCandidates": terminology_candidates,
                    "translationProfile": state.get("translation_profile") or {},
                    "sourceAnalysis": state.get("source_analysis") or {},
                    "supportContext": support_context,
                },
            }
        except Exception as exc:
            raise _node_error("retrieve_support_context", exc) from exc

    def translate(self, state: TranslationState) -> TranslationState:
        try:
            if state.get("blocked"):
                return _blocked_state(state)
            memory_context = _format_support_context(state)
            draft = self.translator.translate(
                state.get("source_text", ""),
                state.get("retrieval_results", []) or [],
                memory_context=memory_context,
                translation_profile=state.get("translation_profile") or {},
                source_analysis=state.get("source_analysis") or {},
            )
            draft_dict = asdict(draft)
            return {
                "draft": draft_dict,
                "reviewed_translation": draft.translation,
                "base_memory_context": memory_context,
            }
        except Exception as exc:
            raise _node_error("translate", exc) from exc

    def inspect(self, state: TranslationState) -> TranslationState:
        try:
            if state.get("blocked"):
                return _blocked_state(state)
            inspection = self.inspector.inspect(
                source_text=state.get("source_text", ""),
                draft_translation=(state.get("draft") or {}).get("translation", ""),
                translation_rationale=(state.get("draft") or {}).get("rationale", ""),
                translation_memory=state.get("translation_memory") or [],
                translation_profile=state.get("translation_profile") or {},
                source_analysis=state.get("source_analysis") or {},
            )
            inspection_dict = asdict(inspection)
            return {"inspection": inspection_dict}
        except Exception as exc:
            raise _node_error("inspect", exc) from exc

    def prepare_annotations(self, state: TranslationState) -> TranslationState:
        try:
            if state.get("blocked"):
                return _blocked_state(state)
            candidates = [_normalize_annotation_candidate(row) for row in state.get("annotation_matches", [])]
            return {
                "annotation_candidates": candidates,
                "context_extraction": {
                    **(state.get("context_extraction") or {}),
                    "annotationCandidates": candidates,
                },
            }
        except Exception as exc:
            raise _node_error("prepare_annotations", exc) from exc

    def finalize(self, state: TranslationState) -> TranslationState:
        try:
            if state.get("blocked"):
                result = {
                    "source_text": state.get("source_text", ""),
                    "retrievals": [],
                    "annotation_matches": [],
                    "draft": {},
                    "inspection": {},
                    "reviewed_translation": "",
                    "context_extraction": state.get("context_extraction"),
                    "memory_context": state.get("base_memory_context", ""),
                    "blocked": True,
                    "block_reason": state.get("block_reason", ""),
                    "translation_profile": state.get("translation_profile") or {},
                    "source_analysis": state.get("source_analysis") or {},
                    "annotation_candidates": state.get("annotation_candidates") or [],
                    "terminology_candidates": state.get("terminology_candidates") or [],
                    "active_terminology": state.get("active_terminology") or [],
                    "terminology_context": state.get("terminology_context", ""),
                    "draft_translation": "",
                    "inspection_issues": [],
                    "support_context": state.get("support_context") or {},
                }
                from .translation_pipeline import AgentWorkflowResult

                return {"workflow_result": AgentWorkflowResult(**result)}

            draft = state.get("draft") or {}
            inspection = state.get("inspection") or {}
            result = {
                "source_text": state.get("source_text", ""),
                "retrievals": state.get("retrievals") or [],
                "annotation_matches": state.get("annotation_matches") or [],
                "draft": draft,
                "inspection": inspection,
                "reviewed_translation": state.get("reviewed_translation") or draft.get("translation", ""),
                "context_extraction": state.get("context_extraction"),
                "memory_context": state.get("base_memory_context", ""),
                "blocked": False,
                "block_reason": "",
                "translation_profile": state.get("translation_profile") or {},
                "source_analysis": state.get("source_analysis") or {},
                "annotation_candidates": state.get("annotation_candidates") or [],
                "terminology_candidates": state.get("terminology_candidates") or [],
                "active_terminology": state.get("active_terminology") or [],
                "terminology_context": state.get("terminology_context", ""),
                "draft_translation": draft.get("translation", ""),
                "inspection_issues": inspection.get("issues") or [],
                "support_context": state.get("support_context") or {},
            }
            from .translation_pipeline import AgentWorkflowResult

            return {"workflow_result": AgentWorkflowResult(**result)}
        except Exception as exc:
            raise _node_error("finalize", exc) from exc

    @staticmethod
    def _retrieval_to_dict(row: RetrievalResult) -> dict[str, Any]:
        return {
            "score": row.score,
            "similarity_score": row.similarity_score,
            "anchor_boost": row.anchor_boost,
            "final_score": row.final_score,
            "item": row.item,
        }

    @staticmethod
    def _annotation_to_dict(row: AnnotationResult) -> dict[str, Any]:
        return {
            "score": row.score,
            "similarity_score": row.similarity_score,
            "trigger_boost": row.trigger_boost,
            "final_score": row.final_score,
            "item": row.item,
        }
