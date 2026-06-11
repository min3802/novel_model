"""Guide/report generation domain package.

This package contains the non-translation guide/report implementation used by
the backend service boundary and related scripts/tests.
"""

from .context_pack_analysis import build_context_pack_overlap_report
from .localization_pipeline import run_localization_pipeline
from .localization_mvp_pipeline import build_localization_guide_mvp
from .platform_trend_advisor import build_localization_advice, rank_countries
from .platform_trend_guide import load_trend_data
from .regulation_policy_analysis import (
    build_policy_attention_payload,
    build_policy_attention_report,
)

__all__ = [
    "build_context_pack_overlap_report",
    "build_localization_guide_mvp",
    "run_localization_pipeline",
    "build_localization_advice",
    "build_policy_attention_payload",
    "build_policy_attention_report",
    "load_trend_data",
    "rank_countries",
]
