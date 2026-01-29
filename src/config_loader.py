# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Configuration Loading
# =============================================================================

# =============================================================================
# Workspace Launcher Configuration
# =============================================================================

CONFIG_DIR = Path("~/.config/workspace-launcher").expanduser()
WORKSPACE_PATTERN = "workspace-*.toml"
PREFERENCES_PATH = CONFIG_DIR / "preferences.toml"

# Legacy paths (for backward compatibility / migration)
LEGACY_CONFIG_DIR = Path("~/.config/iterm2").expanduser()
LEGACY_LAYOUT_PATTERN = "layout-*.toml"
LEGACY_CONFIG_PATH = LEGACY_CONFIG_DIR / "layout.toml"
LEGACY_PREFERENCES_PATH = LEGACY_CONFIG_DIR / "selector-preferences.toml"

# Default configuration - safe values that work without user config
# Uses universally available commands (no broot, no custom tools)
DEFAULT_CONFIG = {
    "layout": {
        "left_pane_ratio": 0.20,
        "settle_time": 0.3,
    },
    "commands": {
        "left": "ls -la",   # Safe default (broot requires installation)
        "right": "zsh",     # Safe default (not claude-smart-start)
    },
    "profiles": {
        "left": None,   # Use default profile if not specified
        "right": None,  # Use "Claude Code" profile for larger font
    },
    "worktrees": {
        "alpha_forge_root": None,  # Disabled by default
        "worktree_pattern": "*.worktree-*",
    },
    "tabs": [],  # Empty - user must configure
}


# Safe fallback commands when configured commands aren't available
SAFE_LEFT_COMMAND = "ls -la"
SAFE_RIGHT_COMMAND = "zsh"

# =============================================================================
# Shell Alias Introspection
# =============================================================================
# ADR: docs/adr/2026-01-17-shell-alias-resolution.md
# Query zsh for aliases at runtime, with fallback to hardcoded known aliases.


def get_shell_aliases() -> dict[str, str]:
    """
    Query zsh for defined aliases at runtime.

    Returns:
        dict mapping alias names to their targets
        e.g., {"br": "broot", "hx": "helix"}
    """
    try:
        result = subprocess.run(
            ["zsh", "-ic", "alias -L"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,  # Graceful degradation: non-zero exit returns empty aliases
            env={**os.environ, "TERM": "dumb"}  # Suppress terminal escape codes
        )
        if result.returncode != 0:
            return {}
        return _parse_alias_output(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {}


def _parse_alias_output(output: str) -> dict[str, str]:
    """
    Parse `alias -L` output into a dict.

    Example input:
        alias br='broot --sort-by-type-dirs-first'
        alias hx=helix
        alias lg='lazygit'

    Returns:
        {"br": "broot", "hx": "helix", "lg": "lazygit"}
    """
    aliases = {}
    # Pattern: alias name='command args' or alias name=command
    pattern = re.compile(r"^alias\s+(\w+)=['\"]?(\S+)")

    for line in output.strip().split("\n"):
        if not line.strip():
            continue
        match = pattern.match(line)
        if match:
            alias_name = match.group(1)
            # Extract just the command name (first word)
            target = match.group(2).split()[0].rstrip("'\"")
            aliases[alias_name] = target

    return aliases


class CommandResolver:
    """Resolve commands with alias and PATH lookup."""

    _cached_aliases: dict[str, str] | None = None

    @classmethod
    def get_aliases(cls) -> dict[str, str]:
        """Get shell aliases, caching result for session."""
        if cls._cached_aliases is None:
            cls._cached_aliases = get_shell_aliases()
            if cls._cached_aliases:
                logger.debug(
                    "Shell aliases discovered",
                    operation="get_aliases",
                    status="success",
                    count=len(cls._cached_aliases)
                )
            else:
                logger.debug(
                    "No shell aliases discovered, using fallback",
                    operation="get_aliases",
                    status="fallback"
                )
        return cls._cached_aliases

    @classmethod
    def resolve(cls, cmd: str) -> str | None:
        """Resolve command through aliases and PATH."""
        aliases = cls.get_aliases()
        resolved = aliases.get(cmd, cmd)
        return shutil.which(resolved)


# Fallback aliases when runtime shell query fails
# Used only if CommandResolver.get_aliases() returns empty
KNOWN_ALIASES = {
    "br": "broot",      # broot file navigator
    "ll": "ls",         # common ls alias
    "la": "ls",         # common ls alias
    "g": "git",         # common git alias
    "v": "nvim",        # common vim aliases
    "vim": "nvim",
}


def validate_command(command: str, fallback: str) -> str:
    """
    Validate that a command exists, falling back to safe default if not.

    Resolution order:
    1. Check if binary exists directly in PATH
    2. Try runtime shell alias resolution via CommandResolver
    3. Fall back to hardcoded KNOWN_ALIASES
    4. If all fail, use fallback command

    Args:
        command: The command to validate (e.g., "br --sort-by-type-dirs-first")
        fallback: Safe fallback command (e.g., "ls -la")

    Returns:
        Original command if binary found, otherwise fallback
    """
    if not command:
        return fallback

    # Extract the binary name (first word)
    parts = command.split()
    if not parts:
        return fallback

    binary = parts[0]

    # Check if binary exists in PATH
    if shutil.which(binary):
        return command

    # Try runtime shell alias resolution (queries zsh, cached for session)
    runtime_aliases = CommandResolver.get_aliases()
    if binary in runtime_aliases:
        actual_binary = runtime_aliases[binary]
        if shutil.which(actual_binary):
            logger.debug(
                "Using runtime shell alias",
                operation="validate_command",
                alias=binary,
                actual_binary=actual_binary,
                source="zsh"
            )
            return command  # Keep original command - shell will resolve alias

    # Fall back to hardcoded aliases if runtime query returned empty
    if binary in KNOWN_ALIASES:
        actual_binary = KNOWN_ALIASES[binary]
        if shutil.which(actual_binary):
            logger.debug(
                "Using fallback known alias",
                operation="validate_command",
                alias=binary,
                actual_binary=actual_binary,
                source="KNOWN_ALIASES"
            )
            return command  # Keep original command - shell will resolve alias

    # Binary not found - log warning and fallback
    logger.warning(
        "Command not found - using fallback",
        operation="validate_command",
        configured_command=command,
        missing_binary=binary,
        fallback_command=fallback
    )
    return fallback


def extract_toml_error_context(error: tomllib.TOMLDecodeError, file_path: Path) -> dict:
    """
    Extract line context from TOML parse error.

    Args:
        error: The TOMLDecodeError exception
        file_path: Path to the TOML file

    Returns:
        Dict with line_number, line_content, and formatted_message
    """
    error_str = str(error)
    line_number = None
    line_content = None

    # Try to extract line number from error message
    # Common formats: "line 15", "at line 15", "(line 15)"
    line_match = re.search(r'line\s+(\d+)', error_str, re.IGNORECASE)
    if line_match:
        line_number = int(line_match.group(1))

    # If we have a line number, read that line from the file
    if line_number and file_path.exists():
        try:
            with open(file_path, "r") as f:
                lines = f.readlines()
                if 0 < line_number <= len(lines):
                    line_content = lines[line_number - 1].rstrip()
        except OSError:
            pass

    # Format helpful message
    if line_number:
        formatted = f"Error on line {line_number}"
        if line_content:
            # Truncate long lines
            display_line = line_content[:50] + "..." if len(line_content) > 50 else line_content
            formatted += f": {display_line}"
        formatted += f"\n\nDetails: {error_str}"
    else:
        formatted = f"TOML parse error: {error_str}"

    return {
        "line_number": line_number,
        "line_content": line_content,
        "formatted_message": formatted,
        "raw_error": error_str
    }


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base dictionary."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict | None:
    """
    Load configuration from TOML file with defaults fallback.

    Returns:
        dict: Merged configuration, or None if config file missing/invalid
    """
    if not LEGACY_CONFIG_PATH.exists():
        return None

    try:
        with open(LEGACY_CONFIG_PATH, "rb") as f:
            user_config = tomllib.load(f)
        return deep_merge(DEFAULT_CONFIG, user_config)
    except tomllib.TOMLDecodeError as e:
        error_context = extract_toml_error_context(e, LEGACY_CONFIG_PATH)
        logger.error(
            "Invalid TOML syntax in configuration file",
            operation="load_config",
            status="failed",
            file=str(LEGACY_CONFIG_PATH),
            line_number=error_context["line_number"],
            line_content=error_context["line_content"],
            error=error_context["formatted_message"]
        )
        return None


def load_config_from_path(config_path: Path) -> Result[dict]:
    """
    Load configuration from specified TOML file with defaults fallback.

    Args:
        config_path: Path to the layout TOML file

    Returns:
        Result[dict]: Ok with merged config, or Err with error details
    """
    start_time = time.perf_counter()
    logger.debug(
        "Loading config from path",
        operation="load_config_from_path",
        status="started",
        config_path=str(config_path)
    )

    if not config_path.exists():
        logger.error(
            "Config file not found",
            operation="load_config_from_path",
            status="failed",
            config_path=str(config_path)
        )
        return Result.err(Error(
            error_type=ErrorType.FILE_NOT_FOUND,
            message=f"Config file not found: {config_path}",
            context={"config_path": str(config_path)}
        ))

    try:
        with open(config_path, "rb") as f:
            user_config = tomllib.load(f)

        merged = deep_merge(DEFAULT_CONFIG, user_config)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        logger.debug(
            "Config loaded successfully",
            operation="load_config_from_path",
            status="success",
            config_path=str(config_path),
            metrics={"tabs_count": len(merged.get("tabs", [])), "duration_ms": duration_ms}
        )

        return Result.ok(merged)

    except tomllib.TOMLDecodeError as e:
        error_context = extract_toml_error_context(e, config_path)
        logger.error(
            "Invalid TOML syntax in configuration file",
            operation="load_config_from_path",
            status="failed",
            file=str(config_path),
            line_number=error_context["line_number"],
            line_content=error_context["line_content"],
            error=error_context["formatted_message"]
        )
        return Result.err(Error(
            error_type=ErrorType.PARSE_ERROR,
            message=error_context["formatted_message"],
            context={"config_path": str(config_path), "line_number": error_context["line_number"]},
            original_exception=e
        ))

