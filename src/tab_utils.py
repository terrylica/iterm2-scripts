# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Tab Utilities
# =============================================================================
# Centralized utilities for tab data handling to ensure consistency across
# all modules. This prevents bugs where display names, paths, or other tab
# properties are computed differently in different parts of the codebase.


def normalize_tab_path(path: str) -> str:
    """Normalize a tab directory path for consistent comparison.

    Expands ~ and resolves symlinks, then strips trailing slashes.
    Use this whenever comparing tab paths for equality.

    Args:
        path: Raw path string (may contain ~ or be relative).

    Returns:
        Absolute normalized path suitable for comparison.
    """
    return os.path.realpath(os.path.expanduser(path)).rstrip("/")


def expand_tab_path(path: str) -> str:
    """Expand ~ in a tab path without resolving symlinks.

    Use this when you need the actual filesystem path but want to
    preserve symlink structure (e.g., for display or cd commands).

    Args:
        path: Raw path string (may contain ~).

    Returns:
        Path with ~ expanded.
    """
    return os.path.expanduser(path)


def get_tab_display_name(
    tab: dict,
    custom_tab_names: dict[str, str] | None = None,
) -> str:
    """Get the display name for a tab with consistent priority.

    This is the SINGLE SOURCE OF TRUTH for tab display names.
    All code that needs to display a tab name should call this function.

    Priority order:
    1. custom_tab_names[dir] - User's custom shorthand name
    2. tab["name"] - Name from workspace config
    3. basename(dir) - Directory name as fallback

    Args:
        tab: Tab configuration dict (must have "dir" key, may have "name").
        custom_tab_names: Optional mapping of dir paths to custom names.

    Returns:
        Display name string for the tab.
    """
    custom_tab_names = custom_tab_names or {}
    path = tab.get("dir", "")
    return (
        custom_tab_names.get(path)
        or tab.get("name")
        or os.path.basename(expand_tab_path(path))
    )


def get_tab_dir(tab: dict) -> str:
    """Get the directory path from a tab config dict.

    Handles both "dir" and legacy "path" keys for compatibility.

    Args:
        tab: Tab configuration dict.

    Returns:
        Directory path string (may contain ~, not expanded).
    """
    return tab.get("dir") or tab.get("path", "")
