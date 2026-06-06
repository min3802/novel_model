from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .ontology import (
    GLOSSARY_POLICY_CONTEXTUAL,
    GLOSSARY_POLICY_LOCKED,
    GLOSSARY_POLICY_PREFERRED,
    glossary_rows_for_locale,
)


@dataclass(slots=True)
class ConsistencyIssue:
    type: str
    source: str
    expected: str
    actual: str
    severity: str
    message: str


def _present_any(translated_text: str, candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate and candidate in translated_text:
            return candidate
    return ""


def check_translation_consistency(
    *,
    source_text: str,
    translated_text: str,
    locale: str,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check noun/proper-noun glossary consistency.

    The checker intentionally does not enforce verbs, adjectives, or normal
    sentence variation.  It only evaluates glossary rows from work memory:
    - locked: exact target required when target exists
    - preferred: preferred or allowed variants pass
    - contextual: reference-only, reported as skipped
    """
    issues: list[ConsistencyIssue] = []
    checked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in glossary_rows_for_locale(memory, locale):
        source = row["source"]
        if source not in source_text:
            continue
        policy = row.get("policy") or GLOSSARY_POLICY_LOCKED
        expected = row.get("target") or row.get("recommendedTranslation") or ""
        allowed = list(row.get("allowedTranslations") or [])
        if expected and expected not in allowed:
            allowed.insert(0, expected)

        if policy == GLOSSARY_POLICY_CONTEXTUAL:
            skipped.append(
                {
                    "source": source,
                    "policy": policy,
                    "reason": "contextual/reference-only term; not enforced",
                }
            )
            continue

        found = _present_any(translated_text, allowed)
        status = "pass" if found else "missing_target"
        if policy == GLOSSARY_POLICY_PREFERRED and found and expected and found != expected:
            status = "pass_with_allowed_variant"
        checked.append(
            {
                "source": source,
                "expected": expected,
                "allowed": allowed,
                "found": found,
                "policy": policy,
                "type": row.get("type", "term"),
                "status": status,
            }
        )

        if not found and expected:
            severity = "HIGH" if policy == GLOSSARY_POLICY_LOCKED else "MEDIUM"
            issues.append(
                ConsistencyIssue(
                    type="glossary_mismatch" if policy == GLOSSARY_POLICY_LOCKED else "preferred_term_missing",
                    source=source,
                    expected=expected,
                    actual="missing",
                    severity=severity,
                    message=(
                        f"Source term '{source}' appears in the Korean text, but the translation does not contain "
                        f"the expected glossary form '{expected}'."
                    ),
                )
            )

    status = "pass" if not issues else "warning"
    return {
        "status": status,
        "checked": checked,
        "skipped": skipped,
        "issues": [asdict(issue) for issue in issues],
        "summary": (
            "Glossary consistency passed for checked noun/proper-noun terms."
            if not issues
            else f"Glossary consistency found {len(issues)} issue(s)."
        ),
    }
