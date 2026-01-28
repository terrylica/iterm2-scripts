# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Pane Setup
# =============================================================================


async def setup_pane_and_send_command(
    session, connection, directory: str, command: str, settle_time: float
):
    """
    Setup a pane: cd to directory, wait briefly, then send command.

    Args:
        session: iTerm2 session object
        connection: iTerm2 connection
        directory: Working directory
        command: Command to execute
        settle_time: Wait time after cd (seconds)
    """
    # Change to target directory (expand ~ first, then quote for paths with spaces)
    expanded_path = os.path.expanduser(directory)
    await session.async_send_text(f"cd {shlex.quote(expanded_path)}\n")

    # Wait briefly for cd to complete
    await asyncio.sleep(settle_time)

    # Check if shell integration provides prompt state
    try:
        prompt = await iterm2.async_get_last_prompt(connection, session.session_id)
        if prompt:
            # Shell integration working - check state
            if prompt.command_state == iterm2.PromptState.EDITING:
                # Ready for input
                await session.async_send_text(f"{command}\n")
                logger.debug(
                    "Command sent via shell integration",
                    operation="setup_pane_and_send_command",
                    status="success",
                    directory=directory,
                    shell_integration=True
                )
                return True
            else:
                # Not ready (command running, etc.)
                logger.warning(
                    "Shell not ready for input",
                    operation="setup_pane_and_send_command",
                    status="not_ready",
                    directory=directory,
                    prompt_state=str(prompt.command_state)
                )
                return False
        else:
            # No prompt info available - send command anyway (best effort)
            await session.async_send_text(f"{command}\n")
            logger.debug(
                "Command sent without prompt info",
                operation="setup_pane_and_send_command",
                status="success",
                directory=directory,
                shell_integration=False
            )
            return True
    except (iterm2.RPCException, AttributeError, TypeError) as e:
        # Shell integration not available or error - send command anyway
        logger.warning(
            "Shell integration unavailable, falling back to direct send",
            operation="setup_pane_and_send_command",
            status="fallback",
            directory=directory,
            error=str(e),
            error_type=type(e).__name__
        )
        await session.async_send_text(f"{command}\n")
        return True


async def create_tab_with_splits(
    window,
    connection,
    directory: str,
    tab_name: str,
    config: dict,
    is_first: bool = False,
):
    """
    Create a tab with left/right split and run commands concurrently.

    Args:
        window: iTerm2 window object
        connection: iTerm2 connection
        directory: Working directory for this tab
        tab_name: Name for the tab
        config: Configuration dictionary
        is_first: If True, use current tab instead of creating new one
    """
    # Extract config values
    left_pane_ratio = config["layout"]["left_pane_ratio"]
    settle_time = config["layout"]["settle_time"]

    # Validate commands - fallback to safe defaults if binary not found
    left_command = validate_command(
        config["commands"]["left"],
        SAFE_LEFT_COMMAND
    )
    right_command = validate_command(
        config["commands"]["right"],
        SAFE_RIGHT_COMMAND
    )

    if is_first:
        # Use the current tab for the first one
        tab = window.current_tab
        left_pane = tab.current_session
    else:
        # Create a new tab
        tab = await window.async_create_tab()
        left_pane = tab.current_session

    # Set tab title (no emoji - cleaner and more space for folder names)
    # Set both tab title and session name for persistence
    await tab.async_set_title(tab_name)
    await left_pane.async_set_name(tab_name)

    # Get current grid size before split
    current_size = left_pane.grid_size

    # Split vertically to create right pane
    # Use custom profile for right pane if configured (e.g., larger font for Claude Code)
    right_profile = config.get("profiles", {}).get("right")
    if right_profile:
        right_pane = await left_pane.async_split_pane(vertical=True, profile=right_profile)
    else:
        right_pane = await left_pane.async_split_pane(vertical=True)

    # Calculate new widths (left pane narrower for broot)
    total_width = current_size.width
    left_width = int(total_width * left_pane_ratio)
    right_width = total_width - left_width

    # Set preferred sizes for each pane
    left_pane.preferred_size = iterm2.util.Size(left_width, current_size.height)
    right_pane.preferred_size = iterm2.util.Size(right_width, current_size.height)

    # Apply the layout changes
    await tab.async_update_layout()

    # Setup both panes concurrently (run in parallel)
    await asyncio.gather(
        setup_pane_and_send_command(
            left_pane, connection, directory, left_command, settle_time
        ),
        setup_pane_and_send_command(
            right_pane, connection, directory, right_command, settle_time
        ),
    )

    return tab


async def maximize_window(window):
    """
    Maximize the window to fill the screen (excluding menu bar and dock)
    """
    try:
        # Get the visible screen area (excludes menu bar and dock)
        screen = NSScreen.mainScreen()
        if screen:
            visible_frame = screen.visibleFrame()

            # Debug output
            logger.debug(
                "Screen dimensions retrieved",
                operation="maximize_window",
                width=int(visible_frame.size.width),
                height=int(visible_frame.size.height),
                origin_x=int(visible_frame.origin.x),
                origin_y=int(visible_frame.origin.y)
            )

            # Create iTerm2 frame using constructor
            frame = iterm2.Frame(
                origin=iterm2.Point(
                    int(visible_frame.origin.x),
                    int(visible_frame.origin.y)
                ),
                size=iterm2.Size(
                    int(visible_frame.size.width),
                    int(visible_frame.size.height)
                )
            )

            # Set the window frame
            await window.async_set_frame(frame)
            logger.debug(
                "Window maximized successfully",
                operation="maximize_window",
                status="success",
                width=int(visible_frame.size.width),
                height=int(visible_frame.size.height)
            )
            return True
        else:
            logger.warning(
                "No main screen found for window maximization",
                operation="maximize_window",
                status="failed"
            )
            return False
    except (AttributeError, TypeError, OSError) as e:
        logger.warning(
            "Could not maximize window",
            operation="maximize_window",
            status="failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return False