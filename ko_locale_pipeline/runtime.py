from __future__ import annotations

import os


TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def is_mock_mode() -> bool:
    """Return whether service-level code should use deterministic fake adapters."""
    return os.getenv("WLIGHTER_MOCK_MODE", "true").lower() in TRUE_VALUES
