# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Setup Wizard
# =============================================================================


def needs_migration() -> bool:
    """
    Check if migration from legacy config directory is needed.

    Returns True if:
    - Legacy config directory exists with layout files
    - New config directory doesn't exist or has no workspace files

    Returns:
        True if migration should be offered
    """
    # Check if legacy config exists
    if not LEGACY_CONFIG_DIR.exists():
        return False

    # Check if legacy has layout files
    legacy_layouts = list(LEGACY_CONFIG_DIR.glob(LEGACY_LAYOUT_PATTERN))
    legacy_prefs = LEGACY_PREFERENCES_PATH.exists()

    if not legacy_layouts and not legacy_prefs:
        return False

    # Check if new config already has workspace files
    if CONFIG_DIR.exists():
        new_workspaces = list(CONFIG_DIR.glob(WORKSPACE_PATTERN))
        if new_workspaces:
            return False  # Already migrated or new config exists

    logger.debug(
        "Migration needed from legacy config",
        operation="needs_migration",
        legacy_dir=str(LEGACY_CONFIG_DIR),
        legacy_layouts=len(legacy_layouts),
        legacy_prefs=legacy_prefs
    )
    return True


def migrate_config_files() -> tuple[int, int]:
    """
    Migrate files from legacy to new config directory.

    Renames:
    - layout-*.toml -> workspace-*.toml
    - selector-preferences.toml -> preferences.toml

    Returns:
        Tuple of (layouts_migrated, prefs_migrated)
    """
    import shutil

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    layouts_migrated = 0
    prefs_migrated = 0

    # Migrate layout files
    for legacy_path in LEGACY_CONFIG_DIR.glob(LEGACY_LAYOUT_PATTERN):
        # layout-foo.toml -> workspace-foo.toml
        old_name = legacy_path.name
        new_name = old_name.replace("layout-", "workspace-")
        new_path = CONFIG_DIR / new_name

        if not new_path.exists():
            shutil.copy2(legacy_path, new_path)
            layouts_migrated += 1
            logger.info(
                "Migrated layout file",
                operation="migrate_config_files",
                old_path=str(legacy_path),
                new_path=str(new_path)
            )

    # Migrate preferences
    if LEGACY_PREFERENCES_PATH.exists() and not PREFERENCES_PATH.exists():
        shutil.copy2(LEGACY_PREFERENCES_PATH, PREFERENCES_PATH)
        prefs_migrated = 1
        logger.info(
            "Migrated preferences file",
            operation="migrate_config_files",
            old_path=str(LEGACY_PREFERENCES_PATH),
            new_path=str(PREFERENCES_PATH)
        )

    return layouts_migrated, prefs_migrated


async def run_migration_wizard(connection, window) -> bool:
    """
    Offer migration from legacy config directory.

    Args:
        connection: iTerm2 connection
        window: Current iTerm2 window

    Returns:
        True if migration completed, False if skipped/cancelled
    """
    # Count legacy files
    legacy_layouts = list(LEGACY_CONFIG_DIR.glob(LEGACY_LAYOUT_PATTERN))

    migrate_alert = iterm2.Alert(
        "Migrate Configuration?",
        f"Found {len(legacy_layouts)} workspace(s) in legacy location:\n"
        f"  {LEGACY_CONFIG_DIR}\n\n"
        f"Migrate to new location?\n"
        f"  {CONFIG_DIR}\n\n"
        "Your original files will be kept as backup.",
        window_id=window.window_id
    )
    migrate_alert.add_button("Migrate")
    migrate_alert.add_button("Skip")
    response = await migrate_alert.async_run(connection)

    if response == 1:  # Skip
        logger.info(
            "Migration skipped by user",
            operation="run_migration_wizard",
            status="skipped"
        )
        return False

    # Perform migration
    layouts_migrated, prefs_migrated = migrate_config_files()

    success_alert = iterm2.Alert(
        "Migration Complete",
        f"Migrated {layouts_migrated} workspace(s) and "
        f"{prefs_migrated} preference file(s).\n\n"
        f"New location: {CONFIG_DIR}\n\n"
        "Original files kept in legacy location.",
        window_id=window.window_id
    )
    success_alert.add_button("OK")
    await success_alert.async_run(connection)

    logger.info(
        "Migration completed",
        operation="run_migration_wizard",
        status="success",
        layouts_migrated=layouts_migrated,
        prefs_migrated=prefs_migrated
    )

    return True


def is_first_run() -> bool:
    """
    Detect if this is the first run for a new user.

    Returns True if:
    - No workspace-*.toml files exist in CONFIG_DIR
    - No legacy layout.toml exists
    - No preferences.toml exists

    Returns:
        True if this appears to be a first-time run
    """
    # Check for any layout files
    layout_files = list(CONFIG_DIR.glob(WORKSPACE_PATTERN))
    if layout_files:
        return False

    # Check for legacy layout.toml
    legacy_layout = CONFIG_DIR / "layout.toml"
    if legacy_layout.exists():
        return False

    # Check for preferences (indicates previous use)
    if PREFERENCES_PATH.exists():
        return False

    logger.debug(
        "First-run detected",
        operation="is_first_run",
        config_dir=str(CONFIG_DIR),
        layout_files_count=0
    )
    return True


def generate_default_layout_content(home_dir: bool = True, project_dir: str | None = None) -> str:
    """
    Generate default layout TOML content.

    Args:
        home_dir: Include home directory tab
        project_dir: Optional project directory to include

    Returns:
        TOML content string
    """
    lines = [
        "# Workspace Launcher Configuration",
        "# Auto-generated by first-run wizard",
        "# Edit this file to customize your workspace tabs",
        "",
        "[layout]",
        "left_pane_ratio = 0.25",
        "settle_time = 0.3",
        "",
        "[commands]",
        "# Safe defaults - customize after verifying tool availability",
        'left = "ls -la"    # Try: br --sort-by-type-dirs-first (requires broot)',
        'right = "zsh"      # Try: css (requires Claude Code)',
        "",
    ]

    if home_dir:
        lines.extend([
            "[[tabs]]",
            'name = "home"',
            'dir = "~"',
            "",
        ])

    if project_dir:
        # Convert to ~ format if in home directory
        home = str(Path.home())
        if project_dir.startswith(home):
            project_dir = "~" + project_dir[len(home):]

        project_name = Path(project_dir).name
        lines.extend([
            "[[tabs]]",
            f'name = "{project_name}"',
            f'dir = "{project_dir}"',
            "",
        ])

    return "\n".join(lines)


async def run_first_run_wizard(connection, window) -> bool:
    """
    Run the first-run wizard for new users.

    Presents a minimal 2-3 step wizard to:
    1. Welcome and explain the tool
    2. Optionally add a project directory
    3. Create default config

    Args:
        connection: iTerm2 connection
        window: Current iTerm2 window

    Returns:
        True if wizard completed successfully, False if cancelled
    """
    logger.info(
        "Starting first-run wizard",
        operation="run_first_run_wizard",
        status="started"
    )

    # Step 1: Welcome dialog
    welcome_alert = iterm2.Alert(
        "Welcome to Workspace Launcher",
        "This tool creates workspace tabs with split panes on startup.\n\n"
        "Each tab has:\n"
        "• Left pane: File browser (narrow)\n"
        "• Right pane: Main workspace (wide)\n\n"
        "Let's set up your first layout.",
        window_id=window.window_id
    )
    welcome_alert.add_button("Get Started")
    welcome_alert.add_button("Cancel")
    response = await welcome_alert.async_run(connection)

    if response == 1:  # Cancel
        logger.info(
            "First-run wizard cancelled at welcome",
            operation="run_first_run_wizard",
            status="cancelled"
        )
        return False

    # Step 2: Ask about project directory
    folder_alert = iterm2.Alert(
        "Add Project Folder",
        "Would you like to add a project folder?\n\n"
        "You can always add more folders later via the Settings dialog.",
        window_id=window.window_id
    )
    folder_alert.add_button("Add Folder")
    folder_alert.add_button("Skip")
    folder_alert.add_button("Cancel")
    response = await folder_alert.async_run(connection)

    if response == 2:  # Cancel
        logger.info(
            "First-run wizard cancelled at folder selection",
            operation="run_first_run_wizard",
            status="cancelled"
        )
        return False

    project_dir = None
    if response == 0:  # Add Folder
        project_dir = choose_folder_native("Select your project folder:")
        if project_dir:
            logger.debug(
                "Project folder selected",
                operation="run_first_run_wizard",
                folder=project_dir
            )

    # Step 3: Create config file
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    layout_content = generate_default_layout_content(
        home_dir=True,
        project_dir=project_dir
    )

    layout_path = CONFIG_DIR / "workspace-default.toml"

    try:
        atomic_write_file(layout_path, layout_content)

        logger.info(
            "First-run wizard completed - layout created",
            operation="run_first_run_wizard",
            status="success",
            layout_path=str(layout_path)
        )

        # Show completion message
        complete_alert = iterm2.Alert(
            "Setup Complete!",
            f"Your layout config has been created:\n"
            f"{layout_path}\n\n"
            "Edit this file to add more workspace tabs.\n\n"
            "Optional enhancements:\n"
            "• brew install broot (file navigator)\n"
            "• brew install swiftdialog (better UI)",
            window_id=window.window_id
        )
        complete_alert.add_button("OK")
        await complete_alert.async_run(connection)

        return True

    except OSError as e:
        logger.error(
            "Failed to create layout file in wizard",
            operation="run_first_run_wizard",
            status="failed",
            error=str(e)
        )

        error_alert = iterm2.Alert(
            "Setup Failed",
            f"Could not create config file:\n{e}\n\n"
            f"Please create manually:\n{layout_path}",
            window_id=window.window_id
        )
        error_alert.add_button("OK")
        await error_alert.async_run(connection)

        return False


async def run_setup_wizard_for_veteran(connection, window) -> bool:
    """
    Run setup wizard for veteran users (manual trigger).

    Unlike first-run wizard, this creates a new workspace file with a unique name
    (workspace-wizard.toml) without overwriting existing configs.

    Args:
        connection: iTerm2 connection
        window: Current iTerm2 window

    Returns:
        True if wizard completed successfully, False if cancelled
    """
    logger.info(
        "Starting setup wizard (veteran user)",
        operation="run_setup_wizard_for_veteran",
        status="started"
    )

    # Step 1: Inform user about the wizard
    info_alert = iterm2.Alert(
        "Setup Wizard",
        "This wizard will create a new workspace configuration file.\n\n"
        "Your existing workspaces will not be modified.\n"
        "The new file will be named: workspace-wizard.toml",
        window_id=window.window_id
    )
    info_alert.add_button("Continue")
    info_alert.add_button("Cancel")
    response = await info_alert.async_run(connection)

    if response == 1:  # Cancel
        logger.info(
            "Veteran wizard cancelled",
            operation="run_setup_wizard_for_veteran",
            status="cancelled"
        )
        return False

    # Step 2: Ask about project directory
    folder_alert = iterm2.Alert(
        "Add Project Folder",
        "Would you like to add a project folder to the new layout?",
        window_id=window.window_id
    )
    folder_alert.add_button("Add Folder")
    folder_alert.add_button("Skip")
    folder_alert.add_button("Cancel")
    response = await folder_alert.async_run(connection)

    if response == 2:  # Cancel
        logger.info(
            "Veteran wizard cancelled at folder selection",
            operation="run_setup_wizard_for_veteran",
            status="cancelled"
        )
        return False

    project_dir = None
    if response == 0:  # Add Folder
        project_dir = choose_folder_native("Select your project folder:")

    # Step 3: Create config file
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    layout_content = generate_default_layout_content(
        home_dir=True,
        project_dir=project_dir
    )

    layout_path = CONFIG_DIR / "workspace-wizard.toml"

    try:
        atomic_write_file(layout_path, layout_content)

        logger.info(
            "Veteran wizard completed - layout created",
            operation="run_setup_wizard_for_veteran",
            status="success",
            layout_path=str(layout_path)
        )

        # Show completion message
        complete_alert = iterm2.Alert(
            "Layout Created!",
            f"New layout saved to:\n{layout_path}\n\n"
            "Select it from the layout list to use it.",
            window_id=window.window_id
        )
        complete_alert.add_button("OK")
        await complete_alert.async_run(connection)

        return True

    except OSError as e:
        logger.error(
            "Failed to create layout file in veteran wizard",
            operation="run_setup_wizard_for_veteran",
            status="failed",
            error=str(e)
        )

        error_alert = iterm2.Alert(
            "Setup Failed",
            f"Could not create config file:\n{e}",
            window_id=window.window_id
        )
        error_alert.add_button("OK")
        await error_alert.async_run(connection)

        return False
