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
