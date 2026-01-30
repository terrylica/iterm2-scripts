# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Tab Detection
# =============================================================================


async def get_open_tab_directories(window) -> set[str]:
    """Return normalized directory paths of all sessions in the current window.

    Queries each session's ``path`` variable via the iTerm2 Python API.
    Paths are resolved through ``os.path.realpath`` so symlinks and
    trailing slashes are handled consistently.

    Args:
        window: iTerm2 Window object (current terminal window).

    Returns:
        Set of absolute directory paths currently open in the window.
    """
    open_dirs: set[str] = set()
    for tab in window.tabs:
        for session in tab.sessions:
            try:
                path = await session.async_get_variable("path")
            except (iterm2.RPCException, AttributeError, TypeError):
                logger.debug(
                    "Could not query session path",
                    session_id=getattr(session, "session_id", "unknown"),
                )
                continue
            if path:
                normalized = os.path.realpath(path).rstrip("/")
                open_dirs.add(normalized)
    return open_dirs


def filter_already_open_tabs(
    all_tabs: list[dict], open_dirs: set[str]
) -> tuple[list[dict], list[str]]:
    """Filter out tabs whose directories are already open.

    Args:
        all_tabs: List of tab config dicts (must have "dir" key).
        open_dirs: Set of normalized directory paths already open.

    Returns:
        Tuple of (tabs_to_create, skipped_tab_names).
    """
    tabs_to_create: list[dict] = []
    tabs_skipped: list[str] = []

    for tab_config in all_tabs:
        tab_dir = tab_config.get("dir", "")
        expanded = os.path.realpath(os.path.expanduser(tab_dir)).rstrip("/")
        if expanded in open_dirs:
            tab_name = tab_config.get("name") or os.path.basename(expanded)
            tabs_skipped.append(tab_name)
            logger.info(
                "Tab skipped - already open",
                tab_name=tab_name,
                tab_dir=tab_dir,
            )
        else:
            tabs_to_create.append(tab_config)

    if tabs_skipped:
        logger.info(
            f"Skipped {len(tabs_skipped)} already-open tab(s)",
            skipped=tabs_skipped,
            creating=len(tabs_to_create),
        )

    return tabs_to_create, tabs_skipped


async def reorder_window_tabs(window, desired_order: list[str]) -> None:
    """Reorder all tabs in a window to match the desired directory order.

    Uses ``window.async_set_tabs()`` to rearrange already-open tabs.
    Tabs not matching any entry in ``desired_order`` are appended at the end.

    Args:
        window: iTerm2 Window object.
        desired_order: List of directory paths in desired tab order.
    """
    # Build map: normalized dir path → Tab object
    dir_to_tab: dict[str, object] = {}
    for tab in window.tabs:
        for session in tab.sessions:
            try:
                path = await session.async_get_variable("path")
            except (iterm2.RPCException, AttributeError, TypeError):
                continue
            if path:
                normalized = os.path.realpath(path).rstrip("/")
                if normalized not in dir_to_tab:
                    dir_to_tab[normalized] = tab
                break  # Use first session's path per tab

    # Build ordered tab list
    ordered_tabs: list[object] = []
    used_tabs: set[str] = set()  # Track tab_ids to avoid duplicates

    for dir_path in desired_order:
        normalized = os.path.realpath(os.path.expanduser(dir_path)).rstrip("/")
        tab = dir_to_tab.get(normalized)
        if tab and tab.tab_id not in used_tabs:
            ordered_tabs.append(tab)
            used_tabs.add(tab.tab_id)

    # Append remaining tabs not in desired_order
    for tab in window.tabs:
        if tab.tab_id not in used_tabs:
            ordered_tabs.append(tab)
            used_tabs.add(tab.tab_id)

    if len(ordered_tabs) > 1:
        try:
            await window.async_set_tabs(ordered_tabs)
            logger.info(
                "Window tabs reordered",
                operation="reorder_window_tabs",
                tab_count=len(ordered_tabs),
            )
        except (iterm2.RPCException, AttributeError, TypeError) as e:
            logger.warning(
                "Failed to reorder window tabs",
                operation="reorder_window_tabs",
                error=str(e),
            )
