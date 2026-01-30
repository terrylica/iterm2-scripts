# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there


async def main(connection):
    """
    Main function to set up the entire workspace.

    Flow:
    1. Check preferences for remembered choice
    2. If no remembered choice, discover workspaces and show selector
    3. Load selected workspace config
    4. Layer 2: Tab customization (optional)
    5. Create tabs with split panes
    6. Maximize window
    """
    main_trace_id = str(uuid4())
    report = ErrorReport()

    logger.info(
        "Workspace Launcher starting",
        operation="main",
        status="started",
        trace_id=main_trace_id
    )

    # =========================================================================
    # iTerm2 Window Setup (needed for dialogs)
    # =========================================================================

    app = await iterm2.async_get_app(connection)

    # Get the current window (or create one if none exists)
    window = app.current_terminal_window
    if window is None:
        logger.info(
            "No current window - creating a new one",
            operation="main",
            trace_id=main_trace_id
        )
        window = await iterm2.Window.async_create(connection)

    # =========================================================================
    # Migration from Legacy Config (if needed)
    # =========================================================================

    if needs_migration():
        logger.info(
            "Legacy config detected - offering migration",
            operation="main",
            status="migration_needed",
            trace_id=main_trace_id
        )
        await run_migration_wizard(connection, window)

    # =========================================================================
    # First-Run Detection and Wizard
    # =========================================================================

    if is_first_run():
        logger.info(
            "First run detected - starting wizard",
            operation="main",
            status="first_run",
            trace_id=main_trace_id
        )
        wizard_success = await run_first_run_wizard(connection, window)
        if not wizard_success:
            logger.info(
                "First-run wizard cancelled or failed",
                operation="main",
                status="wizard_cancelled",
                trace_id=main_trace_id
            )
            return

    # =========================================================================
    # Layout Selection
    # =========================================================================

    prefs = load_preferences()
    all_layouts = discover_layouts()

    # Filter out disabled layouts for selector display
    disabled_layouts = prefs.get("disabled_layouts", [])
    layouts = [layout for layout in all_layouts if layout["name"] not in disabled_layouts]

    if not all_layouts:
        # Fallback: Check for legacy layout.toml (backward compatibility)
        if LEGACY_CONFIG_PATH.exists():
            logger.info(
                "Using legacy config",
                operation="main",
                status="legacy_fallback",
                trace_id=main_trace_id,
                config_path=str(LEGACY_CONFIG_PATH)
            )
            config = load_config()
            if config is None:
                return
            # Skip to tab creation with legacy config
            selected_layout = {"name": "legacy", "path": LEGACY_CONFIG_PATH}
        else:
            logger.error(
                "No workspace files found",
                operation="main",
                status="failed",
                trace_id=main_trace_id,
                expected_location=f"{CONFIG_DIR}/workspace-*.toml"
            )
            return
    else:
        selected_layout = None
        config = None

        # Check for remembered choice
        if prefs.get("remember_choice") and prefs.get("last_layout"):
            last_name = prefs["last_layout"]
            for layout in layouts:
                if layout["name"] == last_name:
                    selected_layout = layout
                    logger.info(
                        "Using remembered workspace",
                        operation="main",
                        status="remembered",
                        trace_id=main_trace_id,
                        layout_name=last_name
                    )
                    break

            if selected_layout is None:
                logger.warning(
                    "Remembered workspace not found, showing selector",
                    operation="main",
                    status="remembered_not_found",
                    trace_id=main_trace_id,
                    remembered_name=last_name
                )

        # Show selector if no remembered choice or remembered layout not found
        # Loop to handle Settings action (directory management)
        while selected_layout is None:
            selector_result = await show_layout_selector(
                connection, layouts, last_layout=prefs.get("last_layout")
            )

            if selector_result is None:
                logger.info(
                    "Workspace selection cancelled",
                    operation="main",
                    status="cancelled",
                    trace_id=main_trace_id
                )
                return

            # Check for special actions
            if isinstance(selector_result, dict):
                action = selector_result.get("action")

                if action == "manage_directories":
                    logger.info(
                        "Opening directory management",
                        operation="main",
                        status="settings",
                        trace_id=main_trace_id
                    )
                    # Show directory management dialog
                    updated_prefs = await show_directory_management(prefs)
                    if updated_prefs is not None:
                        prefs = updated_prefs
                        save_preferences(prefs)
                        logger.info(
                            "Scan directories updated",
                            operation="main",
                            status="directories_updated",
                            trace_id=main_trace_id,
                            enabled_dirs=sum(1 for d in prefs.get("scan_directories", []) if d.get("enabled"))
                        )
                    # Continue loop to show selector again
                    continue

                if action == "manage_layouts":
                    logger.info(
                        "Opening workspace management",
                        operation="main",
                        status="manage_layouts",
                        trace_id=main_trace_id
                    )
                    # Show layout management dialog with ALL layouts
                    updated_prefs = await show_manage_layouts(all_layouts, prefs)
                    if updated_prefs is not None:
                        prefs = updated_prefs
                        save_preferences(prefs)
                        # Refresh filtered layouts list
                        disabled_layouts = prefs.get("disabled_layouts", [])
                        layouts = [layout for layout in all_layouts if layout["name"] not in disabled_layouts]
                        logger.info(
                            "Workspace visibility updated",
                            operation="main",
                            status="layouts_updated",
                            trace_id=main_trace_id,
                            disabled_count=len(disabled_layouts),
                            visible_count=len(layouts)
                        )
                    # Continue loop to show selector again
                    continue

                if action == "run_wizard":
                    logger.info(
                        "Running setup wizard (manual trigger)",
                        operation="main",
                        status="wizard_manual",
                        trace_id=main_trace_id
                    )
                    # Run wizard - creates new layout file without overwriting existing
                    await run_setup_wizard_for_veteran(connection, window)
                    # Refresh layouts after wizard
                    all_layouts = discover_layouts()
                    disabled_layouts = prefs.get("disabled_layouts", [])
                    layouts = [layout for layout in all_layouts if layout["name"] not in disabled_layouts]
                    # Continue loop to show selector again
                    continue

            # Normal layout selection
            selected_layout = selector_result

            # Save last layout choice (but don't auto-enable remember_choice)
            # User can manually set remember_choice = true in preferences to skip selector
            prefs["last_layout"] = selected_layout["name"]
            save_preferences(prefs)

        # Load the selected workspace config
        logger.info(
            "Loading workspace",
            operation="main",
            status="loading",
            trace_id=main_trace_id,
            layout_name=selected_layout["name"]
        )
        config_result = load_config_from_path(selected_layout["path"])

        # Use collect_result to aggregate errors
        if not report.collect_result(config_result, "load_config"):
            logger.error(
                "Failed to load workspace config",
                operation="main",
                status="config_load_failed",
                trace_id=main_trace_id
            )
            report.log_summary(main_trace_id)
            return

        config = config_result.value

    if config is None:
        return

    tabs = config.get("tabs", [])
    if not tabs:
        logger.warning(
            "No tabs configured in workspace",
            operation="main",
            status="no_tabs",
            trace_id=main_trace_id,
            config_path=str(selected_layout["path"])
        )
        return

    # =========================================================================
    # Window Activation (ensure focus before creating tabs)
    # =========================================================================

    # Ensure window has focus before creating tabs
    await app.async_activate()
    await window.async_activate()
    logger.debug(
        "Window activated and focused",
        operation="main",
        trace_id=main_trace_id
    )

    left_pane_ratio = config["layout"]["left_pane_ratio"]
    logger.info(
        "Creating workspace",
        operation="main",
        status="creating",
        trace_id=main_trace_id,
        layout_name=selected_layout["name"],
        left_pane_ratio=int(left_pane_ratio * 100),
        config_path=str(selected_layout["path"])
    )

    # =========================================================================
    # Worktree Discovery (Universal - All Git Repos)
    # =========================================================================

    # Legacy worktree discovery (config-based, for backward compatibility)
    legacy_worktrees = discover_worktrees(config)
    if legacy_worktrees:
        logger.info(
            "Legacy worktrees discovered",
            operation="main",
            trace_id=main_trace_id,
            metrics={"count": len(legacy_worktrees)},
            worktrees=[{"name": wt["name"], "dir": wt["dir"]} for wt in legacy_worktrees]
        )

    # Universal worktree discovery (scans all git repos from configured directories)
    layout_dirs = {Path(tab["dir"]).expanduser() for tab in tabs}
    scan_directories = get_enabled_scan_directories(prefs)
    all_git_repos = discover_git_repos(scan_directories=scan_directories, exclude_dirs=set())
    additional_repos = [r for r in all_git_repos if Path(r["dir"]).expanduser() not in layout_dirs]
    universal_worktrees = discover_all_worktrees(all_git_repos)

    if universal_worktrees:
        logger.info(
            "Universal worktrees discovered",
            operation="main",
            trace_id=main_trace_id,
            metrics={"count": len(universal_worktrees)},
            worktrees=[{"name": wt["name"], "dir": wt["dir"]} for wt in universal_worktrees]
        )

    # Discover untracked folders (directories without .git)
    untracked_folders = discover_untracked_folders(
        scan_directories=scan_directories,
        exclude_dirs=layout_dirs
    )
    if untracked_folders:
        logger.info(
            "Untracked folders discovered",
            operation="main",
            trace_id=main_trace_id,
            metrics={"count": len(untracked_folders)},
            folders=[{"name": f["name"], "dir": f["dir"]} for f in untracked_folders]
        )

    logger.info(
        "Discovery complete",
        operation="main",
        status="discovery_complete",
        trace_id=main_trace_id,
        metrics={
            "layout_tabs": len(tabs),
            "legacy_worktrees": len(legacy_worktrees),
            "universal_worktrees": len(universal_worktrees),
            "additional_repos": len(additional_repos),
            "untracked_folders": len(untracked_folders)
        }
    )

    # =========================================================================
    # Layer 2: Tab Customization (Optional)
    # =========================================================================

    # Check if user wants to skip tab customization
    skip_customization = prefs.get("skip_tab_customization", False)

    if not skip_customization and (universal_worktrees or additional_repos or untracked_folders):
        # Show Layer 2 dialog for tab selection
        logger.info(
            "Showing tab customization dialog",
            operation="main",
            status="layer2_start",
            trace_id=main_trace_id
        )
        # Callback to save custom tab names when user renames
        def save_custom_names(new_names: dict[str, str]) -> None:
            prefs["custom_tab_names"] = new_names
            save_preferences(prefs)

        final_tabs = await show_tab_customization(
            connection,
            layout_tabs=tabs,
            worktrees=universal_worktrees,
            additional_repos=additional_repos,
            untracked_folders=untracked_folders,
            last_tab_selections=prefs.get("last_tab_selections"),
            custom_tab_names=prefs.get("custom_tab_names", {}),
            save_preferences_callback=save_custom_names
        )

        if final_tabs is None:
            logger.info(
                "Workspace creation cancelled at tab customization",
                operation="main",
                status="cancelled",
                trace_id=main_trace_id
            )
            return

        # Validate that user selected at least one tab
        if len(final_tabs) == 0:
            logger.warning(
                "No tabs selected - showing confirmation dialog",
                operation="main",
                status="empty_selection",
                trace_id=main_trace_id
            )
            # Show confirmation dialog for empty selection
            confirm_alert = iterm2.Alert(
                "No Tabs Selected",
                "You unchecked all tabs. Continue anyway?\n\n"
                "iTerm2 will open with no workspace tabs.",
                window_id=window.window_id
            )
            confirm_alert.add_button("Continue")
            confirm_alert.add_button("Go Back")
            response = await confirm_alert.async_run(connection)

            if response == 1:  # "Go Back" clicked
                # Re-show the tab customization dialog
                final_tabs = await show_tab_customization(
                    connection,
                    layout_tabs=tabs,
                    worktrees=universal_worktrees,
                    additional_repos=additional_repos,
                    untracked_folders=untracked_folders,
                    last_tab_selections=prefs.get("last_tab_selections"),
                    custom_tab_names=prefs.get("custom_tab_names", {}),
                    save_preferences_callback=save_custom_names
                )
                if final_tabs is None:
                    return

        all_tabs = final_tabs
    else:
        # Build final tab list with legacy worktrees inserted after matching tab
        # Look for a tab with worktree root configured to insert after
        worktree_root = config.get("worktrees", {}).get("alpha_forge_root")
        all_tabs = []
        for tab_config in tabs:
            all_tabs.append(tab_config)
            # Insert worktrees after the tab that matches the worktree root
            if worktree_root and legacy_worktrees:
                tab_dir = os.path.expanduser(tab_config.get("dir", ""))
                root_expanded = os.path.expanduser(worktree_root)
                if tab_dir == root_expanded:
                    all_tabs.extend(legacy_worktrees)

        # Also add universal worktrees at the end if not using Layer 2
        if universal_worktrees and skip_customization:
            all_tabs.extend(universal_worktrees)

    # =========================================================================
    # Detect Already-Open Tabs
    # =========================================================================

    open_dirs = await get_open_tab_directories(window)
    if open_dirs:
        logger.info(
            "Detected open directories",
            operation="main",
            trace_id=main_trace_id,
            count=len(open_dirs),
        )

    tabs_to_create = []
    tabs_skipped = []
    for tab_config in all_tabs:
        expanded = os.path.realpath(
            os.path.expanduser(tab_config["dir"])
        ).rstrip("/")
        if expanded in open_dirs:
            tab_name = tab_config.get("name") or os.path.basename(expanded)
            tabs_skipped.append(tab_name)
            logger.info(
                "Tab skipped - already open",
                operation="main",
                trace_id=main_trace_id,
                tab_name=tab_name,
                tab_dir=tab_config["dir"],
            )
        else:
            tabs_to_create.append(tab_config)

    if tabs_skipped:
        logger.info(
            f"Skipped {len(tabs_skipped)} already-open tab(s)",
            operation="main",
            trace_id=main_trace_id,
            skipped=tabs_skipped,
            creating=len(tabs_to_create),
        )

    all_tabs = tabs_to_create

    # =========================================================================
    # Window and Tab Creation
    # =========================================================================

    # Maximize window first
    logger.info(
        "Maximizing window",
        operation="main",
        trace_id=main_trace_id
    )
    await maximize_window(window)

    # Track whether we've used the initial tab (for is_first logic)
    # When tabs were skipped (already open), never reuse the active tab —
    # the user's focused tab should not be overwritten.
    used_initial_tab = len(tabs_skipped) > 0

    # Create all tabs in the specified order
    for idx, tab_config in enumerate(all_tabs):
        # Use directory basename as default name if not specified
        tab_name = tab_config.get("name") or os.path.basename(
            os.path.expanduser(tab_config["dir"])
        )
        tab_dir = tab_config["dir"]

        # Validate directory exists
        expanded_dir = os.path.expanduser(tab_dir)
        if not os.path.isdir(expanded_dir):
            logger.warning(
                "Tab skipped - directory not found",
                operation="main",
                status="skip",
                trace_id=main_trace_id,
                tab_index=idx + 1,
                tab_name=tab_name,
                tab_dir=tab_dir
            )
            report.add_warning(Error(
                error_type=ErrorType.FILE_NOT_FOUND,
                message=f"Tab directory not found: {tab_dir}",
                context={"tab_name": tab_name, "tab_dir": tab_dir}
            ))
            continue

        logger.info(
            "Creating tab",
            operation="main",
            trace_id=main_trace_id,
            tab_index=idx + 1,
            tab_name=tab_name,
            tab_dir=tab_dir
        )
        await create_tab_with_splits(
            window,
            connection,
            tab_dir,
            tab_name,
            config,
            is_first=(not used_initial_tab),
        )
        used_initial_tab = True

    # Save updated preferences with all selected tabs (including skipped ones
    # that were already open — they are still part of the workspace selection)
    all_tab_names = list(tabs_skipped) + [
        t.get("name", t.get("dir", "unknown")) for t in all_tabs
    ]
    prefs["last_tab_selections"] = all_tab_names
    save_preferences(prefs)

    logger.info(
        "Workspace created successfully",
        operation="main",
        status="complete",
        trace_id=main_trace_id
    )

    logger.info(
        "Workspace creation complete",
        operation="main",
        status="success",
        trace_id=main_trace_id,
        metrics={
            "tabs_created": len(all_tabs),
            "warnings": len(report.warnings),
            "errors": len(report.errors)
        }
    )

    report.log_summary(main_trace_id)


# Initialize logger and run the script
setup_logger()
iterm2.run_until_complete(main)
