# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Layer 2: Tab Customization Functions
# =============================================================================


def find_layout_by_name(layouts: list[dict], name: str) -> dict | None:
    """
    Find a layout dict by name.

    Args:
        layouts: List of layout dicts from discover_layouts()
        name: Layout name to find

    Returns:
        Layout dict if found, None otherwise
    """
    for layout in layouts:
        if layout.get("name") == name:
            return layout
    return None


# =============================================================================
# SwiftDialog Integration (Modern macOS UI)
# =============================================================================

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


# Track tools we've offered to install this session (to avoid repeated prompts)
_install_offers_shown: set[str] = set()


async def offer_tool_installation(
    connection,
    window,
    tool_name: str,
    brew_package: str,
    description: str
) -> bool:
    """
    Offer to install a missing tool via Homebrew.

    Only offers once per session per tool. Requires Homebrew to be available.

    Args:
        connection: iTerm2 connection
        window: Current iTerm2 window
        tool_name: Display name of the tool (e.g., "broot")
        brew_package: Homebrew package name (e.g., "broot")
        description: Brief description of what the tool does

    Returns:
        True if installation was offered and user accepted, False otherwise
    """
    # Only offer once per session
    if tool_name in _install_offers_shown:
        return False
    _install_offers_shown.add(tool_name)

    # Check if Homebrew is available
    if not is_homebrew_available():
        logger.info(
            "Cannot offer tool installation - Homebrew not available",
            operation="offer_tool_installation",
            tool=tool_name
        )
        return False

    # Show installation offer dialog
    offer_alert = iterm2.Alert(
        f"Install {tool_name}?",
        f"{tool_name} is not installed but is configured in your layout.\n\n"
        f"{description}\n\n"
        f"Install via Homebrew?\n"
        f"Command: brew install {brew_package}",
        window_id=window.window_id
    )
    offer_alert.add_button("Install")
    offer_alert.add_button("Skip")
    response = await offer_alert.async_run(connection)

    if response == 0:  # Install
        logger.info(
            "User accepted tool installation",
            operation="offer_tool_installation",
            tool=tool_name,
            package=brew_package
        )

        try:
            # Run brew install
            result = subprocess.run(
                ["brew", "install", brew_package],
                capture_output=True,
                text=True,
                timeout=300,  # 5 min timeout for installation
                check=False
            )

            if result.returncode == 0:
                logger.info(
                    "Tool installed successfully",
                    operation="offer_tool_installation",
                    tool=tool_name,
                    status="success"
                )

                success_alert = iterm2.Alert(
                    "Installation Complete",
                    f"{tool_name} has been installed successfully.\n\n"
                    "Restart iTerm2 to use it.",
                    window_id=window.window_id
                )
                success_alert.add_button("OK")
                await success_alert.async_run(connection)
                return True
            else:
                logger.error(
                    "Tool installation failed",
                    operation="offer_tool_installation",
                    tool=tool_name,
                    status="failed",
                    returncode=result.returncode,
                    stderr=result.stderr[:500] if result.stderr else None
                )

                error_alert = iterm2.Alert(
                    "Installation Failed",
                    f"Could not install {tool_name}.\n\n"
                    f"Error: {result.stderr[:200] if result.stderr else 'Unknown error'}\n\n"
                    f"Try manually: brew install {brew_package}",
                    window_id=window.window_id
                )
                error_alert.add_button("OK")
                await error_alert.async_run(connection)
                return False

        except subprocess.TimeoutExpired:
            logger.error(
                "Tool installation timed out",
                operation="offer_tool_installation",
                tool=tool_name,
                status="timeout"
            )
            return False

    # User clicked Skip
    logger.debug(
        "User declined tool installation",
        operation="offer_tool_installation",
        tool=tool_name
    )
    return False


def show_tab_customization_swiftdialog(
    layout_tabs: list[dict],
    worktrees: list[dict],
    additional_repos: list[dict],
    untracked_folders: list[dict] | None = None,
    last_tab_selections: list[str] | None = None
) -> list[dict] | None:
    """
    Show Layer 2 checkbox dialog using SwiftDialog (modern macOS UI).

    SwiftDialog provides native macOS checkbox dialogs with proper scrolling,
    category headers, and JSON output. Much better UX for 50+ items.

    Args:
        layout_tabs: Tabs from layout config
        worktrees: Discovered worktrees
        additional_repos: Git repos not in layout
        untracked_folders: Directories without .git
        last_tab_selections: Previously selected tab names (for restoring state)

    Returns:
        List of selected tabs, or None if cancelled
    """
    import tempfile

    if untracked_folders is None:
        untracked_folders = []

    op_trace_id = str(uuid4())
    total_items = len(layout_tabs) + len(worktrees) + len(additional_repos) + len(untracked_folders)

    logger.info(
        "Showing SwiftDialog tab customization",
        operation="show_tab_customization_swiftdialog",
        status="started",
        trace_id=op_trace_id,
        metrics={
            "layout_tabs": len(layout_tabs),
            "worktrees": len(worktrees),
            "additional_repos": len(additional_repos),
            "untracked_folders": len(untracked_folders),
            "total_items": total_items
        }
    )

    # Build checkbox JSON config with categories
    # SwiftDialog supports JSON input for complex configurations
    checkboxes = []
    all_items = []  # Maps labels to tab dicts

    # Convert last_tab_selections to a set for O(1) lookup
    # Also include dir paths for matching (handles tabs without names)
    remembered_selections = set(last_tab_selections) if last_tab_selections else None

    def is_tab_selected(tab: dict, category: str) -> bool:
        """Determine if a tab should be pre-checked."""
        if remembered_selections is None:
            # No remembered selections - use category defaults
            return category in ("layout", "worktree")
        # Check if tab name or dir is in remembered selections
        name = tab.get("name", os.path.basename(tab["dir"]))
        return name in remembered_selections or tab.get("dir") in remembered_selections

    # Category: Layout Tabs
    if layout_tabs:
        checkboxes.append({
            "label": "—— Layout Tabs ——",
            "checked": False,
            "disabled": True
        })
        for tab in layout_tabs:
            label = f"{tab.get('name', os.path.basename(tab['dir']))}"
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(tab, "layout")
            })
            all_items.append({"label": label, "tab": tab, "category": "layout"})

    # Category: Worktrees
    if worktrees:
        checkboxes.append({
            "label": "—— Git Worktrees ——",
            "checked": False,
            "disabled": True
        })
        for wt in worktrees:
            label = f"{wt['name']}"
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(wt, "worktree")
            })
            all_items.append({"label": label, "tab": wt, "category": "worktree"})

    # Category: Additional Repos
    if additional_repos:
        checkboxes.append({
            "label": "—— Additional Repos ——",
            "checked": False,
            "disabled": True
        })
        for repo in additional_repos:
            label = f"{repo['name']}"
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(repo, "discovered")
            })
            all_items.append({"label": label, "tab": repo, "category": "discovered"})

    # Category: Untracked Folders - directories without .git
    if untracked_folders:
        checkboxes.append({
            "label": "—— Untracked Folders ——",
            "checked": False,
            "disabled": True
        })
        for folder in untracked_folders:
            label = f"{folder['name']}"
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(folder, "untracked")
            })
            all_items.append({"label": label, "tab": folder, "category": "untracked"})

    # Calculate dialog height as 90% of screen height
    try:
        screen = NSScreen.mainScreen()
        if screen:
            screen_height = int(screen.frame().size.height)
            dialog_height = int(screen_height * 0.90)
        else:
            dialog_height = 900  # Fallback
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(
            "Failed to get screen dimensions, using fallback height",
            operation="show_tab_customization_swiftdialog",
            error=str(e)
        )
        dialog_height = 900  # Fallback

    # Build SwiftDialog JSON config
    # Compact design: smaller fonts, no main icon, 90% screen height
    dialog_config = {
        "title": "Customize Tabs",
        "titlefont": "size=14",
        "message": f"Select tabs to open ({total_items} available):",
        "messagefont": "size=11",
        "hideicon": True,
        "checkbox": checkboxes,
        "checkboxstyle": {
            "style": "switch",
            "size": "mini"
        },
        "button1text": "Open Selected",
        "button2text": "Cancel",
        "height": str(dialog_height),
        "width": "400",
        "moveable": True,
        "ontop": True,
        "json": True
    }

    # Write config to temp file
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(dialog_config, f)
            config_path = f.name

        # Run SwiftDialog
        swiftdialog_bin = find_swiftdialog_path()
        cmd = [swiftdialog_bin, "--jsonfile", config_path, "--json"]

        logger.debug(
            "Running SwiftDialog",
            operation="show_tab_customization_swiftdialog",
            trace_id=op_trace_id,
            command=" ".join(cmd)
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout for user interaction
            check=False  # We handle return codes manually (0=OK, 2=Cancel, 4=timeout)
        )

        # Clean up temp file
        Path(config_path).unlink(missing_ok=True)

        # Check return code (0=button1/OK, 2=button2/Cancel, 4=timeout)
        if result.returncode == 2:
            logger.info(
                "SwiftDialog cancelled by user",
                operation="show_tab_customization_swiftdialog",
                status="cancelled",
                trace_id=op_trace_id
            )
            return None

        if result.returncode == 4:
            logger.warning(
                "SwiftDialog timed out",
                operation="show_tab_customization_swiftdialog",
                status="timeout",
                trace_id=op_trace_id
            )
            return None

        if result.returncode not in (0, 5):
            logger.error(
                "SwiftDialog failed",
                operation="show_tab_customization_swiftdialog",
                status="failed",
                trace_id=op_trace_id,
                return_code=result.returncode,
                stderr=result.stderr
            )
            return None

        # Parse JSON output
        try:
            output = json.loads(result.stdout) if result.stdout.strip() else {}
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse SwiftDialog JSON output",
                operation="show_tab_customization_swiftdialog",
                status="parse_error",
                trace_id=op_trace_id,
                error=str(e),
                stdout=result.stdout[:500]
            )
            return None

        # Build selected tabs list from JSON output
        # SwiftDialog returns: {"Label": true/false, ...}
        selected_tabs = []
        for item in all_items:
            label = item["label"]
            # SwiftDialog may return label directly or in a nested structure
            is_checked = output.get(label, False)
            if isinstance(is_checked, dict):
                is_checked = is_checked.get("checked", False)
            if is_checked:
                selected_tabs.append(item["tab"])

        logger.info(
            "SwiftDialog tab customization complete",
            operation="show_tab_customization_swiftdialog",
            status="success",
            trace_id=op_trace_id,
            metrics={
                "total_items": len(all_items),
                "selected_tabs": len(selected_tabs)
            }
        )

        return selected_tabs

    except subprocess.TimeoutExpired:
        logger.error(
            "SwiftDialog timed out",
            operation="show_tab_customization_swiftdialog",
            status="timeout",
            trace_id=op_trace_id
        )
        Path(config_path).unlink(missing_ok=True)
        return None

    except (OSError, subprocess.SubprocessError) as e:
        logger.error(
            "SwiftDialog execution failed",
            operation="show_tab_customization_swiftdialog",
            status="exec_error",
            trace_id=op_trace_id,
            error=str(e),
            error_type=type(e).__name__
        )
        return None


async def show_tab_customization_polymodal(
    connection,
    layout_tabs: list[dict],
    worktrees: list[dict],
    additional_repos: list[dict],
    untracked_folders: list[dict] | None = None,
    last_tab_selections: list[str] | None = None
) -> list[dict] | None:
    """
    Show Layer 2 checkbox dialog using iTerm2 PolyModalAlert (fallback).

    This is the fallback when SwiftDialog is not available.
    Limited scrolling support for 50+ items.

    Args:
        connection: iTerm2 connection
        layout_tabs: Tabs from layout config
        worktrees: Discovered worktrees
        additional_repos: Git repos not in layout
        untracked_folders: Directories without .git
        last_tab_selections: Previously selected tab names (for restoring state)

    Returns:
        List of selected tabs, or None if cancelled
    """
    if untracked_folders is None:
        untracked_folders = []

    op_trace_id = str(uuid4())

    logger.info(
        "Showing PolyModalAlert tab customization (fallback)",
        operation="show_tab_customization_polymodal",
        status="started",
        trace_id=op_trace_id,
        metrics={
            "layout_tabs": len(layout_tabs),
            "worktrees": len(worktrees),
            "additional_repos": len(additional_repos),
            "untracked_folders": len(untracked_folders)
        }
    )

    alert = iterm2.PolyModalAlert(
        title="Customize Tabs",
        subtitle="Uncheck tabs you don't want to open:"
    )

    # Build checkbox items with labels
    all_items = []

    # Convert last_tab_selections to a set for O(1) lookup
    remembered_selections = set(last_tab_selections) if last_tab_selections else None

    def is_tab_selected(tab: dict, category: str) -> int:
        """Determine if a tab should be pre-checked (returns 1 or 0)."""
        if remembered_selections is None:
            # No remembered selections - use category defaults
            return 1 if category in ("layout", "worktree") else 0
        # Check if tab name or dir is in remembered selections
        name = tab.get("name", os.path.basename(tab["dir"]))
        return 1 if (name in remembered_selections or tab.get("dir") in remembered_selections) else 0

    # Layout tabs
    for tab in layout_tabs:
        label = f"{tab.get('name', tab['dir'])} ({tab['dir']})"
        alert.add_checkbox_item(label, is_tab_selected(tab, "layout"))
        all_items.append({"label": label, "tab": tab, "category": "layout"})

    # Worktrees
    for wt in worktrees:
        label = f"{wt['name']} ({wt['dir']})"
        alert.add_checkbox_item(label, is_tab_selected(wt, "worktree"))
        all_items.append({"label": label, "tab": wt, "category": "worktree"})

    # Additional repos
    for repo in additional_repos:
        label = f"{repo['name']} ({repo['dir']})"
        alert.add_checkbox_item(label, is_tab_selected(repo, "discovered"))
        all_items.append({"label": label, "tab": repo, "category": "discovered"})

    # Untracked folders
    for folder in untracked_folders:
        label = f"{folder['name']} ({folder['dir']})"
        alert.add_checkbox_item(label, is_tab_selected(folder, "untracked"))
        all_items.append({"label": label, "tab": folder, "category": "untracked"})

    # Add buttons
    alert.add_button("Open Selected")
    alert.add_button("Cancel")

    try:
        result = await alert.async_run(connection)

        # Check if cancelled (second button)
        if result.button == "Cancel":
            logger.info(
                "Tab customization cancelled",
                operation="show_tab_customization_polymodal",
                status="cancelled",
                trace_id=op_trace_id
            )
            return None

        # Get checked labels from result.checks (list of checked label strings)
        checked_labels = set(result.checks) if result.checks else set()

        # Return tabs whose labels were checked
        selected_tabs = [item["tab"] for item in all_items if item["label"] in checked_labels]

        logger.info(
            "PolyModalAlert tab customization complete",
            operation="show_tab_customization_polymodal",
            status="success",
            trace_id=op_trace_id,
            metrics={"selected_tabs": len(selected_tabs)}
        )

        return selected_tabs

    except (iterm2.RPCException, AttributeError, TypeError, ValueError) as e:
        logger.error(
            "Failed to show PolyModalAlert dialog",
            operation="show_tab_customization_polymodal",
            status="failed",
            trace_id=op_trace_id,
            error=str(e),
            error_type=type(e).__name__
        )
        return None


async def show_tab_customization(
    connection,
    layout_tabs: list[dict],
    worktrees: list[dict],
    additional_repos: list[dict],
    untracked_folders: list[dict] | None = None,
    last_tab_selections: list[str] | None = None
) -> list[dict] | None:
    """
    Show Layer 2 checkbox dialog for tab customization.

    Uses SwiftDialog for modern macOS UI with proper scrolling and categories.
    Falls back to iTerm2 PolyModalAlert if SwiftDialog is not installed.

    Args:
        connection: iTerm2 connection
        layout_tabs: Tabs from layout config
        worktrees: Discovered worktrees
        additional_repos: Git repos not in layout
        untracked_folders: Directories without .git
        last_tab_selections: Previously selected tab names (for restoring state)

    Returns:
        List of selected tabs, or None if cancelled
    """
    if untracked_folders is None:
        untracked_folders = []

    # Prefer SwiftDialog for better UX with many items
    if is_swiftdialog_available():
        logger.debug(
            "Using SwiftDialog for tab customization",
            operation="show_tab_customization"
        )
        # SwiftDialog is synchronous (subprocess), run in executor
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            show_tab_customization_swiftdialog,
            layout_tabs,
            worktrees,
            additional_repos,
            untracked_folders,
            last_tab_selections
        )
        return result
    else:
        logger.debug(
            "SwiftDialog not available, using PolyModalAlert fallback",
            operation="show_tab_customization"
        )
        return await show_tab_customization_polymodal(
            connection,
            layout_tabs,
            worktrees,
            additional_repos,
            untracked_folders,
            last_tab_selections
        )


# =============================================================================
# Directory Management (SwiftDialog UI)
# =============================================================================


def choose_folder_native(prompt: str = "Select a folder:") -> str | None:
    """
    Show native macOS folder picker using osascript.

    Uses AppleScript to show the native folder picker dialog.
    This works outside iTerm2 sandbox since osascript runs externally.

    Args:
        prompt: Text to show in the folder picker dialog

    Returns:
        Selected folder path, or None if cancelled
    """
    # Build AppleScript command
    # Use shlex.quote to handle special characters in prompt
    applescript = f'POSIX path of (choose folder with prompt "{prompt}")'

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            timeout=120,
            check=False
        )

        if result.returncode == 0 and result.stdout.strip():
            # Remove trailing slash if present
            folder = result.stdout.strip().rstrip("/")
            logger.debug(
                "Folder selected",
                operation="choose_folder_native",
                folder=folder
            )
            return folder

        # User cancelled (returncode != 0 but no error)
        logger.debug(
            "Folder picker cancelled",
            operation="choose_folder_native"
        )
        return None

    except subprocess.TimeoutExpired:
        logger.warning(
            "Folder picker timed out",
            operation="choose_folder_native"
        )
        return None
    except OSError as e:
        logger.warning(
            "Folder picker failed",
            operation="choose_folder_native",
            error=str(e)
        )
        return None


def show_directory_management_swiftdialog(
    current_dirs: list[dict]
) -> list[dict] | None:
    """
    Show directory management dialog using SwiftDialog.

    Features:
    - Checkboxes for existing directories (unchecked = DELETE from list)
    - "Add Folder" button triggers native macOS folder picker (up to 3 per session)
    - Wider window with smaller font for full path visibility
    - All directories (including defaults) can be deleted

    Args:
        current_dirs: List of {"path": str, "enabled": bool} dicts

    Returns:
        Updated list of directory configs (only checked items), or None if cancelled
    """
    import tempfile

    op_trace_id = str(uuid4())

    # Filter to only enabled directories for display
    working_dirs = [d.copy() for d in current_dirs if d.get("enabled", True)]
    folders_added_this_session = 0
    max_folders_per_session = 3

    logger.info(
        "Showing directory management dialog",
        operation="show_directory_management",
        status="started",
        trace_id=op_trace_id,
        metrics={"current_dirs": len(working_dirs)}
    )

    # Loop to handle "Add Folder" button clicks
    while True:
        # Build checkboxes for current directories
        checkboxes = [
            {
                "label": "─── Directories (uncheck to delete) ───",
                "checked": False,
                "disabled": True,
                "icon": "SF=folder.fill,colour=blue"
            }
        ]

        for scan_dir in working_dirs:
            path = scan_dir["path"]
            expanded = Path(path).expanduser()
            exists = expanded.exists()
            icon_color = "green" if exists else "red"
            display_path = str(expanded) if not path.startswith("~") else path

            checkboxes.append({
                "label": display_path,
                "checked": True,
                "icon": f"SF=folder.fill,colour={icon_color}"
            })

        # Calculate dynamic height
        num_checkboxes = len(checkboxes)
        base_height = 160
        checkbox_height = num_checkboxes * 40
        calculated_height = base_height + checkbox_height
        dialog_height = max(300, min(700, calculated_height))

        # Determine if Add Folder button should be enabled
        can_add_more = folders_added_this_session < max_folders_per_session
        add_button_text = f"➕ Add Folder ({max_folders_per_session - folders_added_this_session} left)"

        # Build dialog config
        dialog_config = {
            "title": "Manage Scan Directories",
            "message": f"**Checked** = keep, **Unchecked** = delete.\n{len(working_dirs)} directories configured.",
            "messagefont": "size=13",
            "icon": "SF=folder.badge.gearshape,colour=blue",
            "iconsize": "50",
            "checkbox": checkboxes,
            "checkboxstyle": {
                "style": "switch",
                "size": "small"
            },
            "button1text": "Save",
            "button2text": "Cancel",
            "height": str(dialog_height),
            "width": "700",
            "moveable": True,
            "ontop": True,
            "json": True
        }

        # Add "Add Folder" button if allowed (no action - we handle return code 3)
        if can_add_more:
            dialog_config["infobuttontext"] = add_button_text

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(dialog_config, f)
                config_path = f.name

            swiftdialog_bin = find_swiftdialog_path()
            cmd = [swiftdialog_bin, "--jsonfile", config_path, "--json"]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=False
            )

            Path(config_path).unlink(missing_ok=True)

            # Return code 3 = info button clicked (Add Folder)
            if result.returncode == 3:
                logger.debug(
                    "Add Folder button clicked",
                    operation="show_directory_management",
                    trace_id=op_trace_id
                )
                # Show folder input dialog
                new_folder = choose_folder_native("Select folder to add:")
                if new_folder and Path(new_folder).expanduser().exists():
                    # Convert to ~ format
                    home = str(Path.home())
                    if new_folder.startswith(home):
                        new_folder = "~" + new_folder[len(home):]

                    # Check if already in list
                    existing_paths = {d["path"] for d in working_dirs}
                    if new_folder not in existing_paths:
                        working_dirs.append({"path": new_folder, "enabled": True})
                        folders_added_this_session += 1
                        logger.info(
                            "Folder added via native picker",
                            operation="show_directory_management",
                            trace_id=op_trace_id,
                            new_path=new_folder
                        )
                        # Return immediately with updated list (don't re-show dialog)
                        return working_dirs
                # User cancelled folder picker - return to main dialog
                continue

            # Return code 2 = Cancel
            if result.returncode == 2:
                logger.info(
                    "Directory management cancelled",
                    operation="show_directory_management",
                    status="cancelled",
                    trace_id=op_trace_id
                )
                return None

            # Return code 0 or 5 = Save
            if result.returncode not in (0, 5):
                logger.error(
                    "SwiftDialog failed",
                    operation="show_directory_management",
                    status="failed",
                    trace_id=op_trace_id,
                    return_code=result.returncode
                )
                return None

            # Parse output
            try:
                output = json.loads(result.stdout) if result.stdout.strip() else {}
            except json.JSONDecodeError:
                return None

            # Build final list - only keep checked items
            updated_dirs = []
            for scan_dir in working_dirs:
                path = scan_dir["path"]
                expanded = Path(path).expanduser()
                display_path = str(expanded) if not path.startswith("~") else path

                is_checked = output.get(display_path, False)
                if isinstance(is_checked, dict):
                    is_checked = is_checked.get("checked", False)

                if is_checked:
                    updated_dirs.append({"path": path, "enabled": True})
                else:
                    logger.info(
                        "Directory deleted",
                        operation="show_directory_management",
                        trace_id=op_trace_id,
                        deleted_path=path
                    )

            logger.info(
                "Directory management complete",
                operation="show_directory_management",
                status="success",
                trace_id=op_trace_id,
                metrics={"total_dirs": len(updated_dirs), "added": folders_added_this_session}
            )

            return updated_dirs

        except subprocess.TimeoutExpired:
            logger.error(
                "SwiftDialog timed out",
                operation="show_directory_management",
                status="timeout",
                trace_id=op_trace_id
            )
            Path(config_path).unlink(missing_ok=True)
            return None

        except (OSError, subprocess.SubprocessError) as e:
            logger.error(
                "SwiftDialog execution failed",
                operation="show_directory_management",
                status="exec_error",
                trace_id=op_trace_id,
                error=str(e)
            )
            Path(config_path).unlink(missing_ok=True)
            return None


async def show_directory_management(prefs: dict) -> dict | None:
    """
    Show directory management UI and return updated preferences.

    Uses SwiftDialog if available, otherwise shows message.

    Args:
        prefs: Current preferences dict

    Returns:
        Updated preferences dict, or None if cancelled
    """
    if not is_swiftdialog_available():
        logger.warning(
            "SwiftDialog not available for directory management",
            operation="show_directory_management"
        )
        return None

    current_dirs = prefs.get("scan_directories", DEFAULT_SCAN_DIRECTORIES.copy())

    # Run SwiftDialog in executor (non-blocking)
    loop = asyncio.get_event_loop()
    updated_dirs = await loop.run_in_executor(
        None,
        show_directory_management_swiftdialog,
        current_dirs
    )

    if updated_dirs is None:
        return None

    # Update preferences with new directories
    updated_prefs = prefs.copy()
    updated_prefs["scan_directories"] = updated_dirs

    return updated_prefs

