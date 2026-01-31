# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there
# SwiftDialog utilities (CATEGORY_ICONS, find_swiftdialog_path, etc.) are in swiftdialog.py

# =============================================================================
# Dialog Functions (Tab Customization, Directory Management)
# =============================================================================
# Shared Helpers
# =============================================================================
# Note: get_tab_display_name() and related utilities are in tab_utils.py
# to ensure consistent tab name resolution across the entire codebase.

# Target width for header labels (dynamically padded)
# 40 chars - balanced width that fits single line with 📌 emoji prefix
HEADER_TARGET_WIDTH = 40


def _make_header_label(text: str, char: str, target_width: int = HEADER_TARGET_WIDTH) -> str:
    """Create a centered header label with dynamic padding.

    Args:
        text: The header text (e.g., "LAYOUT TABS", "EON/ (34)")
        char: The padding character (e.g., "▓" for L1, "═" for L2)
        target_width: Total target width for the header

    Returns:
        Centered header string padded to target width.
    """
    content = f"  {text}  "
    available = target_width - len(content)
    if available <= 0:
        return content
    left_pad = available // 2
    right_pad = available - left_pad
    return char * left_pad + content + char * right_pad


def _get_max_dialog_height(screen_percent: float = 0.90, fallback: int = 900) -> int:
    """Get maximum dialog height as a percentage of screen height."""
    try:
        screen = NSScreen.mainScreen()
        if screen:
            return int(screen.frame().size.height * screen_percent)
    except (AttributeError, TypeError, ValueError):
        pass
    return fallback


def _is_tab_selected(
    tab: dict,
    category: str,
    remembered_selections: set[str] | None,
    custom_tab_names: dict[str, str] | None = None,
) -> bool:
    """Determine if a tab should be pre-checked based on remembered selections."""
    if remembered_selections is None:
        return category in ("layout", "worktree")
    name = get_tab_display_name(tab, custom_tab_names)
    return name in remembered_selections or get_tab_dir(tab) in remembered_selections


def _build_category_checkboxes(
    items: list[dict],
    category_key: str,
    header_label: str,
    header_icon: str,
    item_icon: str,
    custom_tab_names: dict[str, str],
    remembered_selections: set[str] | None,
) -> tuple[list[dict], list[dict]]:
    """Build checkbox entries and item metadata for a category.

    Returns:
        Tuple of (checkboxes list for SwiftDialog, all_items metadata list).
    """
    if not items:
        return [], []

    checkboxes = [
        {"label": header_label, "checked": False, "disabled": True, "icon": header_icon}
    ]
    all_items = []

    for tab in items:
        path = get_tab_dir(tab)
        name = get_tab_display_name(tab, custom_tab_names)
        label = format_tab_label(path, name)

        tab_path = Path(path).expanduser()
        icon = item_icon if tab_path.exists() else CATEGORY_ICONS["missing_path"]

        checkboxes.append({
            "label": label,
            "checked": _is_tab_selected(tab, category_key, remembered_selections, custom_tab_names),
            "icon": icon,
        })
        all_items.append({"label": label, "tab": tab, "category": category_key})

    return checkboxes, all_items


def _build_grouped_category_checkboxes(
    items: list[dict],
    category_key: str,
    header_label: str,
    header_icon: str,
    item_icon: str,
    custom_tab_names: dict[str, str],
    remembered_selections: set[str] | None,
) -> tuple[list[dict], list[dict]]:
    """Build checkbox entries grouped by parent directory.

    Similar to _build_category_checkboxes but groups items by their parent
    directory (e.g., ~/eon/, ~/fork-tools/) with sub-headers.

    Returns:
        Tuple of (checkboxes list for SwiftDialog, all_items metadata list).
    """
    if not items:
        return [], []

    # Group items by parent directory
    groups: dict[str, list[dict]] = {}
    for tab in items:
        path = get_tab_dir(tab)
        expanded = Path(path).expanduser()
        # Use full parent path for grouping key to handle same-name dirs
        parent_key = str(expanded.parent)
        if parent_key not in groups:
            groups[parent_key] = []
        groups[parent_key].append(tab)

    # Sort groups by parent directory name, then sort items within each group
    sorted_groups = sorted(groups.items(), key=lambda x: Path(x[0]).name.lower())

    checkboxes = [
        {"label": header_label, "checked": False, "disabled": True, "icon": header_icon}
    ]
    all_items = []

    for parent_path, group_items in sorted_groups:
        # Add sub-header for this parent directory with double-line box drawing
        parent_name = Path(parent_path).name.upper()
        count = len(group_items)
        # Use double-line ═ for Level 2 with dynamic padding to target width
        sub_header = _make_header_label(f"{parent_name}/ ({count})", "═")
        checkboxes.append({
            "label": sub_header,
            "checked": False,
            "disabled": True,
            "icon": "SF=folder.fill.badge.gearshape",
        })

        # Sort items within group alphabetically by display name
        group_items.sort(key=lambda t: get_tab_display_name(t, custom_tab_names).lower())

        for tab in group_items:
            path = get_tab_dir(tab)
            name = get_tab_display_name(tab, custom_tab_names)
            label = format_tab_label(path, name)

            tab_path = Path(path).expanduser()
            icon = item_icon if tab_path.exists() else CATEGORY_ICONS["missing_path"]

            checkboxes.append({
                "label": label,
                "checked": _is_tab_selected(tab, category_key, remembered_selections, custom_tab_names),
                "icon": icon,
            })
            all_items.append({"label": label, "tab": tab, "category": category_key})

    return checkboxes, all_items


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

    # Build checkboxes for each category (switch style for visual clarity)
    checkboxes = []
    for cat in non_empty:
        checkboxes.append({
            "label": f"{cat['name']} ({cat['count']} items)",
            "icon": cat.get("icon", "SF=folder.fill"),
            "checked": False
        })

    # Height: ~140px overhead + ~40px per checkbox item
    dialog_height = 140 + len(non_empty) * 40

    dialog_config = {
        "title": "Select Category to Edit",
        "titlefont": "size=18",
        "message": "Choose a category to customize shorthand names:",
        "messagefont": "size=14",
        "appearance": "dark",
        "hideicon": True,
        "checkbox": checkboxes,
        "checkboxstyle": {"style": "switch", "size": "regular"},
        "button1text": "Edit Selected",
        "button2text": "Cancel",
        "height": str(dialog_height),
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

    # Parse selected category from checkbox output
    # SwiftDialog returns: {"Layout Tabs (5 items)": true, "Git Worktrees (3 items)": false, ...}
    for label, selected in output.items():
        if selected:
            # Extract category name (strip the count suffix)
            # "Layout Tabs (5 items)" -> "Layout Tabs"
            category_name = label.rsplit(" (", 1)[0] if " (" in label else label

            # Match back to original category names
            for cat in non_empty:
                if cat["name"] == category_name:
                    logger.info(
                        "Category selected",
                        category=category_name,
                        operation="show_category_selector_dialog"
                    )
                    return category_name

    logger.debug(
        "No category selected",
        operation="show_category_selector_dialog"
    )
    return None


# =============================================================================
# Rename Tabs Dialog (Category-based with Search)
# =============================================================================


def show_rename_tabs_dialog(
    items: list[dict],
    custom_names: dict[str, str] | None = None,
    category_name: str | None = None
) -> dict[str, str] | None:
    """
    Show dialog to edit shorthand names for tabs.

    When category_name is provided, only shows items in that category.

    SwiftDialog textfields are NOT scrollable (TextEntryView uses plain VStack,
    no NSScrollView). Height is calculated explicitly to fit all fields.
    If items exceed screen capacity, they are paginated automatically.

    Height formula: message_overhead(200) + items * per_item(45) + buttons(60).
    Message overhead covers title bar + explanatory message text area.
    The message area always occupies space in SwiftDialog's layout, so we fill
    it with explanatory text rather than leaving it as a blank gap.

    Args:
        items: List of dicts with "dir"/"path", "name", and optional "category" keys
        custom_names: Existing custom name mappings (path -> name)
        category_name: If provided, filter to this category only

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

    # Height calculation constants
    # SwiftDialog textfields: ~45px per field (measured empirically)
    # Message area: ~200px (title bar + explanatory text + padding)
    # Buttons: ~60px (Cancel + Save row)
    per_item_height = 45
    message_overhead = 200
    buttons_height = 60

    max_dialog_height = _get_max_dialog_height(0.80)

    max_items_per_page = max(
        (max_dialog_height - message_overhead - buttons_height) // per_item_height, 3
    )

    # Paginate if items exceed screen capacity
    # Navigation: Next (button1, rc=0), Cancel (button2, rc=2), Back (info button, rc=3)
    all_results = {}
    total_items = len(items)
    total_pages = (total_items + max_items_per_page - 1) // max_items_per_page
    current_page = 0  # 0-indexed

    # Explanatory message fills the message area that SwiftDialog always
    # allocates. Without text, this area appears as a blank gap.
    message_text = (
        "Each row shows a directory path on the left and its "
        "short name on the right.\n\n"
        "The short name is what you will see in the iTerm2 tab bar. "
        "By default, it uses the folder name (e.g. \"repo-00\"). "
        "You can change it to anything you like \u2014 for example, "
        "rename \"my-long-project-name\" to \"MLPN\" so the tab is "
        "easier to read at a glance.\n\n"
        "Changes are saved to your preferences and persist across "
        "iTerm2 restarts."
    )

    while 0 <= current_page < total_pages:
        start = current_page * max_items_per_page
        end = min(start + max_items_per_page, total_items)
        page_items = items[start:end]
        page_num = current_page + 1  # 1-indexed for display

        # Build text fields — use previously-edited values from all_results
        textfields = []
        for item in page_items:
            path = item.get("dir") or item.get("path", "")
            # Priority: edits from this session > saved custom names > item name
            current_name = (
                all_results.get(path)
                or custom_names.get(path)
                or item.get("name", os.path.basename(path))
            )
            path_display = path.replace(str(Path.home()), "~")

            textfields.append({
                "title": path_display,
                "value": current_name,
                "prompt": "Shorthand"
            })

        # Build title with category and page info
        title = "Rename Tabs"
        if category_name:
            title = f"Rename: {category_name}"
        title = f"{title} ({total_items} items)"
        if total_pages > 1:
            title = f"{title} \u2014 Page {page_num}/{total_pages}"

        # Calculate exact height for this page's content
        dialog_height = message_overhead + len(page_items) * per_item_height + buttons_height

        # Button layout:
        #   button1 (rc=0): "Next" on non-last pages, "Save" on last page
        #   button2 (rc=2): "Cancel" always
        #   infobuttontext (rc=3): "Back" on pages after the first
        is_last_page = page_num >= total_pages
        button1 = "Save" if is_last_page else "Next"

        dialog_config = {
            "title": title,
            "titlefont": "size=16",
            "message": message_text,
            "messagefont": "size=15",
            "messagealignment": "left",
            "appearance": "dark",
            "hideicon": True,
            "textfield": textfields,
            "button1text": button1,
            "button2text": "Cancel",
            "height": str(dialog_height),
            "width": "700",
            "moveable": True,
            "ontop": True,
            "json": True
        }

        # Add Back button on pages after the first
        if current_page > 0:
            dialog_config["infobuttontext"] = "Back"

        logger.info(
            "Showing rename dialog",
            operation="show_rename_tabs_dialog",
            category=category_name,
            item_count=len(page_items),
            page=page_num,
            total_pages=total_pages,
            dialog_height=dialog_height
        )

        # Run dialog
        return_code, output = run_swiftdialog(dialog_config)

        # Collect edits from this page regardless of navigation direction
        if output:
            for item in page_items:
                path = item.get("dir") or item.get("path", "")
                path_display = path.replace(str(Path.home()), "~")
                if path_display in output:
                    new_name = output[path_display].strip()
                    if new_name:
                        all_results[path] = new_name
                    else:
                        all_results[path] = os.path.basename(path)

        if return_code == 0:
            # Next / Save pressed
            if is_last_page:
                break  # Save and exit
            current_page += 1
        elif return_code == 3:
            # Back (info button) pressed
            current_page = max(0, current_page - 1)
        else:
            # Cancel (rc=2) or other
            logger.debug(
                "Rename dialog cancelled",
                return_code=return_code,
                page=page_num,
                operation="show_rename_tabs_dialog"
            )
            return all_results if all_results else None

    logger.info(
        "Rename dialog completed",
        renamed_count=len(all_results),
        category=category_name,
        operation="show_rename_tabs_dialog"
    )

    return all_results if all_results else None


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
    checkboxes = []
    all_items = []
    remembered_selections = set(last_tab_selections) if last_tab_selections else None

    # Build category checkboxes using shared helpers
    # Level 1 headers use 📌 emoji + block characters (▓) for visual impact
    # Layout tabs and worktrees use flat list
    flat_categories = [
        (layout_tabs, "layout", f"📌 {_make_header_label('LAYOUT TABS', '▓')}",
         CATEGORY_ICONS["header_layout"], CATEGORY_ICONS["layout_tab"]),
        (worktrees, "worktree", f"📌 {_make_header_label('GIT WORKTREES', '▓')}",
         CATEGORY_ICONS["header_worktree"], CATEGORY_ICONS["git_worktree"]),
    ]
    for items, cat_key, header, header_icon, item_icon in flat_categories:
        cat_checkboxes, cat_items = _build_category_checkboxes(
            items, cat_key, header, header_icon, item_icon,
            custom_tab_names, remembered_selections,
        )
        checkboxes.extend(cat_checkboxes)
        all_items.extend(cat_items)

    # Additional repos grouped by parent directory (alphabetically: eon, fork-tools, own)
    # Level 1 header with 📌 emoji, Level 2 sub-headers use ═ without emoji
    repo_checkboxes, repo_items = _build_grouped_category_checkboxes(
        additional_repos, "discovered", f"📌 {_make_header_label('ADDITIONAL REPOS', '▓')}",
        CATEGORY_ICONS["header_repo"], CATEGORY_ICONS["additional_repo"],
        custom_tab_names, remembered_selections,
    )
    checkboxes.extend(repo_checkboxes)
    all_items.extend(repo_items)

    # Untracked folders use flat list with 📌 emoji
    untracked_checkboxes, untracked_items = _build_category_checkboxes(
        untracked_folders, "untracked", f"📌 {_make_header_label('UNTRACKED FOLDERS', '▓')}",
        CATEGORY_ICONS["header_untracked"], CATEGORY_ICONS["untracked"],
        custom_tab_names, remembered_selections,
    )
    checkboxes.extend(untracked_checkboxes)
    all_items.extend(untracked_items)

    dialog_height = _get_max_dialog_height(0.90)

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
            "size": "regular"
        },
        "button1text": "Open Selected",
        "button2text": "Back",  # Returns to workspace selector
        "infobuttontext": "Rename Tabs",  # Info button triggers rename dialog
        "height": str(dialog_height),
        "width": "750",  # Match SwiftDialog's 700px checkbox area + padding
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

        # Check return code (0=button1/OK, 2=button2/Back, 3=info button, 4=timeout)
        if result.returncode == 2:
            logger.info(
                "Back to selector requested",
                operation="show_tab_customization_swiftdialog",
                status="back",
                trace_id=op_trace_id
            )
            return "BACK_TO_SELECTOR"

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
    remembered_selections = set(last_tab_selections) if last_tab_selections else None

    # PolyModalAlert uses simple label format and int (0/1) for checked state
    poly_categories = [
        (layout_tabs, "layout"),
        (worktrees, "worktree"),
        (additional_repos, "discovered"),
        (untracked_folders, "untracked"),
    ]
    for items, cat_key in poly_categories:
        for tab in items:
            label = f"{tab.get('name', tab.get('dir', ''))} ({tab.get('dir', '')})"
            checked = 1 if _is_tab_selected(tab, cat_key, remembered_selections) else 0
            alert.add_checkbox_item(label, checked)
            all_items.append({"label": label, "tab": tab, "category": cat_key})

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
                # Build items list with category tags for all inputs
                # Use get_tab_display_name for consistent name resolution
                items_to_rename = []
                category_sources = [
                    (layout_tabs, "Layout Tabs"),
                    (worktrees, "Git Worktrees"),
                    (additional_repos, "Additional Repos"),
                    (untracked_folders, "Untracked Folders"),
                ]
                for source_list, category_name in category_sources:
                    for tab in source_list:
                        items_to_rename.append({
                            "dir": get_tab_dir(tab),
                            "name": get_tab_display_name(tab, custom_tab_names),
                            "category": category_name,
                        })

                # Filter out items without paths
                items_to_rename = [i for i in items_to_rename if i.get("dir")]

                # Build category list with counts
                from collections import Counter
                category_counts = Counter(i["category"] for i in items_to_rename)
                categories = [
                    {
                        "name": "Layout Tabs",
                        "count": category_counts.get("Layout Tabs", 0),
                        "icon": CATEGORY_ICONS["layout_tab"]
                    },
                    {
                        "name": "Git Worktrees",
                        "count": category_counts.get("Git Worktrees", 0),
                        "icon": CATEGORY_ICONS["git_worktree"]
                    },
                    {
                        "name": "Additional Repos",
                        "count": category_counts.get("Additional Repos", 0),
                        "icon": CATEGORY_ICONS["additional_repo"]
                    },
                    {
                        "name": "Untracked Folders",
                        "count": category_counts.get("Untracked Folders", 0),
                        "icon": CATEGORY_ICONS["untracked"]
                    },
                ]

                # Show category selector
                selected_category = await loop.run_in_executor(
                    None,
                    partial(show_category_selector_dialog, categories)
                )

                if selected_category:
                    # Show rename dialog filtered to selected category
                    new_names = await loop.run_in_executor(
                        None,
                        partial(
                            show_rename_tabs_dialog,
                            items_to_rename,
                            custom_tab_names,
                            selected_category  # category_name filter
                        )
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
                            category=selected_category,
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
# Tab Reorder Dialog
# =============================================================================


def show_tab_reorder_dialog(
    tabs: list[dict],
    custom_tab_names: dict[str, str] | None = None,
) -> list[dict] | None:
    """
    Show a dialog to reorder selected tabs before opening.

    Uses SwiftDialog text fields with numeric ordering. The user assigns
    numbers to each tab, clicks Sort to preview the new order (dialog
    re-launches with reordered tabs), and clicks Finalize to commit.

    Args:
        tabs: List of tab dicts (must have "dir" key, optional "name")
        custom_tab_names: Dict mapping paths to custom shorthand names

    Returns:
        Reordered list of tab dicts, or None if cancelled
    """
    if not tabs or len(tabs) <= 1:
        return tabs  # Nothing to reorder

    if custom_tab_names is None:
        custom_tab_names = {}

    current = list(tabs)
    iteration = 0

    while True:
        # Build select dropdowns — 10x range with defaults at 10, 20, 30...
        # Gives 9 slots between each tab for free insertion without conflicts
        count = len(current)
        max_val = count * 10
        values = [str(n) for n in range(1, max_val + 1)]
        selectitems = []
        for i, tab in enumerate(current):
            name = get_tab_display_name(tab, custom_tab_names)
            selectitems.append({
                "title": name,
                "values": values,
                "default": str((i + 1) * 10),
            })

        if iteration == 0:
            msg = (
                "Set tab order using dropdowns, then click **Sort** to preview.\\n"
                "Click **Finalize** to open tabs in the current order."
            )
            button1 = "Sort"
        else:
            msg = (
                "Tabs re-sorted. Adjust and **Sort** again, "
                "or click **Finalize** to apply this order."
            )
            button1 = "Sort Again"

        dialog_config = {
            "title": "Tab Order",
            "titlefont": "size=18",
            "message": msg,
            "messagefont": "size=14",
            "appearance": "dark",
            "hideicon": True,
            "selectitems": selectitems,
            "button1text": button1,
            "button2text": "Cancel",
            "infobuttontext": "Finalize",
            "width": "750",
            "height": str(160 + 50 * count),
            "moveable": True,
            "ontop": True,
            "json": True,
        }

        return_code, output = run_swiftdialog(dialog_config)

        if return_code == 0:
            # Sort button (button1) — reorder and re-show
            if output:
                current = _reorder_tabs_by_numbers(current, custom_tab_names, output)
            iteration += 1
            logger.info(
                "Tab reorder preview",
                operation="show_tab_reorder_dialog",
                iteration=iteration,
                order=[get_tab_display_name(t, custom_tab_names) for t in current],
            )
            continue

        elif return_code == 3:
            # Finalize (info button) — commit current order
            logger.info(
                "Tab order finalized",
                operation="show_tab_reorder_dialog",
                iterations=iteration,
                final_order=[get_tab_display_name(t, custom_tab_names) for t in current],
            )
            return current

        else:
            # Cancel (rc=2) or other
            logger.debug(
                "Tab reorder cancelled",
                return_code=return_code,
                operation="show_tab_reorder_dialog",
            )
            return None


def _reorder_tabs_by_numbers(
    tabs: list[dict],
    custom_tab_names: dict[str, str],
    output: dict,
) -> list[dict]:
    """Sort tabs by the numeric values from the reorder dialog output."""
    pairs = []
    for tab in tabs:
        name = get_tab_display_name(tab, custom_tab_names)
        raw = output.get(name, "999")
        # Handle both textfield ("3") and selectitems ({"selectedValue": "3"})
        if isinstance(raw, dict):
            raw = raw.get("selectedValue", "999")
        try:
            num = int(raw)
        except (ValueError, TypeError):
            num = 999
        pairs.append((num, tab))

    pairs.sort(key=lambda x: x[0])
    return [tab for _, tab in pairs]
