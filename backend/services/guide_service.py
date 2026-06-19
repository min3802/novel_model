"""Thin adapter for the localization guide pipeline."""

from __future__ import annotations

from typing import Any

from app.guide import generate_guide


def guide(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a localization guide response for the requested payload."""
    return generate_guide(payload)
