from __future__ import annotations

from typing import Any

from .terminology import (
    TERMINOLOGY_POLICY_CONTEXTUAL,
    TERMINOLOGY_POLICY_LOCKED,
    TERMINOLOGY_POLICY_PREFERRED,
    TerminologyIssue,
    issue_to_dict,
    present_any,
    terminology_rows_for_locale,
)


def check_translation_consistency(
    *,
    source_text: str,
    translated_text: str,
    locale: str,
    memory: dict[str, Any] | list[dict[str, Any]] | None = None,
    terminology: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check noun/proper-noun terminology consistency only.

    This intentionally ignores verbs, adjectives, idiomatic phrasing, and normal
    sentence variation. It evaluates only explicit terminology/glossary rows:
    - locked: exact target required when the source noun/proper noun appears
    - preferred: target or allowed variants pass
    - contextual: reference-only, skipped from enforcement
    """
    terms = terminology if terminology is not None else memory
    issues: list[TerminologyIssue] = []
    checked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in terminology_rows_for_locale(terms, locale):
        source = row["source"]
        if source not in source_text:
            continue
        policy = row.get("policy") or TERMINOLOGY_POLICY_LOCKED
        expected = row.get("target") or row.get("recommendedTranslation") or ""
        allowed = list(row.get("allowedTranslations") or [])
        if expected and expected not in allowed:
            allowed.insert(0, expected)

        if policy == TERMINOLOGY_POLICY_CONTEXTUAL:
            skipped.append(
                {
                    "source": source,
                    "policy": policy,
                    "reason": "contextual/reference-only noun term; not enforced",
                }
            )
            continue
        if not expected and not allowed:
            skipped.append(
                {
                    "source": source,
                    "policy": policy,
                    "reason": "no confirmed target translation; candidate only",
                }
            )
            continue

        found = present_any(translated_text, allowed)
        status = "pass" if found else "missing_target"
        if policy == TERMINOLOGY_POLICY_PREFERRED and found and expected and found != expected:
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

        if not found:
            severity = "HIGH" if policy == TERMINOLOGY_POLICY_LOCKED else "MEDIUM"
            issues.append(
                TerminologyIssue(
                    type="terminology_mismatch" if policy == TERMINOLOGY_POLICY_LOCKED else "preferred_term_missing",
                    source=source,
                    expected=expected or ", ".join(allowed),
                    actual="missing",
                    severity=severity,
                    message=(
                        f"Source noun/proper noun '{source}' appears in the original text, but the translation does not contain "
                        f"the expected terminology form '{expected or ', '.join(allowed)}'."
                    ),
                )
            )

    status = "pass" if not issues else "warning"
    return {
        "status": status,
        "checked": checked,
        "skipped": skipped,
        "issues": [issue_to_dict(issue) for issue in issues],
        "summary": (
            "Terminology consistency passed for checked noun/proper-noun terms."
            if not issues
            else f"Terminology consistency found {len(issues)} issue(s)."
        ),
    }
