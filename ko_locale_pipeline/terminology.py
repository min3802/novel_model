from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

TERMINOLOGY_POLICY_LOCKED = "locked"
TERMINOLOGY_POLICY_PREFERRED = "preferred"
TERMINOLOGY_POLICY_CONTEXTUAL = "contextual"
TERMINOLOGY_STATUS_CONFIRMED = "confirmed"
TERMINOLOGY_STATUS_SUGGESTED = "suggested"


def ko(value: str) -> str:
    try:
        return value.encode("ascii").decode("unicode_escape")
    except UnicodeEncodeError:
        return value


_NOUN_SUFFIX_RULES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "business_name",
        TERMINOLOGY_POLICY_LOCKED,
        "business/place proper noun",
        tuple(map(ko, ("\uc57d\uad6d", "\uc11c\uc810", "\uc2dd\ub2f9", "\uc0c1\ud68c", "\uc0c1\uc810", "\uc5ec\uad00", "\ub2e4\ubc29", "\uce74\ud398", "\ubb38\uad6c\uc810"))),
    ),
    (
        "place_name",
        TERMINOLOGY_POLICY_LOCKED,
        "place proper noun",
        tuple(map(ko, ("\uc2dc\uc7a5", "\uc5ed", "\ub9c8\uc744", "\uac70\ub9ac", "\uace8\ubaa9", "\ub3d9", "\uad81", "\uc0b0", "\uac15"))),
    ),
    (
        "organization_name",
        TERMINOLOGY_POLICY_LOCKED,
        "organization proper noun",
        tuple(map(ko, ("\uae38\ub4dc", "\ubb38\ud30c", "\ud559\uc6d0", "\ud559\uad50", "\ud68c\uc0ac", "\uac00\ubb38", "\uc655\uad6d", "\uc81c\uad6d"))),
    ),
)
_COMMON_NOUNS: dict[str, tuple[str, list[str]]] = {
    ko("\uc57d\uad6d"): ("pharmacy", ["pharmacy", "drugstore"]),
    ko("\uc2dc\uc7a5"): ("market", ["market"]),
    ko("\uae38\ub4dc"): ("guild", ["guild"]),
    ko("\ubb38\ud30c"): ("sect", ["sect", "clan"]),
    ko("\uac00\ubb38"): ("family", ["family", "house"]),
}
_HANGUL_NAME_RE = re.compile(r"[\uac00-\ud7a3]{2,4}(?:\uc740|\ub294|\uc774|\uac00|\uc744|\ub97c|\uc5d0\uac8c|\ud55c\ud14c|\uc640|\uacfc|\uc758|\ub3c4|\ub9cc|\ubd80\ud130|\uae4c\uc9c0|\uc5d0\uc11c|\ub85c|\uc73c\ub85c|,)")
_EN_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
_PARTICLE_SUFFIXES = tuple(map(ko, ("\uc5d0\uac8c", "\ud55c\ud14c", "\ubd80\ud130", "\uae4c\uc9c0", "\uc5d0\uc11c", "\uc73c\ub85c", "\uc740", "\ub294", "\uc774", "\uac00", "\uc744", "\ub97c", "\uc640", "\uacfc", "\uc758", "\ub3c4", "\ub9cc", "\ub85c", ",")))


@dataclass(slots=True)
class TerminologyIssue:
    type: str
    source: str
    expected: str
    actual: str
    severity: str
    message: str


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _strip_particle(value: str) -> str:
    for suffix in _PARTICLE_SUFFIXES:
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: -len(_clean(item.get("source")))):
        key = (_clean(row.get("source")), _clean(row.get("type")))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def extract_noun_terminology_candidates(source_text: str) -> list[dict[str, Any]]:
    """Suggest noun/proper-noun glossary rows without enforcing verbs/adjectives."""
    text = source_text or ""
    rows: list[dict[str, Any]] = []

    for type_name, policy, meaning, suffixes in _NOUN_SUFFIX_RULES:
        for suffix in suffixes:
            pattern = re.compile(rf"[\uac00-\ud7a3]{{2,12}}\s*{re.escape(suffix)}")
            for match in pattern.finditer(text):
                source = match.group(0).strip()
                rows.append(
                    {
                        "source": source,
                        "type": type_name,
                        "meaning": meaning,
                        "policy": policy,
                        "recommendedTranslation": "",
                        "allowedTranslations": [],
                        "status": TERMINOLOGY_STATUS_SUGGESTED,
                    }
                )

    for term, (target, allowed) in _COMMON_NOUNS.items():
        if term in text:
            rows.append(
                {
                    "source": term,
                    "type": "common_noun",
                    "meaning": "recurring noun; prefer consistency but allow natural variants",
                    "policy": TERMINOLOGY_POLICY_PREFERRED,
                    "recommendedTranslation": target,
                    "allowedTranslations": allowed,
                    "status": TERMINOLOGY_STATUS_SUGGESTED,
                }
            )

    for match in _HANGUL_NAME_RE.finditer(text):
        source = _strip_particle(match.group(0).strip())
        if len(source) >= 2:
            rows.append(
                {
                    "source": source,
                    "type": "person_name",
                    "meaning": "Korean person-name candidate",
                    "policy": TERMINOLOGY_POLICY_LOCKED,
                    "recommendedTranslation": "",
                    "allowedTranslations": [],
                    "status": TERMINOLOGY_STATUS_SUGGESTED,
                }
            )

    for match in _EN_NAME_RE.finditer(text):
        source = match.group(0).strip()
        rows.append(
            {
                "source": source,
                "type": "proper_noun",
                "meaning": "proper noun candidate",
                "policy": TERMINOLOGY_POLICY_LOCKED,
                "recommendedTranslation": "",
                "allowedTranslations": [],
                "status": TERMINOLOGY_STATUS_SUGGESTED,
            }
        )

    return _dedupe_rows(rows)


def _target_for_locale(row: dict[str, Any], locale: str) -> str:
    targets = row.get("targets")
    if isinstance(targets, dict):
        return _clean(targets.get(locale) or targets.get("default"))
    return _clean(row.get("target") or row.get("translation") or row.get("recommendedTranslation"))


def normalize_terminology_row(row: dict[str, Any], locale: str) -> dict[str, Any]:
    source = _clean(row.get("source") or row.get("term"))
    target = _target_for_locale(row, locale)
    allowed = [_clean(item) for item in (row.get("allowedTranslations") or row.get("allowed") or [])]
    allowed = [item for item in allowed if item]
    if target and target not in allowed:
        allowed.insert(0, target)
    policy = _clean(row.get("policy")) or TERMINOLOGY_POLICY_LOCKED
    if policy not in {TERMINOLOGY_POLICY_LOCKED, TERMINOLOGY_POLICY_PREFERRED, TERMINOLOGY_POLICY_CONTEXTUAL}:
        policy = TERMINOLOGY_POLICY_LOCKED if row.get("type") != "common_noun" else TERMINOLOGY_POLICY_PREFERRED
    return {
        **row,
        "source": source,
        "target": target,
        "allowedTranslations": allowed,
        "policy": policy,
        "status": _clean(row.get("status")) or TERMINOLOGY_STATUS_SUGGESTED,
        "type": _clean(row.get("type")) or "term",
    }


def terminology_rows_for_locale(terms: Any, locale: str, *, confirmed_only: bool = False) -> list[dict[str, Any]]:
    if not terms:
        return []
    if isinstance(terms, dict):
        raw_rows = terms.get("terms") or terms.get("terminology") or terms.get("glossary") or []
    elif isinstance(terms, list):
        raw_rows = terms
    else:
        return []

    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        row = normalize_terminology_row(raw, locale)
        if not row["source"]:
            continue
        if confirmed_only and row.get("status") != TERMINOLOGY_STATUS_CONFIRMED:
            continue
        rows.append(row)
    return _dedupe_rows(rows)


def merge_terminology(existing: Any, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = terminology_rows_for_locale(existing, "default")
    existing_sources = {_clean(row.get("source")) for row in rows}
    for candidate in candidates:
        source = _clean(candidate.get("source"))
        if source and source not in existing_sources:
            rows.append(dict(candidate))
            existing_sources.add(source)
    return _dedupe_rows(rows)


def render_terminology_context(terms: Any, locale: str, *, source_text: str = "") -> str:
    rows = []
    for row in terminology_rows_for_locale(terms, locale, confirmed_only=False):
        if source_text and row["source"] not in source_text:
            continue
        if row.get("policy") == TERMINOLOGY_POLICY_CONTEXTUAL:
            continue
        rows.append(row)
    if not rows:
        return ""

    lines = [
        "Terminology / proper-noun consistency glossary:",
        "- Enforce only noun/proper-noun rows listed here; do not freeze verbs, adjectives, or normal phrasing.",
        "- LOCKED rows must use the listed target consistently when the source appears.",
        "- PREFERRED rows may use listed variants when the sentence needs natural wording.",
    ]
    for row in rows:
        allowed = [item for item in row.get("allowedTranslations", []) if item and item != row.get("target")]
        allowed_text = f"; allowed variants: {', '.join(allowed)}" if allowed else ""
        target = row.get("target", "")
        if target:
            lines.append(f"- [{row['policy'].upper()}] {row['source']} => {target}{allowed_text} ({row.get('type', 'term')})")
        else:
            lines.append(
                f"- [SUGGESTED {row['policy'].upper()}] {row['source']} => choose one translation/transliteration and reuse it ({row.get('type', 'term')})"
            )
    return "\n".join(lines)


def present_any(translated_text: str, candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate and candidate in translated_text:
            return candidate
    return ""


def issue_to_dict(issue: TerminologyIssue) -> dict[str, Any]:
    return asdict(issue)
