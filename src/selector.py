# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# First-Run Detection and Wizard
# =============================================================================


async def show_auto_open_dialog(
    connection, layout_name: str
) -> str:
    """
    Show a dialog offering to auto-open the last workspace.

    Args:
        connection: iTerm2 connection object
        layout_name: Name of the last used workspace

    Returns:
        "open" if user accepts, "change" to show full selector, "cancel" to exit.
    """
    alert = iterm2.Alert(
        title="Workspace Launcher",
        subtitle=f"Press Enter to open workspace: {layout_name}",
    )
    # Button 0: Open (default/blue — triggers if user just hits Enter)
    alert.add_button("Open")
    # Button 1: Change Workspace (goes to full selector)
    alert.add_button("Change Workspace")
    # Button 2: Cancel (exit entirely)
    alert.add_button("Cancel")

    try:
        result = await alert.async_run(connection)

        # Restore focus
        app = await iterm2.async_get_app(connection)
        if app:
            await app.async_activate()

        button_index = result - 1000
        logger.debug(
            "Auto-open dialog result",
            operation="show_auto_open_dialog",
            button_index=button_index,
        )

        if button_index == 0:
            return "open"
        elif button_index == 1:
            return "change"
        else:
            return "cancel"

    except (iterm2.RPCException, ValueError, TypeError) as e:
        logger.error(
            "Auto-open dialog error",
            operation="show_auto_open_dialog",
            error=str(e),
        )
        return "cancel"


async def show_layout_selector(
    connection, layouts: list[dict], last_layout: str | None = None
) -> dict | None:
    """
    Show layout selection dialog and return chosen layout.

    Args:
        connection: iTerm2 connection object
        layouts: List of layout dicts from discover_layouts()
        last_layout: Name of last used layout (will be shown first as default)

    Returns:
        Selected layout dict, or None if cancelled/no layouts
    """
    # Always show dialog - even with 0 layouts, user needs access to
    # Manage Layouts (to re-enable), Scan Folders, Setup Wizard buttons

    # Reorder layouts so last_layout is first (becomes default blue button)
    ordered_layouts = list(layouts)
    if last_layout:
        for i, layout in enumerate(ordered_layouts):
            if layout["name"] == last_layout:
                # Move to front
                ordered_layouts.insert(0, ordered_layouts.pop(i))
                logger.debug(
                    "Reordered layouts, last used first",
                    operation="show_layout_selector",
                    last_layout=last_layout
                )
                break

    # Build alert with layout buttons
    logger.debug(
        "Showing selector dialog",
        operation="show_layout_selector",
        status="started",
        metrics={"layouts_count": len(ordered_layouts)}
    )

    # Dynamic subtitle based on workspace count
    if ordered_layouts:
        subtitle = "Choose a workspace to load:"
    else:
        subtitle = "No workspaces enabled. Use 'Manage Workspaces' to enable."

    alert = iterm2.Alert(
        title="Select Workspace",
        subtitle=subtitle,
    )

    # Add button for each layout (last used first as default)
    for layout in ordered_layouts:
        alert.add_button(layout["display"])
        logger.debug(
            "Added button to dialog",
            operation="show_layout_selector",
            layout_display=layout["display"]
        )

    # Add Scan Folders button (for directory management)
    alert.add_button("Scan Folders...")

    # Add Manage Workspaces button (for enabling/disabling workspaces)
    alert.add_button("Manage Workspaces...")

    # Add Setup Wizard button (for veteran users to re-run wizard)
    alert.add_button("Setup Wizard...")

    # Add Cancel button at the end
    alert.add_button("Cancel")

    # Show dialog and get result
    try:
        result = await alert.async_run(connection)

        # CRITICAL: Restore focus after dialog closes
        # The modal dialog may have caused focus to shift away from iTerm2
        app = await iterm2.async_get_app(connection)
        if app:
            await app.async_activate()  # Bring iTerm2 to foreground
            logger.debug(
                "Restored app focus after dialog",
                operation="show_layout_selector"
            )

        logger.debug(
            "Dialog result received",
            operation="show_layout_selector",
            result_raw=result
        )

        # Result is 1000 + button_index
        button_index = result - 1000

        logger.debug(
            "Button index calculated",
            operation="show_layout_selector",
            button_index=button_index
        )

        # Check if Scan Folders was clicked
        if button_index == len(ordered_layouts):
            logger.debug(
                "Scan Folders clicked",
                operation="show_layout_selector",
                status="scan_folders"
            )
            # Return special action dict
            return {"action": "manage_directories"}

        # Check if Manage Layouts was clicked
        if button_index == len(ordered_layouts) + 1:
            logger.debug(
                "Manage Layouts clicked",
                operation="show_layout_selector",
                status="manage_layouts"
            )
            # Return special action dict
            return {"action": "manage_layouts"}

        # Check if Setup Wizard was clicked
        if button_index == len(ordered_layouts) + 2:
            logger.debug(
                "Setup Wizard clicked",
                operation="show_layout_selector",
                status="wizard"
            )
            # Return special action dict
            return {"action": "run_wizard"}

        # Check if Cancel was clicked (last button)
        if button_index > len(ordered_layouts) + 2:
            logger.debug(
                "Cancel clicked or invalid selection",
                operation="show_layout_selector",
                status="cancelled"
            )
            return None

        selected = ordered_layouts[button_index]
        logger.debug(
            "Layout selected",
            operation="show_layout_selector",
            status="success",
            layout_name=selected["name"]
        )

        return selected

    except (iterm2.RPCException, ValueError, TypeError) as e:
        logger.error(
            "Dialog error occurred",
            operation="show_layout_selector",
            status="failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return None


# =============================================================================
# Git Worktree Detection (Optional)
# Discovers worktrees using <root>.worktree-* naming convention
# =============================================================================


def extract_slug(worktree_path: str, prefix: str) -> str:
    """
    Extract slug from worktree path.

    Example: my-project.worktree-2025-01-15-feature-branch-name
             → feature-branch-name
    """
    basename = os.path.basename(worktree_path)
    # Remove prefix (e.g., "my-project.worktree-")
    if basename.startswith(prefix):
        remainder = basename[len(prefix):]
        # Remove date: YYYY-MM-DD-
        parts = remainder.split("-", 3)
        if len(parts) >= 4:
            return parts[3]  # slug after date
        return remainder
    return basename


def generate_acronym(slug: str) -> str:
    """
    Generate acronym from slug words.

    Example: feature-branch-name → fbn
    """
    words = slug.split("-")
    return "".join(word[0].lower() for word in words if word)


def discover_worktrees(config: dict) -> list[dict]:
    """
    Discover git worktrees dynamically based on config.

    Args:
        config: Configuration dict with worktrees section

    Returns:
        List of tab configs: [{"name": "AF-ssv", "dir": "/path/to/worktree"}]
    """
    worktree_config = config.get("worktrees", {})
    root = worktree_config.get("alpha_forge_root")

    # Worktree discovery disabled if no root configured
    if not root:
        return []

    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return []

    # Get pattern from config or derive from root basename
    pattern = worktree_config.get("worktree_pattern")
    if not pattern:
        # Derive pattern from root: ~/projects/my-repo → my-repo.worktree-*
        root_name = os.path.basename(root)
        pattern = f"{root_name}.worktree-*"

    # Build glob pattern in parent directory
    parent_dir = os.path.dirname(root)
    glob_pattern = os.path.join(parent_dir, pattern)
    candidates = glob.glob(glob_pattern)

    if not candidates:
        return []

    # Validate with git worktree list
    try:
        result = subprocess.run(
            ["git", "worktree", "list"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,  # Handle non-zero returncode explicitly below
        )
        if result.returncode != 0:
            logger.warning(
                "Git worktree list failed",
                operation="discover_worktrees",
                status="failed",
                root=root,
                returncode=result.returncode,
                stderr=result.stderr.strip() if result.stderr else None
            )
            return []

        # Parse valid worktree paths from output
        valid_paths = set()
        for line in result.stdout.strip().split("\n"):
            if line:
                # Format: /path/to/worktree  abc1234 [branch-name]
                parts = line.split()
                if parts:
                    valid_paths.add(parts[0])
    except subprocess.TimeoutExpired:
        logger.error(
            "Git worktree list timed out",
            operation="discover_worktrees",
            status="timeout",
            root=root,
            timeout_seconds=5
        )
        return []
    except FileNotFoundError:
        logger.error(
            "Git command not found",
            operation="discover_worktrees",
            status="git_not_found",
            root=root
        )
        return []

    # Filter and generate tab configs
    # Derive prefix for slug extraction (e.g., "my-project.worktree-")
    root_name = os.path.basename(root)
    prefix = f"{root_name}.worktree-"

    tabs = []
    for path in sorted(candidates):
        if path in valid_paths:
            slug = extract_slug(path, prefix)
            acronym = generate_acronym(slug)
            # Use root basename for tab prefix (e.g., "MP" for my-project)
            tab_prefix = "".join(word[0].upper() for word in root_name.split("-") if word)
            tabs.append({"name": f"{tab_prefix}-{acronym}", "dir": path})

    return tabs


# =============================================================================
# Universal Worktree Detection (All Git Repos)
# =============================================================================


def get_enabled_scan_directories(prefs: dict) -> list[Path]:
    """
    Get list of enabled scan directories from preferences.

    Args:
        prefs: Preferences dict with scan_directories key

    Returns:
        List of Path objects for enabled directories
    """
    scan_dirs = prefs.get("scan_directories", DEFAULT_SCAN_DIRECTORIES)
    enabled_dirs = []

    for scan_dir in scan_dirs:
        if scan_dir.get("enabled", True):
            path = Path(scan_dir["path"]).expanduser()
            enabled_dirs.append(path)

    return enabled_dirs


def discover_all_directories(
    scan_directories: list[Path] | None = None,
    exclude_dirs: set[Path] | None = None
) -> tuple[list[dict], list[dict]]:
    """
    Single-pass discovery of git repos AND untracked folders.

    Performance optimization: iterates filesystem once instead of twice.

    Args:
        scan_directories: List of directories to scan (from preferences)
        exclude_dirs: Set of paths to exclude (optional)

    Returns:
        Tuple of (git_repos, untracked_folders) - both as list of dicts
    """
    start_time = time.perf_counter()

    if scan_directories is None:
        scan_directories = []
    if exclude_dirs is None:
        exclude_dirs = set()

    git_repos = []
    untracked = []
    op_trace_id = str(uuid4())

    logger.debug(
        "Starting single-pass directory discovery",
        operation="discover_all_directories",
        status="started",
        trace_id=op_trace_id,
        discovery_dirs=[str(d) for d in scan_directories]
    )

    for base_dir in scan_directories:
        if not base_dir.exists():
            continue

        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            if child in exclude_dirs:
                continue
            # Skip hidden directories for untracked (but not for git repos)
            is_hidden = child.name.startswith(".")

            git_path = child / ".git"
            if git_path.exists():
                # Has .git - check if it's a repo (directory) or worktree (file)
                if git_path.is_dir():
                    # Real git repository
                    git_repos.append({
                        "name": child.name,
                        "dir": str(child)
                    })
                # else: worktree (.git is file) - skip, discovered separately
            elif not is_hidden:
                # No .git and not hidden - untracked folder
                untracked.append({
                    "name": child.name,
                    "dir": str(child)
                })

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.debug(
        "Single-pass discovery complete",
        operation="discover_all_directories",
        status="success",
        trace_id=op_trace_id,
        metrics={
            "repos_found": len(git_repos),
            "untracked_found": len(untracked),
            "duration_ms": duration_ms
        }
    )

    return (
        sorted(git_repos, key=lambda x: x["name"]),
        sorted(untracked, key=lambda x: x["name"])
    )


def discover_git_repos(
    scan_directories: list[Path] | None = None,
    exclude_dirs: set[Path] | None = None
) -> list[dict]:
    """
    Find git repositories in discovery directories.

    Note: For better performance, use discover_all_directories() which does
    a single filesystem pass for both repos and untracked folders.

    Args:
        scan_directories: List of directories to scan (from preferences)
        exclude_dirs: Set of paths to exclude (optional)

    Returns:
        List of dicts: {"name": "repo-name", "dir": "/path/to/repo"}
    """
    repos, _ = discover_all_directories(scan_directories, exclude_dirs)
    return repos


def discover_untracked_folders(
    scan_directories: list[Path] | None = None,
    exclude_dirs: set[Path] | None = None
) -> list[dict]:
    """
    Find directories that are NOT git repositories (untracked folders).

    Note: For better performance, use discover_all_directories() which does
    a single filesystem pass for both repos and untracked folders.

    Args:
        scan_directories: List of directories to scan (from preferences)
        exclude_dirs: Set of paths to exclude (optional)

    Returns:
        List of dicts: {"name": "folder-name", "dir": "/path/to/folder"}
    """
    _, untracked = discover_all_directories(scan_directories, exclude_dirs)
    return untracked


def discover_all_worktrees(git_repos: list[dict]) -> list[dict]:
    """
    Discover git worktrees from ALL git repositories.

    Scans each git repo and returns any worktrees found (excluding main worktree).

    Args:
        git_repos: List of dicts with "name" and "dir" keys (from discover_git_repos)

    Returns:
        List of dicts: {"name": "repo.wt-branch", "dir": "/path/to/worktree", "parent": "repo-name"}
    """
    start_time = time.perf_counter()
    discovered = []
    op_trace_id = str(uuid4())

    logger.debug(
        "Starting universal worktree discovery",
        operation="discover_all_worktrees",
        status="started",
        trace_id=op_trace_id,
        metrics={"repos_to_scan": len(git_repos)}
    )

    for repo in git_repos:
        repo_path = Path(repo["dir"]).expanduser()
        if not repo_path.exists():
            logger.debug(
                "Skipping non-existent repo path",
                operation="discover_all_worktrees",
                trace_id=op_trace_id,
                repo=repo["name"],
                path=str(repo_path)
            )
            continue

        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
                timeout=10  # Prevent hanging on slow filesystems
            )

            # Parse porcelain output
            # Format: worktree /path\nHEAD sha\nbranch refs/heads/name\n\n
            # OR for detached: worktree /path\nHEAD sha\ndetached\n\n
            current_worktree = {}
            is_prunable = False

            for line in result.stdout.split("\n"):
                if line.startswith("worktree "):
                    # Save previous worktree if valid
                    if current_worktree and current_worktree.get("name") and not is_prunable:
                        discovered.append(current_worktree)
                    # Reset for new worktree
                    current_worktree = {}
                    is_prunable = False

                    wt_path = Path(line[9:])  # Remove "worktree " prefix
                    # Skip main worktree (same as repo path)
                    if wt_path.resolve() == repo_path.resolve():
                        current_worktree = {}  # Reset, don't save main
                        continue
                    # Skip if directory doesn't exist
                    if not wt_path.is_dir():
                        current_worktree = {}
                        continue
                    current_worktree = {
                        "dir": str(wt_path),
                        "parent": repo["name"]
                    }
                elif line.startswith("branch "):
                    branch = line.split("/")[-1]  # refs/heads/feature -> feature
                    if current_worktree:
                        # Name format: RepoAbbrev.wt-branch
                        abbrev = repo["name"][:2].upper()
                        current_worktree["name"] = f"{abbrev}.wt-{branch}"
                elif line == "detached":
                    # Handle detached HEAD worktrees
                    if current_worktree:
                        abbrev = repo["name"][:2].upper()
                        # Use directory name for detached worktrees
                        dir_name = Path(current_worktree["dir"]).name
                        current_worktree["name"] = f"{abbrev}.wt-{dir_name}"
                        current_worktree["detached"] = True
                elif line.startswith("prunable"):
                    # Skip prunable worktrees (missing directory)
                    is_prunable = True

            # Don't forget last worktree
            if current_worktree and current_worktree.get("name") and not is_prunable:
                discovered.append(current_worktree)

        except subprocess.CalledProcessError as e:
            logger.warning(
                "Failed to list worktrees for repo",
                operation="discover_all_worktrees",
                status="failed",
                trace_id=op_trace_id,
                repo=repo["name"],
                error=str(e.stderr) if e.stderr else "unknown"
            )
            continue
        except subprocess.TimeoutExpired:
            logger.warning(
                "Timeout listing worktrees for repo",
                operation="discover_all_worktrees",
                status="timeout",
                trace_id=op_trace_id,
                repo=repo["name"]
            )
            continue

    # Deduplicate by directory path (same worktree can be found from multiple repos)
    seen_dirs = set()
    unique_worktrees = []
    for wt in discovered:
        wt_dir = Path(wt["dir"]).resolve()
        if wt_dir not in seen_dirs:
            seen_dirs.add(wt_dir)
            unique_worktrees.append(wt)

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.debug(
        "Universal worktree discovery complete",
        operation="discover_all_worktrees",
        status="success",
        trace_id=op_trace_id,
        metrics={
            "worktrees_found": len(unique_worktrees),
            "duplicates_removed": len(discovered) - len(unique_worktrees),
            "duration_ms": duration_ms
        }
    )

    return unique_worktrees

