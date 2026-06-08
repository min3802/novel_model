from __future__ import annotations

from pathlib import Path


def find_ancestor_containing(start: Path, relative_path: str) -> Path:
    """Return the nearest ancestor containing ``relative_path``."""
    resolved_start = Path(start).resolve()
    search_roots = [resolved_start, *resolved_start.parents]
    for root in search_roots:
        if (root / relative_path).exists():
            return root
    raise FileNotFoundError(
        f"Could not find ancestor containing {relative_path!r} from {resolved_start}"
    )


def package_project_root(start: Path | None = None) -> Path:
    """Directory that owns the pipeline package and local data files."""
    anchor = Path(start or __file__).resolve()
    return find_ancestor_containing(anchor, "app/translation")


def repository_root(start: Path | None = None) -> Path:
    """Repository/workspace root containing shared prompts."""
    anchor = Path(start or __file__).resolve()
    return find_ancestor_containing(anchor, "prompts/cultural_review")


def cultural_review_prompt_root(start: Path | None = None) -> Path:
    return repository_root(start) / "prompts" / "cultural_review"
