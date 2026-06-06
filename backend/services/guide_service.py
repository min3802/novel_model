"""Localization guide service boundary.

Keeps guide generation out of the HTTP router so frontend/API routing,
trend-guide logic, and future guide workers can evolve independently.
"""

from __future__ import annotations

from typing import Any

from data.localization_guide.platform_trend_advisor import build_localization_advice


def guide(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a localization guide response for the requested target market."""
    return build_localization_advice(payload)
