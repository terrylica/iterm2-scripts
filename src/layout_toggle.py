# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Workspace Management
# =============================================================================


def show_manage_layouts_swiftdialog(
    layouts: list[dict],
    disabled_layouts: list[str]
) -> list[str] | None:
    """
    Show dialog to enable/disable workspaces.

    Args:
        layouts: List of workspace dicts from discover_layouts()
        disabled_layouts: Current list of disabled workspace names

    Returns:
        Updated list of disabled workspace names, or None if cancelled
    """
    if not layouts:
        logger.warning(
            "No workspaces to manage",
            operation="show_manage_layouts_swiftdialog"
        )
        return None

    # Build checkboxes: checked = ENABLED (will show in selector)
    checkboxes = []
    for layout in layouts:
        is_enabled = layout["name"] not in disabled_layouts
        checkboxes.append({
            "label": layout["display"],
            "checked": is_enabled,
            "icon": CATEGORY_ICONS["layout_tab"]
        })

    # Calculate dialog height
    item_count = len(layouts)
    dialog_height = min(200 + item_count * 50, 600)

    dialog_config = {
        "title": "Manage Workspaces",
        "titlefont": "size=18",
        "message": "Toggle workspaces to show/hide in selector:",
        "messagefont": "size=14",
        "appearance": "dark",
        "hideicon": True,
        "checkbox": checkboxes,
        "checkboxstyle": {
            "style": "switch",
            "size": "regular"
        },
        "button1text": "Save",
        "button2text": "Cancel",
        "height": str(dialog_height),
        "width": "600",
        "moveable": True,
        "ontop": True,
        "json": True
    }

    logger.debug(
        "Showing manage layouts dialog",
        operation="show_manage_layouts_swiftdialog",
        layout_count=len(layouts),
        disabled_count=len(disabled_layouts)
    )

    return_code, output = run_swiftdialog(dialog_config)

    if return_code == 2:
        logger.debug(
            "Manage layouts cancelled",
            operation="show_manage_layouts_swiftdialog"
        )
        return None

    if return_code != 0 or not output:
        logger.warning(
            "Manage layouts dialog error",
            operation="show_manage_layouts_swiftdialog",
            return_code=return_code
        )
        return None

    # Parse output: unchecked layouts are disabled
    new_disabled = []
    for layout in layouts:
        # SwiftDialog returns {"label": true/false, ...}
        label = layout["display"]
        is_checked = output.get(label, True)
        if not is_checked:
            new_disabled.append(layout["name"])

    logger.info(
        "Workspaces updated",
        operation="show_manage_layouts_swiftdialog",
        disabled_layouts=new_disabled,
        total_workspaces=len(layouts)
    )

    return new_disabled


async def show_manage_layouts(
    layouts: list[dict],
    prefs: dict
) -> dict | None:
    """
    Show workspace management UI and return updated preferences.

    Uses SwiftDialog if available.

    Args:
        layouts: All workspaces (including disabled ones)
        prefs: Current preferences dict

    Returns:
        Updated preferences dict, or None if cancelled
    """
    if not is_swiftdialog_available():
        logger.warning(
            "SwiftDialog not available for workspace management",
            operation="show_manage_layouts"
        )
        return None

    disabled_layouts = prefs.get("disabled_layouts", [])

    # Run SwiftDialog in executor (non-blocking)
    loop = asyncio.get_event_loop()
    new_disabled = await loop.run_in_executor(
        None,
        show_manage_layouts_swiftdialog,
        layouts,
        disabled_layouts
    )

    if new_disabled is None:
        return None

    # Update preferences with new disabled list
    updated_prefs = prefs.copy()
    updated_prefs["disabled_layouts"] = new_disabled

    return updated_prefs
