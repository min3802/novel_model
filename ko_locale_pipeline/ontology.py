from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .project_paths import repository_root


MEMORY_VERSION = 1
MEMORY_STATUS_SUGGESTED = "suggested"
MEMORY_STATUS_CONFIRMED = "confirmed"


# Glossary policy constants.  The consistency layer intentionally focuses on
# nouns / named entities, not verbs or ordinary style variation.
GLOSSARY_POLICY_LOCKED = "locked"
GLOSSARY_POLICY_PREFERRED = "preferred"
GLOSSARY_POLICY_CONTEXTUAL = "contextual"

def _u(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


NAMED_ENTITY_SUFFIXES = [
    _u("\\uace0\\ub4f1\\ud559\\uad50"), _u("\\ub300\\ud559\\uad50"), _u("\\ud3b8\\uc758\\uc810"), _u("\\ubb38\\uad6c\\uc810"),
    _u("\\ub300\\uc7a5\\uac04"), _u("\\uc911\\uc559\\uc9c0\\ubd80"), _u("\\uc57d\\uad6d"), _u("\\ubcd1\\uc6d0"),
    _u("\\uc758\\uc6d0"), _u("\\uc2dc\\uc7a5"), _u("\\uc0c1\\uc810"), _u("\\uc2dd\\ub2f9"), _u("\\uce74\\ud398"),
    _u("\\ub2e4\\ubc29"), _u("\\uc5ec\\uad00"), _u("\\ud638\\ud154"), _u("\\uc11c\\uc810"), _u("\\ud559\\uad50"),
    _u("\\ud559\\uc6d0"), _u("\\ud68c\\uc0ac"), _u("\\uae38\\ub4dc"), _u("\\uc0c1\\ud68c"), _u("\\ud611\\ud68c"),
    _u("\\uad50\\ub2e8"), _u("\\uae30\\uc0ac\\ub2e8"), _u("\\uc655\\uad6d"), _u("\\uc81c\\uad6d"), _u("\\uacf5\\uad6d"),
    _u("\\uac00\\ubb38"), _u("\\ubb38\\ud30c"), _u("\\uc885\\ud30c"), _u("\\uc9c0\\ubd80"), _u("\\ubcf8\\ubd80"),
    _u("\\ud56d\\uad6c"), _u("\\ub9c8\\uc744"), _u("\\ub3c4\\uc2dc"), _u("\\uac70\\ub9ac"), _u("\\uace8\\ubaa9"),
    _u("\\ub358\\uc804"), _u("\\uc0ac\\uc6d0"), _u("\\uc2e0\\uc804"), _u("\\ub9c8\\ud0d1"), _u("\\ud0d1"),
    _u("\\uad81"), _u("\\uc131"), _u("\\uad00"), _u("\\uc6d0"), _u("\\uc5ed"),
]

GENERIC_MODIFIERS = {
    _u("\\uadfc\\ucc98"), _u("\\ub3d9\\ub124"), _u("\\uc791\\uc740"), _u("\\ud070"), _u("\\ub0a1\\uc740"),
    _u("\\uc0c8"), _u("\\uc624\\ub798\\ub41c"), _u("\\uc720\\uba85\\ud55c"), _u("\\uac00\\uae4c\\uc6b4"),
    _u("\\uba3c"), _u("\\ubb38"), _u("\\uc5f4\\ub9b0"), _u("\\uc5b4\\ub290"), _u("\\ud55c"),
    _u("\\uadf8"), _u("\\uc774"), _u("\\uc800"), _u("\\uc6b0\\ub9ac"), _u("\\uadfc\\ubc29"), _u("\\uc8fc\\ubcc0"),
}

COMMON_NOUN_TRANSLATION_HINTS: dict[str, dict[str, Any]] = {
    _u("\\uc57d\\uad6d"): {
        "type": "common_noun",
        "policy": GLOSSARY_POLICY_PREFERRED,
        "recommendedTranslation": "pharmacy",
        "allowedTranslations": ["pharmacy", "drugstore", "chemist"],
        "meaning": "General place noun. If it is part of a business name, the longer locked phrase wins.",
    },
    _u("\\uc2dc\\uc7a5"): {
        "type": "common_noun",
        "policy": GLOSSARY_POLICY_PREFERRED,
        "recommendedTranslation": "market",
        "allowedTranslations": ["market", "marketplace"],
        "meaning": "General place noun. If it is part of a named market, the longer locked phrase wins.",
    },
}

KOREAN_PARTICLE_OR_BOUNDARY = r"(?=$|[\s,.;:!??\"'??}\])]|[????????????????????])"



def memory_dir() -> Path:
    return repository_root(Path(__file__)) / "data" / "ontology"


def memory_path(work_id: int) -> Path:
    return memory_dir() / f"work_{work_id}.json"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_empty_memory(work_id: int, *, title: str = "") -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "version": MEMORY_VERSION,
        "workId": work_id,
        "title": title,
        "updatedAt": timestamp,
        "characters": [],
        "relations": [],
        "terms": [],
        "speechStyles": [],
        "events": [],
        "translationPolicies": [],
        "notes": [],
    }


def load_memory(work_id: int, *, title: str = "") -> dict[str, Any]:
    path = memory_path(work_id)
    if not path.exists():
        return create_empty_memory(work_id, title=title)
    with path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    base = create_empty_memory(work_id, title=title)
    base.update(loaded)
    base.setdefault("workId", work_id)
    if title and not base.get("title"):
        base["title"] = title
    return base


def save_memory(memory: dict[str, Any]) -> dict[str, Any]:
    work_id = int(memory["workId"])
    memory = dict(memory)
    memory["version"] = int(memory.get("version") or MEMORY_VERSION)
    memory["updatedAt"] = now_iso()
    path = memory_path(work_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return memory


def normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", "", text)


def make_id(prefix: str, value: str) -> str:
    key = normalize_key(value)
    if not key:
        key = "unknown"
    asciiish = re.sub(r"[^0-9a-zA-Z가-힣_]+", "_", key).strip("_")
    return f"{prefix}_{asciiish[:48] or 'unknown'}"


def _ensure_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _merge_list_values(existing: list[Any], incoming: list[Any]) -> list[Any]:
    result = list(existing)
    seen = {json.dumps(item, ensure_ascii=False, sort_keys=True, default=str) for item in result}
    for item in incoming:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _upsert_by_name(
    rows: list[dict[str, Any]],
    incoming: dict[str, Any],
    *,
    id_prefix: str,
    name_fields: tuple[str, ...],
) -> None:
    name = ""
    for field in name_fields:
        name = str(incoming.get(field) or "").strip()
        if name:
            break
    if not name:
        return

    aliases = [str(v).strip() for v in _ensure_list(incoming.get("aliases")) if str(v).strip()]
    candidate_keys = {normalize_key(name), *(normalize_key(alias) for alias in aliases)}
    candidate_keys.discard("")

    for row in rows:
        row_names = [row.get(field) for field in name_fields]
        row_names.extend(_ensure_list(row.get("aliases")))
        row_keys = {normalize_key(item) for item in row_names if item}
        if candidate_keys & row_keys:
            for key, value in incoming.items():
                if value in (None, "", []):
                    continue
                if key in {"traits", "aliases", "evidence", "rules", "examples"}:
                    row[key] = _merge_list_values(_ensure_list(row.get(key)), _ensure_list(value))
                elif key == "confidence":
                    row[key] = max(float(row.get(key) or 0), float(value or 0))
                elif key == "status":
                    if row.get("status") != MEMORY_STATUS_CONFIRMED:
                        row[key] = value
                elif key not in row or row.get(key) in (None, "", []):
                    row[key] = value
            row.setdefault("id", make_id(id_prefix, name))
            row.setdefault("status", MEMORY_STATUS_SUGGESTED)
            return

    next_row = dict(incoming)
    next_row.setdefault("id", make_id(id_prefix, name))
    next_row.setdefault("status", MEMORY_STATUS_SUGGESTED)
    next_row.setdefault("confidence", 0.5)
    rows.append(next_row)


def _relation_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_key(row.get("from")),
        normalize_key(row.get("to")),
        normalize_key(row.get("relation")),
    )



def _clean_candidate_prefix(prefix: str) -> str:
    words = [word for word in re.split(r"\s+", prefix.strip()) if word]
    if not words:
        return ""
    # Keep only the immediate naming prefix. Drop earlier clause/location words
    # that are marked by particles (e.g. "???? ?? ??" -> "??",
    # "??? ??? ??" -> "???").
    boundary_endings = tuple(_u(value) for value in [
        r"\uc740", r"\ub294", r"\uc774", r"\uac00", r"\uc744", r"\ub97c", r"\uc5d0", r"\uc5d0\uc11c", r"\uc73c\ub85c", r"\ub85c", r"\ub3c4", r"\ub9cc",
    ])
    cleaned: list[str] = []
    for word in words[-4:]:
        if word in GENERIC_MODIFIERS:
            cleaned = []
            continue
        if any(word.endswith(ending) for ending in boundary_endings):
            cleaned = []
            continue
        cleaned.append(word)
    if not cleaned:
        return ""
    return " ".join(cleaned[-3:]).strip()


def extract_named_entity_glossary_candidates(source_text: str) -> list[dict[str, Any]]:
    """Extract noun-phrase glossary candidates where common nouns are part of names.

    This is deliberately conservative: it locks longer named phrases such as
    "?? ??" but does not lock generic phrases like "?? ??".  Longer
    phrases are returned before shorter/common terms so downstream prompts and
    checks apply the most specific rule first.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    suffixes = sorted(NAMED_ENTITY_SUFFIXES, key=len, reverse=True)
    suffix_alt = "|".join(re.escape(suffix) for suffix in suffixes)
    pattern = re.compile(rf"((?:[\uac00-\ud7a3A-Za-z0-9]+\s*){{0,4}}?)({suffix_alt}){KOREAN_PARTICLE_OR_BOUNDARY}")
    for match in pattern.finditer(source_text):
        prefix = _clean_candidate_prefix(match.group(1))
        suffix = match.group(2)
        if not prefix:
            continue
        candidate = f"{prefix} {suffix}".strip()
        first_word = prefix.split()[0]
        if first_word in GENERIC_MODIFIERS:
            continue
        if candidate in seen or candidate == suffix:
            continue
        seen.add(candidate)
        candidates.append(
            {
                "source": candidate,
                "type": _term_type_for_suffix(suffix),
                "meaning": f"'{suffix}' is part of a named noun phrase; translate the whole phrase consistently.",
                "policy": GLOSSARY_POLICY_LOCKED,
                "recommendedTranslation": "",
                "allowedTranslations": [],
                "confidence": 0.72,
                "status": MEMORY_STATUS_SUGGESTED,
                "evidence": [_first_evidence_for_term(source_text, candidate)],
                "priority": 100 + len(candidate),
                "sourceSuffix": suffix,
            }
        )

    # Add common-noun hints only when the exact common noun appears and is not
    # already covered by a longer named phrase.  These are preferred/contextual,
    # never locked, so they do not flag accepted variants as errors.
    for source, hint in COMMON_NOUN_TRANSLATION_HINTS.items():
        if source not in source_text:
            continue
        if source in seen:
            continue
        seen.add(source)
        candidates.append(
            {
                "source": source,
                "type": hint["type"],
                "meaning": hint["meaning"],
                "policy": hint["policy"],
                "recommendedTranslation": hint["recommendedTranslation"],
                "allowedTranslations": list(hint.get("allowedTranslations") or []),
                "confidence": 0.45,
                "status": MEMORY_STATUS_SUGGESTED,
                "evidence": [_first_evidence_for_term(source_text, source)],
                "priority": 10,
            }
        )

    # Korean personal names in classic samples and user stories.  Keep this
    # conservative: 2-4 Hangul syllables followed by a common subject/object
    # particle, excluding ordinary pronouns/time words.
    stopwords = {_u("\\uadf8\\ub294"), _u("\\uadf8\\ub140"), _u("\\uadf8\\uac00"), _u("\\uadf8\\ub97c"), _u("\\uc624\\ub298"), _u("\\uc774\\uc81c"), _u("\\uc0ac\\ub78c"), _u("\\ubb38\\uc7a5"), _u("\\uc6d0\\ubb38"), _u("\\uc544\\ub0b4"), _u("\\ud559\\uc0dd"), _u("\\uc18c\\ub140"), _u("\\uc18c\\ub144")}
    for match in re.finditer(_u(r"([\uac00-\ud7a3]{2,4})(?=[\uc740\ub294\uc774\uac00\uc744\ub97c\uc5d0\uac8c\uaed8])"), source_text):
        name = match.group(1)
        if name in stopwords or name in seen:
            continue
        seen.add(name)
        candidates.append(
            {
                "source": name,
                "type": "person_name",
                "meaning": "candidate Korean personal name; keep transliteration consistent if confirmed/used",
                "policy": GLOSSARY_POLICY_LOCKED,
                "recommendedTranslation": "",
                "allowedTranslations": [],
                "confidence": 0.58,
                "status": MEMORY_STATUS_SUGGESTED,
                "evidence": [_first_evidence_for_term(source_text, name)],
                "priority": 90 + len(name),
            }
        )

    candidates.sort(key=lambda row: (-int(row.get("priority") or 0), -len(row.get("source") or "")))
    return candidates


def _term_type_for_suffix(suffix: str) -> str:
    business_suffixes = {_u(v) for v in [
        r"\uc57d\uad6d", r"\ubcd1\uc6d0", r"\uc758\uc6d0", r"\uc2dc\uc7a5", r"\uc0c1\uc810", r"\uc2dd\ub2f9", r"\uce74\ud398",
        r"\ud3b8\uc758\uc810", r"\uc11c\uc810", r"\ubb38\uad6c\uc810", r"\ub300\uc7a5\uac04", r"\uc5ec\uad00", r"\ud638\ud154",
    ]}
    organization_suffixes = {_u(v) for v in [
        r"\uae38\ub4dc", r"\uc0c1\ud68c", r"\ud611\ud68c", r"\uad50\ub2e8", r"\uae30\uc0ac\ub2e8", r"\ud68c\uc0ac",
        r"\ud559\uad50", r"\uace0\ub4f1\ud559\uad50", r"\ub300\ud559\uad50", r"\ud559\uc6d0", r"\uc9c0\ubd80", r"\ubcf8\ubd80",
    ]}
    if suffix in business_suffixes:
        return "business_name"
    if suffix in organization_suffixes:
        return "organization_name"
    return "place_name"


def _first_evidence_for_term(text: str, needle: str) -> str:
    idx = text.find(needle)
    if idx < 0:
        return text.strip()[:120]
    return text[max(0, idx - 40): min(len(text), idx + len(needle) + 40)].strip()


def normalize_glossary_term(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    source = str(normalized.get("source") or normalized.get("term") or normalized.get("name") or "").strip()
    normalized["source"] = source
    normalized.setdefault("type", "fixed_term")
    normalized.setdefault("policy", GLOSSARY_POLICY_LOCKED)
    normalized.setdefault("status", MEMORY_STATUS_SUGGESTED)
    normalized.setdefault("confidence", 0.5)
    normalized.setdefault("allowedTranslations", [])
    normalized.setdefault("recommendedTranslation", normalized.get("target") or normalized.get("translation") or "")
    normalized.setdefault("priority", 100 if normalized.get("policy") == GLOSSARY_POLICY_LOCKED else 10)
    normalized.setdefault("id", make_id("term", source))
    return normalized


def upsert_glossary_candidates(memory: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    merged = dict(memory)
    merged["terms"] = list(merged.get("terms") or [])
    for candidate in candidates:
        candidate = normalize_glossary_term(candidate)
        if not candidate.get("source"):
            continue
        _upsert_by_name(merged["terms"], candidate, id_prefix="term", name_fields=("source", "term", "name"))
    merged["terms"].sort(
        key=lambda row: (
            0 if row.get("policy") == GLOSSARY_POLICY_LOCKED else 1,
            -len(str(row.get("source") or row.get("term") or "")),
        )
    )
    merged["updatedAt"] = now_iso()
    return merged


def glossary_rows_for_locale(memory: dict[str, Any] | None, locale: str) -> list[dict[str, Any]]:
    if not memory:
        return []
    rows: list[dict[str, Any]] = []
    for raw in memory.get("terms", []) or []:
        row = normalize_glossary_term(raw)
        source = row.get("source")
        if not source:
            continue
        target = (
            row.get("target")
            or row.get("translation")
            or (row.get("targets") or {}).get(locale)
            or row.get("recommendedTranslation")
            or ""
        )
        allowed = list(row.get("allowedTranslations") or row.get("allowed") or [])
        if target and target not in allowed:
            allowed.insert(0, target)
        row["target"] = str(target).strip()
        row["allowedTranslations"] = [str(item).strip() for item in allowed if str(item).strip()]
        rows.append(row)
    rows.sort(
        key=lambda row: (
            0 if row.get("policy") == GLOSSARY_POLICY_LOCKED else 1,
            -len(str(row.get("source") or "")),
        )
    )
    return rows


def render_glossary_context(memory: dict[str, Any] | None, locale: str, *, source_text: str = "") -> str:
    rows = []
    for row in glossary_rows_for_locale(memory, locale):
        if source_text and row["source"] not in source_text:
            continue
        rows.append(row)
    if not rows:
        return ""
    lines = [
        "Terminology / proper-noun glossary:",
        "- Apply longer source phrases before shorter/common nouns.",
        "- LOCKED terms must use the exact target form when a target is present.",
        "- PREFERRED terms should use the preferred target; allowed variants are acceptable.",
        "- CONTEXTUAL terms are reference-only; choose the natural translation by context.",
        "- Do not enforce verbs, adjectives, ordinary style, or sentence structure as glossary items.",
    ]
    for row in rows[:24]:
        source = row["source"]
        policy = row.get("policy", GLOSSARY_POLICY_LOCKED)
        target = row.get("target") or row.get("recommendedTranslation") or "TRANSLITERATE CONSISTENTLY"
        allowed = row.get("allowedTranslations") or []
        allowed_text = f"; allowed: {', '.join(allowed)}" if allowed else ""
        lines.append(f"- [{policy.upper()}] {source} => {target}{allowed_text} ({row.get('type', 'term')})")
    return "\n".join(lines)


def merge_extraction(memory: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    """Merge LLM-suggested extraction into a work memory without overriding confirmed data."""
    merged = dict(memory)
    for key in ["characters", "relations", "terms", "speechStyles", "events", "translationPolicies", "notes"]:
        merged[key] = list(merged.get(key) or [])

    for item in extraction.get("characters") or []:
        _upsert_by_name(merged["characters"], item, id_prefix="char", name_fields=("name", "canonicalName"))

    for item in extraction.get("terms") or []:
        _upsert_by_name(merged["terms"], item, id_prefix="term", name_fields=("source", "term", "name"))

    for item in extraction.get("speechStyles") or []:
        _upsert_by_name(merged["speechStyles"], item, id_prefix="speech", name_fields=("character", "name"))

    existing_relations = {_relation_key(row) for row in merged["relations"]}
    for item in extraction.get("relations") or []:
        key = _relation_key(item)
        if key == ("", "", "") or key in existing_relations:
            continue
        row = dict(item)
        row.setdefault("id", make_id("rel", "::".join(key)))
        row.setdefault("status", MEMORY_STATUS_SUGGESTED)
        row.setdefault("confidence", 0.5)
        merged["relations"].append(row)
        existing_relations.add(key)

    for item in extraction.get("events") or []:
        _upsert_by_name(merged["events"], item, id_prefix="event", name_fields=("title", "name", "summary"))

    for item in extraction.get("translationPolicies") or []:
        _upsert_by_name(merged["translationPolicies"], item, id_prefix="policy", name_fields=("source", "name"))

    merged["updatedAt"] = now_iso()
    return merged


def compact_memory_context(memory: dict[str, Any], *, include_suggested: bool = True, max_items: int = 8) -> str:
    """Render compact prompt context. Confirmed rows are strongest; suggested rows are clearly marked."""
    def useful(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        selected = []
        for row in rows:
            status = row.get("status", MEMORY_STATUS_SUGGESTED)
            if include_suggested or status == MEMORY_STATUS_CONFIRMED:
                selected.append(row)
        selected.sort(key=lambda row: 0 if row.get("status") == MEMORY_STATUS_CONFIRMED else 1)
        return selected[:max_items]

    lines: list[str] = []
    title = memory.get("title")
    if title:
        lines.append(f"작품: {title}")

    characters = useful(memory.get("characters") or [])
    if characters:
        lines.append("인물:")
        for row in characters:
            detail = ", ".join(str(v) for v in _ensure_list(row.get("traits"))[:3] if v)
            suffix = f" — {detail}" if detail else ""
            lines.append(f"- {row.get('name') or row.get('canonicalName')} ({row.get('status', MEMORY_STATUS_SUGGESTED)}){suffix}")

    relations = useful(memory.get("relations") or [])
    if relations:
        lines.append("관계:")
        for row in relations:
            lines.append(f"- {row.get('from')} ↔ {row.get('to')}: {row.get('relation')} ({row.get('status', MEMORY_STATUS_SUGGESTED)})")

    terms = useful(memory.get("terms") or [])
    if terms:
        lines.append("용어/문화 요소:")
        for row in terms:
            target = row.get("target") or row.get("translation") or row.get("recommendedTranslation")
            policy = row.get("policy") or row.get("meaning") or row.get("type")
            tail = " / ".join(str(v) for v in [target, policy] if v)
            lines.append(f"- {row.get('source') or row.get('term')}: {tail} ({row.get('status', MEMORY_STATUS_SUGGESTED)})")

    styles = useful(memory.get("speechStyles") or [])
    if styles:
        lines.append("말투/문체:")
        for row in styles:
            rules = "; ".join(str(v) for v in _ensure_list(row.get("rules"))[:3] if v)
            lines.append(f"- {row.get('character') or row.get('name')}: {rules or row.get('summary', '')} ({row.get('status', MEMORY_STATUS_SUGGESTED)})")

    if not lines:
        return "작품 메모리 없음"
    return "\n".join(lines)
