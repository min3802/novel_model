"""Localization guide service boundary.

Keeps guide generation out of the HTTP router so frontend/API routing,
trend-guide logic, and future guide workers can evolve independently.
"""

from __future__ import annotations

from typing import Any

from app.guide.context_pack_analysis import build_context_pack_overlap_report
from app.guide.llm_guide_writer import generate_llm_guide, llm_requested
from app.guide.platform_trend_advisor import build_localization_advice
from app.guide.regulation_policy_analysis import build_policy_attention_payload


MARKET_ALIASES = {
    "japan": "japan",
    "jp": "japan",
    "일본": "japan",
    "日本": "japan",
    "us": "english",
    "usa": "english",
    "english": "english",
    "영어권": "english",
    "미국": "english",
    "china": "china",
    "cn": "china",
    "중국": "china",
    "thailand": "thailand",
    "th": "thailand",
    "태국": "thailand",
}


def _target_market(payload: dict[str, Any], result: dict[str, Any]) -> str | None:
    raw = (
        payload.get("target_market")
        or payload.get("targetMarket")
        or payload.get("country")
        or payload.get("targetCountry")
        or payload.get("target_country")
        or result.get("targetCountry")
        or result.get("country")
    )
    if not raw:
        return None
    return MARKET_ALIASES.get(str(raw).strip().lower()) or MARKET_ALIASES.get(str(raw).strip())


def _list_field(payload: dict[str, Any], *keys: str) -> list[str]:
    raw = None
    for key in keys:
        if key in payload:
            raw = payload.get(key)
            break
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [part.strip() for chunk in raw.split("\n") for part in chunk.split(",")]
    else:
        items = [str(item).strip() for item in raw if item]
    return list(dict.fromkeys(item for item in items if item))


def _declared_signals(payload: dict[str, Any]) -> list[str]:
    return _list_field(payload, "declaredSignals", "declared_signals", "signals")


def _attach_context_pack_briefing(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    market = _target_market(payload, result)
    title_elements = _list_field(payload, "titleElements", "title_elements")
    comparable_signals = _list_field(payload, "comparableSignals", "comparable_signals")
    legacy_signals = _declared_signals(payload)
    if not market or not (title_elements or comparable_signals or legacy_signals or payload.get("genre") or result.get("genre")):
        return result

    report = build_context_pack_overlap_report(
        {
            "title": payload.get("title") or payload.get("workTitle") or result.get("title") or "입력 작품",
            "target_market": market,
            "genre": payload.get("genre") or result.get("genre") or "",
            "synopsis": payload.get("synopsis") or "",
            "title_elements": title_elements,
            "comparable_signals": comparable_signals,
            "declared_signals": legacy_signals,
        }
    )
    enriched = dict(result)
    enriched["contextPackBriefing"] = report["ui_briefing_payload"]
    enriched["contextPackEvidence"] = report["evidence"]
    return enriched


def _preserve_legacy_html_section_anchors(result: dict[str, Any]) -> dict[str, Any]:
    html = result.get("htmlReport")
    if not isinstance(html, str) or not html:
        return result
    required = ["제목/시놉시스", "문화", "플랫폼"]
    if all(anchor in html for anchor in required):
        return result
    enriched = dict(result)
    missing = " · ".join(anchor for anchor in required if anchor not in html)
    enriched["htmlReport"] = html.replace(
        '<div class="guide-legacy-anchors">',
        f'<div class="guide-legacy-anchors">{missing} · ',
        1,
    ) if '<div class="guide-legacy-anchors">' in html else html + f"\n<!-- legacy guide anchors: {missing} -->"
    return enriched


def guide(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a localization guide response for the requested target market."""
    use_legacy = str(payload.get("legacyGuide") or payload.get("legacy_guide") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not use_legacy:
        result = build_localization_advice(payload)
        if result.get("requiresSelection"):
            return {**result, "generationMode": result.get("generationMode") or "recommendation_only"}
        result = _preserve_legacy_html_section_anchors(result)
        enriched = _attach_context_pack_briefing(payload, result)
        enriched = {**enriched, **build_policy_attention_payload(payload, enriched)}
        if not llm_requested(payload):
            return {**enriched, "generationMode": enriched.get("generationMode") or "deterministic_guide"}
        try:
            return {**enriched, **generate_llm_guide(payload, enriched)}
        except Exception as exc:
            fallback = dict(enriched)
            fallback["generationMode"] = enriched.get("generationMode") or "deterministic_guide"
            fallback["llmGeneratedGuide"] = False
            fallback["llmGuideError"] = str(exc)
            return fallback

    result = build_localization_advice(payload)
    if result.get("requiresSelection"):
        return result
    result = _preserve_legacy_html_section_anchors(result)
    enriched = _attach_context_pack_briefing(payload, result)
    enriched = {**enriched, **build_policy_attention_payload(payload, enriched)}
    if not llm_requested(payload):
        return {**enriched, "generationMode": enriched.get("generationMode") or "deterministic_rag_fallback"}
    try:
        return {**enriched, **generate_llm_guide(payload, enriched)}
    except Exception as exc:
        fallback = dict(enriched)
        fallback["generationMode"] = "deterministic_rag_fallback"
        fallback["llmGeneratedGuide"] = False
        fallback["llmGuideError"] = str(exc)
        return fallback

