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
    # Layout Selection (outer loop: "Back" from tab customization restarts)
    # =========================================================================

    prefs = load_preferences()

    while True:  # Back from tab customization restarts workspace selection
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

            # Auto-open last workspace if available
            if prefs.get("last_layout"):
                last_name = prefs["last_layout"]
                # Find the layout in the available list
                last_layout_match = None
                for layout in layouts:
                    if layout["name"] == last_name:
                        last_layout_match = layout
                        break

                if last_layout_match:
                    auto_result = await show_auto_open_dialog(
                        connection, last_name
                    )
                    if auto_result == "open":
                        selected_layout = last_layout_match
                        logger.info(
                            "Auto-opening last workspace",
                            operation="main",
                            status="auto_open",
                            trace_id=main_trace_id,
                            layout_name=last_name,
                        )
                    elif auto_result == "cancel":
                        logger.info(
                            "Auto-open cancelled",
                            operation="main",
                            status="cancelled",
                            trace_id=main_trace_id,
                        )
                        return
                    else:
                        # "change" — fall through to full selector
                        logger.info(
                            "User chose to change workspace",
                            operation="main",
                            status="change_workspace",
                            trace_id=main_trace_id,
                        )
                else:
                    logger.warning(
                        "Last workspace not found, showing selector",
                        operation="main",
                        status="last_not_found",
                        trace_id=main_trace_id,
                        last_layout=last_name,
                    )

            # Show selector if no auto-open or user chose to change
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
            def save_custom_names(new_names: dict[str, str], _prefs=prefs) -> None:
                _prefs["custom_tab_names"] = new_names
                save_preferences(_prefs)

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

            if final_tabs == "BACK_TO_SELECTOR":
                logger.info(
                    "Returning to workspace selector",
                    operation="main",
                    status="back_to_selector",
                    trace_id=main_trace_id
                )
                continue  # Re-enter outer workspace selection loop

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

            # Apply saved tab order from previous session (if any)
            saved_order = prefs.get("last_tab_order")
            if saved_order and len(final_tabs) > 1:
                order_map = {d: i for i, d in enumerate(saved_order)}
                final_tabs.sort(
                    key=lambda t: order_map.get(t.get("dir", ""), 999)
                )

            all_tabs = final_tabs

            # Offer tab reorder if more than 1 tab selected
            if len(all_tabs) > 1 and is_swiftdialog_available():
                reordered = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda _tabs=all_tabs, _prefs=prefs: show_tab_reorder_dialog(
                        _tabs,
                        custom_tab_names=_prefs.get("custom_tab_names", {}),
                    ),
                )
                if reordered is not None:
                    all_tabs = reordered
                    # Persist tab order so it's remembered next session
                    prefs["last_tab_order"] = [
                        t.get("dir", "") for t in all_tabs
                    ]
                    save_preferences(prefs)
                # None means cancelled reorder — keep original order

            break
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

            break

    # =========================================================================
    # Detect Already-Open Tabs
    # =========================================================================

    # Get custom tab names early - used by filter and display throughout
    custom_tab_names = prefs.get("custom_tab_names", {})

    open_dirs = await get_open_tab_directories(window)
    if open_dirs:
        logger.info(
            "Detected open directories",
            operation="main",
            trace_id=main_trace_id,
            count=len(open_dirs),
        )

    tabs_to_create, tabs_skipped = filter_already_open_tabs(
        all_tabs, open_dirs, custom_tab_names
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

    # Track created tabs for reordering (dir_path → Tab object)
    created_tabs: dict[str, object] = {}

    # Create all tabs in the specified order
    for idx, tab_config in enumerate(all_tabs):
        tab_dir = get_tab_dir(tab_config)
        # Use centralized utility for consistent name resolution
        tab_name = get_tab_display_name(tab_config, custom_tab_names)

        # Validate directory exists
        expanded_dir = expand_tab_path(tab_dir)
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
        tab = await create_tab_with_splits(
            window,
            connection,
            tab_dir,
            tab_name,
            config,
            is_first=(not used_initial_tab),
        )
        # Track created tab for reordering
        created_tabs[tab_dir] = tab
        used_initial_tab = True

    # Reorder all window tabs to match the finalized order
    # Pass created_tabs to bypass path query for newly created tabs
    if prefs.get("last_tab_order"):
        await reorder_window_tabs(window, prefs["last_tab_order"], created_tabs)

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
