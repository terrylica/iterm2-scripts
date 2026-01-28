# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there
# SwiftDialog utilities (CATEGORY_ICONS, find_swiftdialog_path, etc.) are in swiftdialog.py

# =============================================================================
# Dialog Functions (Tab Customization, Directory Management)
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
# Tool Installation Helpers
# =============================================================================

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


# =============================================================================
# Category Selector Dialog
# =============================================================================


def show_category_selector_dialog(
    categories: list[dict],
) -> str | None:
    """
    Show dialog to select which category to edit.

    Uses radio buttons (single selection) so user edits one category at a time.

    Args:
        categories: List of dicts with "name", "count", and "icon" keys

    Returns:
        Selected category name, or None if cancelled
    """
    if not categories:
        logger.debug("No categories to select", operation="show_category_selector_dialog")
        return None

    # Filter out empty categories
    non_empty = [c for c in categories if c.get("count", 0) > 0]
    if not non_empty:
        logger.debug("All categories are empty", operation="show_category_selector_dialog")
        return None

    # Build radio buttons for each category
    # SwiftDialog uses "selectitems" for radio buttons
    select_items = []
    for cat in non_empty:
        select_items.append({
            "title": f"{cat['name']} ({cat['count']} items)",
            "icon": cat.get("icon", "SF=folder.fill"),
        })

    dialog_config = {
        "title": "Select Category to Edit",
        "titlefont": "size=18",
        "message": "Choose a category to customize shorthand names:",
        "messagefont": "size=14",
        "appearance": "dark",
        "hideicon": True,
        "selectitems": select_items,
        "button1text": "Edit Selected",
        "button2text": "Cancel",
        "height": "350",
        "width": "600",
        "moveable": True,
        "ontop": True,
        "json": True
    }

    logger.info(
        "Showing category selector",
        operation="show_category_selector_dialog",
        category_count=len(non_empty)
    )

    return_code, output = run_swiftdialog(dialog_config)

    if return_code != 0:
        logger.debug(
            "Category selector cancelled",
            return_code=return_code,
            operation="show_category_selector_dialog"
        )
        return None

    if not output:
        logger.warning(
            "No output from category selector",
            operation="show_category_selector_dialog"
        )
        return None

    # Parse selected category from output
    # SwiftDialog returns: {"SelectedOption": "Layout Tabs (5 items)", ...}
    selected = output.get("SelectedOption", "")
    if not selected:
        # Try alternate key format
        selected = output.get("selectedOption", "")

    # Extract category name (strip the count suffix)
    # "Layout Tabs (5 items)" -> "Layout Tabs"
    category_name = selected.rsplit(" (", 1)[0] if " (" in selected else selected

    # Match back to original category names
    for cat in non_empty:
        if cat["name"] == category_name:
            logger.info(
                "Category selected",
                category=category_name,
                operation="show_category_selector_dialog"
            )
            return category_name

    logger.warning(
        "Selected category not found",
        selected=selected,
        operation="show_category_selector_dialog"
    )
    return None


# =============================================================================
# Rename Tabs Dialog (Category-based with Search)
# =============================================================================


def show_rename_tabs_dialog(
    items: list[dict],
    custom_names: dict[str, str] | None = None,
    category_name: str | None = None,
    search_filter: str | None = None
) -> dict[str, str] | None:
    """
    Show dialog to edit shorthand names for tabs.

    When category_name is provided, only shows items in that category.
    Includes search field to filter items within the category.

    Args:
        items: List of dicts with "dir"/"path", "name", and optional "category" keys
        custom_names: Existing custom name mappings (path -> name)
        category_name: If provided, filter to this category only
        search_filter: Pre-populated search filter (optional)

    Returns:
        Dict mapping path -> new_name if saved, None if cancelled
    """
    if not items:
        logger.debug("No items to rename", operation="show_rename_tabs_dialog")
        return None

    if custom_names is None:
        custom_names = {}

    # Filter by category if specified
    if category_name:
        items = [i for i in items if i.get("category") == category_name]

    if not items:
        logger.debug(
            "No items after category filter",
            category=category_name,
            operation="show_rename_tabs_dialog"
        )
        return None

    # Build text fields for each item
    textfields = []

    # Add search field at top
    textfields.append({
        "title": "Search / Filter",
        "value": search_filter or "",
        "prompt": "Type to filter items (leave empty to show all)",
        "name": "search_filter"
    })

    for item in items:
        path = item.get("dir") or item.get("path", "")
        # Use custom name if set, otherwise use item's current name
        current_name = custom_names.get(path) or item.get("name", os.path.basename(path))

        # Display path with ~ for home directory
        path_display = path.replace(str(Path.home()), "~")

        textfields.append({
            "title": path_display,
            "value": current_name,
            "prompt": "Shorthand name"
        })

    # Calculate dialog height dynamically based on screen size
    try:
        screen = NSScreen.mainScreen()
        if screen:
            screen_height = int(screen.frame().size.height)
            # Use 70% of screen height for rename dialog (less than main dialog)
            max_height = int(screen_height * 0.70)
        else:
            max_height = 700
    except (AttributeError, TypeError, ValueError):
        max_height = 700

    # Calculate needed height: base + items * per_item
    base_height = 180  # Extra for search field
    per_item_height = 55
    needed_height = base_height + len(items) * per_item_height
    dialog_height = min(needed_height, max_height)

    # Build title with category info
    title = "Rename Tabs"
    if category_name:
        title = f"Rename: {category_name}"

    dialog_config = {
        "title": title,
        "titlefont": "size=18",
        "message": f"Edit shorthand names ({len(items)} items):",
        "messagefont": "size=14",
        "appearance": "dark",
        "hideicon": True,
        "textfield": textfields,
        "button1text": "Save",
        "button2text": "Cancel",
        "infobuttontext": "Filter",  # Trigger re-filter
        "height": str(dialog_height),
        "width": "750",
        "moveable": True,
        "ontop": True,
        "json": True
    }

    logger.info(
        "Showing rename dialog",
        operation="show_rename_tabs_dialog",
        category=category_name,
        item_count=len(items),
        dialog_height=dialog_height
    )

    # Run dialog
    return_code, output = run_swiftdialog(dialog_config)

    if return_code == 3:
        # Info button clicked - user wants to filter
        # Get the search value and recursively call with filter applied
        if output:
            new_filter = output.get("search_filter", "").strip().lower()
            if new_filter:
                # Filter items by search term
                filtered_items = [
                    i for i in items
                    if new_filter in (i.get("dir") or i.get("path", "")).lower()
                    or new_filter in (i.get("name", "")).lower()
                    or new_filter in custom_names.get(
                        i.get("dir") or i.get("path", ""), ""
                    ).lower()
                ]
                if filtered_items:
                    logger.info(
                        "Applying search filter",
                        filter=new_filter,
                        matched=len(filtered_items),
                        operation="show_rename_tabs_dialog"
                    )
                    # Recursive call with filtered items
                    return show_rename_tabs_dialog(
                        filtered_items,
                        custom_names,
                        category_name,
                        new_filter
                    )
        # No valid filter, re-show same dialog
        return show_rename_tabs_dialog(items, custom_names, category_name, None)

    if return_code != 0:
        logger.debug(
            "Rename dialog cancelled",
            return_code=return_code,
            operation="show_rename_tabs_dialog"
        )
        return None

    if not output:
        logger.warning(
            "No output from rename dialog",
            operation="show_rename_tabs_dialog"
        )
        return None

    # Parse output - SwiftDialog returns text field values
    # Output format: {"<path_display>": "<value>", "search_filter": "...", ...}
    result = {}
    for item in items:
        path = item.get("dir") or item.get("path", "")
        path_display = path.replace(str(Path.home()), "~")

        if path_display in output:
            new_name = output[path_display].strip()
            if new_name:
                result[path] = new_name
            else:
                # Empty name - use basename as fallback
                result[path] = os.path.basename(path)

    logger.info(
        "Rename dialog completed",
        renamed_count=len(result),
        category=category_name,
        operation="show_rename_tabs_dialog"
    )

    return result


def show_tab_customization_swiftdialog(
    layout_tabs: list[dict],
    worktrees: list[dict],
    additional_repos: list[dict],
    untracked_folders: list[dict] | None = None,
    last_tab_selections: list[str] | None = None,
    custom_tab_names: dict[str, str] | None = None,
    on_rename_requested: Callable | None = None
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
        custom_tab_names: Dict mapping paths to custom shorthand names
        on_rename_requested: Callback when "Rename Tabs" is clicked, receives all_items

    Returns:
        List of selected tabs, or None if cancelled
    """

    if untracked_folders is None:
        untracked_folders = []

    if custom_tab_names is None:
        custom_tab_names = {}

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
            "disabled": True,
            "icon": CATEGORY_ICONS["header_layout"]
        })
        for tab in layout_tabs:
            path = tab["dir"]
            # Use custom name if set, otherwise use tab's name or basename
            name = custom_tab_names.get(path) or tab.get("name", os.path.basename(path))
            label = format_tab_label(path, name)
            # Check if path exists for status indication
            tab_path = Path(path).expanduser()
            if tab_path.exists():
                icon = CATEGORY_ICONS["layout_tab"]
            else:
                icon = CATEGORY_ICONS["missing_path"]
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(tab, "layout"),
                "icon": icon
            })
            all_items.append({"label": label, "tab": tab, "category": "layout"})

    # Category: Worktrees
    if worktrees:
        checkboxes.append({
            "label": "—— Git Worktrees ——",
            "checked": False,
            "disabled": True,
            "icon": CATEGORY_ICONS["header_worktree"]
        })
        for wt in worktrees:
            path = wt["dir"]
            name = custom_tab_names.get(path) or wt["name"]
            label = format_tab_label(path, name)
            # Check if worktree path exists
            wt_path = Path(path).expanduser()
            if wt_path.exists():
                icon = CATEGORY_ICONS["git_worktree"]
            else:
                icon = CATEGORY_ICONS["missing_path"]
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(wt, "worktree"),
                "icon": icon
            })
            all_items.append({"label": label, "tab": wt, "category": "worktree"})

    # Category: Additional Repos
    if additional_repos:
        checkboxes.append({
            "label": "—— Additional Repos ——",
            "checked": False,
            "disabled": True,
            "icon": CATEGORY_ICONS["header_repo"]
        })
        for repo in additional_repos:
            path = repo["dir"]
            name = custom_tab_names.get(path) or repo["name"]
            label = format_tab_label(path, name)
            # Check if repo path exists
            repo_path = Path(path).expanduser()
            if repo_path.exists():
                icon = CATEGORY_ICONS["additional_repo"]
            else:
                icon = CATEGORY_ICONS["missing_path"]
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(repo, "discovered"),
                "icon": icon
            })
            all_items.append({"label": label, "tab": repo, "category": "discovered"})

    # Category: Untracked Folders - directories without .git
    if untracked_folders:
        checkboxes.append({
            "label": "—— Untracked Folders ——",
            "checked": False,
            "disabled": True,
            "icon": CATEGORY_ICONS["header_untracked"]
        })
        for folder in untracked_folders:
            path = folder["dir"]
            name = custom_tab_names.get(path) or folder["name"]
            label = format_tab_label(path, name)
            # Check if folder path exists
            folder_path = Path(path).expanduser()
            if folder_path.exists():
                icon = CATEGORY_ICONS["untracked"]
            else:
                icon = CATEGORY_ICONS["missing_path"]
            checkboxes.append({
                "label": label,
                "checked": is_tab_selected(folder, "untracked"),
                "icon": icon
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
    # Wide compact design: larger fonts, tight spacing, path + shorthand labels
    dialog_config = {
        "title": "Customize Tabs",
        "titlefont": "size=18",
        "message": f"Select tabs to open ({total_items} available):",
        "messagefont": "size=14",
        "appearance": "dark",  # Force dark mode for consistent toggle colors
        "hideicon": True,
        "checkbox": checkboxes,
        "checkboxstyle": {
            "style": "switch",
            "size": "small"
        },
        "button1text": "Open Selected",
        "button2text": "Cancel",
        "infobuttontext": "Rename Tabs",  # Info button triggers rename dialog
        "height": str(dialog_height),
        "width": "900",  # Wider to accommodate path + shorthand labels
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

        # Check return code (0=button1/OK, 2=button2/Cancel, 3=info button, 4=timeout)
        if result.returncode == 2:
            logger.info(
                "SwiftDialog cancelled by user",
                operation="show_tab_customization_swiftdialog",
                status="cancelled",
                trace_id=op_trace_id
            )
            return None

        if result.returncode == 3:
            # Info button clicked - "Rename Tabs"
            logger.info(
                "Rename Tabs requested",
                operation="show_tab_customization_swiftdialog",
                status="rename_requested",
                trace_id=op_trace_id
            )
            if on_rename_requested:
                on_rename_requested(all_items)
            # Return special marker to indicate rename was requested
            return "RENAME_REQUESTED"

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
    last_tab_selections: list[str] | None = None,
    custom_tab_names: dict[str, str] | None = None,
    save_preferences_callback: Callable | None = None
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
        custom_tab_names: Dict mapping paths to custom shorthand names
        save_preferences_callback: Callback to save preferences when names change

    Returns:
        List of selected tabs, or None if cancelled
    """
    if untracked_folders is None:
        untracked_folders = []

    if custom_tab_names is None:
        custom_tab_names = {}

    # Prefer SwiftDialog for better UX with many items
    if is_swiftdialog_available():
        logger.debug(
            "Using SwiftDialog for tab customization",
            operation="show_tab_customization"
        )

        # Loop to handle rename dialog flow
        import asyncio
        from functools import partial
        loop = asyncio.get_event_loop()

        while True:
            result = await loop.run_in_executor(
                None,
                partial(
                    show_tab_customization_swiftdialog,
                    layout_tabs,
                    worktrees,
                    additional_repos,
                    untracked_folders,
                    last_tab_selections,
                    custom_tab_names,
                    None  # on_rename_requested not used - we check return value instead
                )
            )

            # Check if rename was requested
            if result == "RENAME_REQUESTED":
                # Build items list for rename dialog from all inputs
                items_to_rename = []
                for tab in layout_tabs:
                    items_to_rename.append({
                        "path": tab.get("dir", ""),
                        "name": tab.get("name", os.path.basename(tab.get("dir", "")))
                    })
                for wt in worktrees:
                    items_to_rename.append({
                        "path": wt.get("dir", ""),
                        "name": wt.get("name", "")
                    })
                for repo in additional_repos:
                    items_to_rename.append({
                        "path": repo.get("dir", ""),
                        "name": repo.get("name", "")
                    })
                for folder in untracked_folders:
                    items_to_rename.append({
                        "path": folder.get("dir", ""),
                        "name": folder.get("name", "")
                    })

                # Filter out items without paths
                items_to_rename = [i for i in items_to_rename if i["path"]]

                new_names = await loop.run_in_executor(
                    None,
                    partial(show_rename_tabs_dialog, items_to_rename, custom_tab_names)
                )

                if new_names:
                    # Update custom_tab_names with new values
                    custom_tab_names.update(new_names)

                    # Save preferences if callback provided
                    if save_preferences_callback:
                        save_preferences_callback(custom_tab_names)

                    logger.info(
                        "Tab names updated",
                        renamed_count=len(new_names),
                        operation="show_tab_customization"
                    )

                # Re-show main dialog with updated names
                continue

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
                "icon": CATEGORY_ICONS["header_repo"]
            }
        ]

        for scan_dir in working_dirs:
            path = scan_dir["path"]
            expanded = Path(path).expanduser()
            exists = expanded.exists()
            display_path = str(expanded) if not path.startswith("~") else path

            checkboxes.append({
                "label": display_path,
                "checked": True,
                "icon": CATEGORY_ICONS["additional_repo"] if exists else CATEGORY_ICONS["missing_path"]
            })

        # Calculate dynamic height
        num_checkboxes = len(checkboxes)
        base_height = 160
        checkbox_height = num_checkboxes * 40
        calculated_height = base_height + checkbox_height
        dialog_height = max(300, min(700, calculated_height))

        # Determine if Add Folder button should be enabled
        can_add_more = folders_added_this_session < max_folders_per_session
        add_button_text = f"+ Add Folder ({max_folders_per_session - folders_added_this_session} left)"

        # Build dialog config
        dialog_config = {
            "title": "Manage Scan Directories",
            "message": f"**Checked** = keep, **Unchecked** = delete.\n{len(working_dirs)} directories configured.",
            "messagefont": "size=13",
            "appearance": "dark",  # Force dark mode for consistent toggle colors
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

