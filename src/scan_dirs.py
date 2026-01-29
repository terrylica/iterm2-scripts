# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Directory Management
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
                "size": "regular"
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
