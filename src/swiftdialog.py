# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# SwiftDialog Utilities
# =============================================================================

# SF Symbol icons per category with status-based coloring
# Format: "SF=symbol_name,colour=color_name,scale=large"
CATEGORY_ICONS = {
    # Category icons (for selectable items) - large scale for visibility
    "layout_tab": "SF=doc.text.fill,colour=blue,scale=large",
    "git_worktree": "SF=arrow.triangle.branch,colour=purple,scale=large",
    "additional_repo": "SF=folder.fill,colour=green,scale=large",
    "untracked": "SF=questionmark.folder,colour=orange,scale=large",
    # Status variants
    "missing_path": "SF=folder.fill,colour=red,scale=large",
    # Header icons (for disabled category separators)
    "header_layout": "SF=doc.text,colour=gray,scale=large",
    "header_worktree": "SF=arrow.triangle.branch,colour=gray,scale=large",
    "header_repo": "SF=folder,colour=gray,scale=large",
    "header_untracked": "SF=questionmark.folder,colour=gray,scale=large",
}

# Cached SwiftDialog path (None = not checked yet, False = not found)
_swiftdialog_path_cache: str | None | bool = None


def find_swiftdialog_path() -> str | None:
    """
    Find SwiftDialog binary across Intel and Apple Silicon Homebrew paths.

    Search order:
    1. /opt/homebrew/bin/dialog (Apple Silicon Homebrew)
    2. /usr/local/bin/dialog (Intel Homebrew)
    3. shutil.which("dialog") (fallback to PATH)

    Returns:
        Path to SwiftDialog binary, or None if not found
    """
    global _swiftdialog_path_cache

    # Return cached result if already checked
    if _swiftdialog_path_cache is not None:
        return _swiftdialog_path_cache if _swiftdialog_path_cache else None

    # Search paths in order of preference
    search_paths = [
        "/opt/homebrew/bin/dialog",  # Apple Silicon Homebrew
        "/usr/local/bin/dialog",      # Intel Homebrew
    ]

    for path in search_paths:
        if Path(path).exists():
            _swiftdialog_path_cache = path
            logger.debug(
                "Found SwiftDialog",
                path=path,
                operation="find_swiftdialog_path",
            )
            return path

    # Fallback to PATH lookup
    path_result = shutil.which("dialog")
    if path_result:
        _swiftdialog_path_cache = path_result
        logger.debug(
            "Found SwiftDialog via PATH",
            path=path_result,
            operation="find_swiftdialog_path",
        )
        return path_result

    # Not found
    _swiftdialog_path_cache = False
    logger.debug(
        "SwiftDialog not found",
        searched=search_paths,
        operation="find_swiftdialog_path",
    )
    return None


def is_swiftdialog_available() -> bool:
    """Check if SwiftDialog is installed."""
    return find_swiftdialog_path() is not None


def is_homebrew_available() -> bool:
    """
    Check if Homebrew is installed and available.

    Returns:
        True if brew command is available in PATH
    """
    return shutil.which("brew") is not None


def run_swiftdialog(config: dict) -> tuple[int, dict | None]:
    """
    Run SwiftDialog with given configuration.

    Args:
        config: Dialog configuration dict (will be written as JSON)

    Returns:
        Tuple of (return_code, parsed_output_dict or None)
        Return codes:
        - 0: Button 1 clicked (e.g., "OK", "Save")
        - 2: Button 2 clicked (e.g., "Cancel")
        - 3: Info button clicked (e.g., "Rename Tabs")
        - 4: Timeout
        - Other: Error
    """
    swiftdialog_bin = find_swiftdialog_path()
    if not swiftdialog_bin:
        logger.error("SwiftDialog not available", operation="run_swiftdialog")
        return (-1, None)

    config_path = None
    # Write config to temp file
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(config, f)
            config_path = f.name

        # Run SwiftDialog
        cmd = [swiftdialog_bin, "--jsonfile", config_path, "--json"]
        logger.debug(
            "Running SwiftDialog",
            config_path=config_path,
            operation="run_swiftdialog"
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
            check=False
        )

        # Parse JSON output if available
        output_dict = None
        if result.stdout.strip():
            try:
                output_dict = json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning(
                    "Could not parse SwiftDialog output",
                    stdout=result.stdout[:200],
                    operation="run_swiftdialog"
                )

        return (result.returncode, output_dict)

    except subprocess.TimeoutExpired:
        logger.error("SwiftDialog timed out", operation="run_swiftdialog")
        return (4, None)
    except OSError as e:
        logger.error(
            "SwiftDialog OS error",
            error=str(e),
            operation="run_swiftdialog"
        )
        return (-1, None)
    finally:
        # Clean up temp file
        if config_path:
            try:
                Path(config_path).unlink(missing_ok=True)
            except OSError as e:
                logger.debug(
                    "Could not delete temp config file",
                    path=config_path,
                    error=str(e),
                    operation="run_swiftdialog"
                )


def format_tab_label(path: str, name: str, wrap_threshold: int = 50) -> str:
    """
    Format tab label as 'shorthand (path)' with shorthand name prominent.

    If path exceeds wrap_threshold characters, it wraps to a second line
    to avoid clipping by SwiftDialog's 700px checkbox area limit.

    Note: SwiftDialog checkbox area is hardcoded to 700px max width in its
    source code (dataEntryMaxWidth in MessageContentView.swift).

    Args:
        path: Directory path (will be shortened with ~ for home)
        name: Shorthand name (displayed first, prominently)
        wrap_threshold: Path length at which to wrap to second line (default 50)

    Returns:
        Formatted label string: "shorthand (path)" or "shorthand\\n(path)" if long
    """
    # Replace home directory with ~
    path_display = path.replace(str(Path.home()), "~")

    # Wrap long paths to second line to avoid clipping
    if len(path_display) > wrap_threshold:
        return f"{name}\n({path_display})"

    return f"{name} ({path_display})"
