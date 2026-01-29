# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Tool Installation Helpers
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
