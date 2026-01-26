# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Layout Selector Functions
# =============================================================================


def discover_layouts() -> list[dict]:
    """
    Discover available layout files in config directory.

    Scans CONFIG_DIR for files matching LAYOUT_PATTERN (layout-*.toml).

    Returns:
        List of dicts with keys: name, display, path, tab_count
        Example: [{"name": "full", "display": "full (29 tabs)",
                   "path": Path(...), "tab_count": 29}, ...]
    """
    start_time = time.perf_counter()
    layouts = []
    op_trace_id = str(uuid4())

    logger.debug(
        "Starting layout discovery",
        operation="discover_layouts",
        status="started",
        trace_id=op_trace_id,
        config_dir=str(CONFIG_DIR),
        pattern=LAYOUT_PATTERN
    )

    for path in sorted(CONFIG_DIR.glob(LAYOUT_PATTERN)):
        logger.debug(
            "Found layout file",
            operation="discover_layouts",
            trace_id=op_trace_id,
            file=path.name
        )

        # Extract display name: layout-{name}.toml -> {name}
        match = re.match(r"layout-(.+)\.toml$", path.name)
        if not match:
            logger.debug(
                "Skipping file - doesn't match pattern",
                operation="discover_layouts",
                trace_id=op_trace_id,
                file=path.name
            )
            continue

        name = match.group(1)

        # Parse file to count tabs
        try:
            with open(path, "rb") as f:
                config = tomllib.load(f)
            tab_count = len(config.get("tabs", []))

            layout = {
                "name": name,
                "display": f"{name} ({tab_count} tabs)",
                "path": path,
                "tab_count": tab_count,
            }
            layouts.append(layout)

            logger.debug(
                "Added layout",
                operation="discover_layouts",
                trace_id=op_trace_id,
                layout_name=name,
                metrics={"tab_count": tab_count}
            )

        except tomllib.TOMLDecodeError as e:
            error_context = extract_toml_error_context(e, path)
            logger.warning(
                "Skipping layout file due to invalid TOML",
                operation="discover_layouts",
                status="skip",
                trace_id=op_trace_id,
                file=path.name,
                line_number=error_context["line_number"],
                error=error_context["formatted_message"]
            )
        except (OSError, KeyError, TypeError) as e:
            logger.warning(
                "Skipping layout file due to error",
                operation="discover_layouts",
                status="skip",
                trace_id=op_trace_id,
                file=path.name,
                error=str(e),
                error_type=type(e).__name__
            )

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.debug(
        "Layout discovery complete",
        operation="discover_layouts",
        status="success",
        trace_id=op_trace_id,
        metrics={"layouts_found": len(layouts), "duration_ms": duration_ms}
    )

    return layouts


# Default directories to scan for git repos
# Empty by default for portability - users configure via Settings or first-run wizard
DEFAULT_SCAN_DIRECTORIES: list[dict[str, str | bool]] = []


def load_preferences() -> dict:
    """
    Load selector preferences from TOML file.

    Returns:
        dict with keys: remember_choice (bool), last_layout (str|None),
        scan_directories (list of {"path": str, "enabled": bool})
    """
    defaults = {
        "remember_choice": False,
        "last_layout": None,
        "scan_directories": DEFAULT_SCAN_DIRECTORIES.copy(),
    }

    if not PREFERENCES_PATH.exists():
        logger.debug(
            "Preferences file does not exist, using defaults",
            operation="load_preferences",
            status="default",
            file=str(PREFERENCES_PATH)
        )
        return defaults

    try:
        with open(PREFERENCES_PATH, "rb") as f:
            prefs = tomllib.load(f)

        result = {**defaults, **prefs}

        # Ensure scan_directories has proper structure
        if "scan_directories" not in prefs:
            result["scan_directories"] = DEFAULT_SCAN_DIRECTORIES.copy()

        logger.debug(
            "Preferences loaded successfully",
            operation="load_preferences",
            status="success",
            remember_choice=result.get("remember_choice"),
            last_layout=result.get("last_layout"),
            scan_directories_count=len(result.get("scan_directories", []))
        )
        return result

    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as e:
        logger.warning(
            "Failed to load preferences, using defaults",
            operation="load_preferences",
            status="fallback",
            file=str(PREFERENCES_PATH),
            error=str(e),
            error_type=type(e).__name__
        )
        return defaults


def atomic_write_file(path: Path, content: str) -> None:
    """
    Write file atomically using temp file → fsync → rename pattern.

    This ensures the file is never partially written, even if the system
    crashes or disk fills up during the write.

    Args:
        path: Target file path
        content: Content to write

    Raises:
        OSError: If write fails (including disk full - errno.ENOSPC)
    """
    import errno
    import tempfile

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (for atomic rename)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )

    try:
        # Write content
        with os.fdopen(temp_fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # Ensure data hits disk

        # Atomic rename
        os.rename(temp_path, path)

        logger.debug(
            "Atomic file write successful",
            operation="atomic_write_file",
            path=str(path)
        )

    except OSError as e:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError:
            pass

        # Provide clear message for disk full
        if e.errno == errno.ENOSPC:
            raise OSError(f"Disk full - cannot write to {path}") from e
        raise


def save_preferences(prefs: dict) -> None:
    """
    Save selector preferences to TOML file atomically.

    Uses atomic write pattern (temp file → fsync → rename) to prevent
    corruption from partial writes.

    Args:
        prefs: dict with remember_choice, last_layout, scan_directories keys
    """
    lines = [
        "# iTerm2 Layout Selector Preferences",
        "# Auto-generated by default-layout.py",
        "# Delete this file to reset and show selector dialog again",
        "",
        f"remember_choice = {'true' if prefs.get('remember_choice') else 'false'}",
    ]

    if prefs.get("last_layout"):
        lines.append(f'last_layout = "{prefs["last_layout"]}"')

    # Add new preference fields for Layer 2
    if prefs.get("skip_tab_customization") is not None:
        lines.append(f"skip_tab_customization = {'true' if prefs.get('skip_tab_customization') else 'false'}")

    if prefs.get("last_tab_selections"):
        # Format as TOML array
        tabs_str = ", ".join(f'"{t}"' for t in prefs["last_tab_selections"])
        lines.append(f"last_tab_selections = [{tabs_str}]")

    # Save scan directories as TOML array of tables
    scan_dirs = prefs.get("scan_directories")
    if scan_dirs:
        lines.append("")
        lines.append("# Directories to scan for git repos (auto-discovery)")
        lines.append("# Add/remove via 'Manage Directories' option in layout selector")
        for scan_dir in scan_dirs:
            lines.append("")
            lines.append("[[scan_directories]]")
            lines.append(f'path = "{scan_dir["path"]}"')
            lines.append(f"enabled = {'true' if scan_dir.get('enabled', True) else 'false'}")

    content = "\n".join(lines) + "\n"

    try:
        atomic_write_file(PREFERENCES_PATH, content)

        logger.debug(
            "Preferences saved successfully",
            operation="save_preferences",
            status="success",
            file=str(PREFERENCES_PATH),
            remember_choice=prefs.get("remember_choice"),
            last_layout=prefs.get("last_layout"),
            scan_directories_count=len(scan_dirs) if scan_dirs else 0
        )

    except OSError as e:
        logger.error(
            "Failed to save preferences - user choices may not persist",
            operation="save_preferences",
            status="failed",
            file=str(PREFERENCES_PATH),
            error=str(e)
        )


async def reset_preferences(connection, window) -> bool:
    """
    Reset selector preferences to defaults after user confirmation.

    Deletes the selector-preferences.toml file, which will cause:
    - Layout selector to show on next startup
    - Scan directories to reset to defaults
    - Remembered layout choice to be cleared

    Args:
        connection: iTerm2 connection
        window: Current iTerm2 window

    Returns:
        True if preferences were reset, False if cancelled
    """
    # Confirm with user
    confirm_alert = iterm2.Alert(
        "Reset Preferences?",
        "This will reset all layout selector preferences:\n\n"
        "• Layout selector will show on startup\n"
        "• Scan directories will be cleared\n"
        "• Tab selections will be forgotten\n\n"
        "Layout config files will NOT be deleted.",
        window_id=window.window_id
    )
    confirm_alert.add_button("Reset")
    confirm_alert.add_button("Cancel")
    response = await confirm_alert.async_run(connection)

    if response == 1:  # Cancel
        logger.debug(
            "Preference reset cancelled",
            operation="reset_preferences",
            status="cancelled"
        )
        return False

    # Delete preferences file
    try:
        if PREFERENCES_PATH.exists():
            PREFERENCES_PATH.unlink()
            logger.info(
                "Preferences reset successfully",
                operation="reset_preferences",
                status="success",
                file=str(PREFERENCES_PATH)
            )

            success_alert = iterm2.Alert(
                "Preferences Reset",
                "Preferences have been reset.\n\n"
                "Restart iTerm2 for changes to take effect.",
                window_id=window.window_id
            )
            success_alert.add_button("OK")
            await success_alert.async_run(connection)
            return True
        else:
            logger.debug(
                "No preferences file to delete",
                operation="reset_preferences",
                status="no_file"
            )
            return True

    except OSError as e:
        logger.error(
            "Failed to reset preferences",
            operation="reset_preferences",
            status="failed",
            error=str(e)
        )

        error_alert = iterm2.Alert(
            "Reset Failed",
            f"Could not delete preferences file:\n{e}",
            window_id=window.window_id
        )
        error_alert.add_button("OK")
        await error_alert.async_run(connection)
        return False

