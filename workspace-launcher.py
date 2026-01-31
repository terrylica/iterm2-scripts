#!/usr/bin/env python3
# ruff: noqa: F401
# /// script
# requires-python = ">=3.13"
# dependencies = ["iterm2", "pyobjc", "loguru", "platformdirs"]
# ///
"""
Workspace Launcher for iTerm2
Creates tabs with left/right splits (left pane narrow, right pane wide)
Maximizes window to fill screen

Configuration: ~/.config/workspace-launcher/workspace-*.toml
Design: modular source concatenation for iTerm2 AutoLaunch

Features:
- Workspace selector dialog for multiple configurations
- Multi-layer selection: workspace choice + tab customization
- TOML-based configuration for workspace tabs
- Universal worktree detection (all git repos)
- Structured JSONL logging (machine-readable)
- Graceful error handling with Script Console output
- First-run wizard for new users
- Portable defaults (no hardcoded paths or tools)
"""

import asyncio
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Generic, TypeVar
from uuid import uuid4

# =============================================================================
# PATH Augmentation for iTerm2 AutoLaunch Environment
# =============================================================================
# iTerm2 AutoLaunch scripts run with minimal macOS PATH (just /usr/bin:/bin:/usr/sbin:/sbin)
# This doesn't include Homebrew or other common tool locations.
# We augment PATH early so shutil.which() can find installed tools like broot, claude, etc.

_ADDITIONAL_PATHS = [
    "/opt/homebrew/bin",      # Homebrew on Apple Silicon
    "/opt/homebrew/sbin",     # Homebrew sbin on Apple Silicon
    "/usr/local/bin",         # Homebrew on Intel / user binaries
    "/usr/local/sbin",        # Intel Homebrew sbin
    os.path.expanduser("~/.local/bin"),  # User local binaries (uv, pipx, etc.)
    os.path.expanduser("~/bin"),          # User personal scripts
    os.path.expanduser("~/.cargo/bin"),   # Rust/Cargo binaries
]

def _augment_path() -> None:
    """
    Augment PATH with common macOS tool locations.

    Called early at module load time to ensure shutil.which() can find
    tools installed via Homebrew, cargo, pipx, etc.
    """
    current_path = os.environ.get("PATH", "")
    path_dirs = current_path.split(os.pathsep)

    # Prepend additional paths that aren't already present
    for additional in reversed(_ADDITIONAL_PATHS):
        if additional not in path_dirs and os.path.isdir(additional):
            path_dirs.insert(0, additional)

    os.environ["PATH"] = os.pathsep.join(path_dirs)

# Run PATH augmentation immediately at module load
_augment_path()


def show_import_error_dialog(package: str, error_msg: str) -> None:
    """
    Show visible osascript dialog when imports fail.

    This function works without any external dependencies since it uses
    osascript directly. Shows a native macOS dialog to inform users about
    missing packages.

    Args:
        package: Name of the missing package
        error_msg: The actual error message
    """
    message = (
        f"Missing Python package: {package}\\n\\n"
        f"Run this command to install:\\n"
        f"uv pip install {package}\\n\\n"
        f"Error: {error_msg}"
    )
    title = "Workspace Launcher - Import Error"

    # AppleScript dialog that works without any Python dependencies
    applescript = f'''
    display dialog "{message}" with title "{title}" buttons {{"OK"}} default button "OK" with icon stop
    '''

    try:
        subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            timeout=30,
            check=False
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        # If even osascript fails, at least print to stderr
        sys.stderr.write(f"ERROR: {message.replace(chr(92) + 'n', chr(10))}\n")
        sys.stderr.write(f"(osascript also failed: {e})\n")


# Import external packages with visible error dialogs
try:
    import iterm2
except ImportError as e:
    show_import_error_dialog("iterm2", str(e))
    sys.exit(1)

try:
    import platformdirs
except ImportError as e:
    show_import_error_dialog("platformdirs", str(e))
    sys.exit(1)

try:
    from AppKit import NSScreen
except ImportError as e:
    show_import_error_dialog("pyobjc", str(e))
    sys.exit(1)

try:
    from loguru import logger
except ImportError as e:
    show_import_error_dialog("loguru", str(e))
    sys.exit(1)


# =============================================================================
# Module: logging_config.py
# =============================================================================

# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Structured Logging Setup (JSONL format)
# =============================================================================

# Correlation ID for async operations
trace_id_var: ContextVar[str] = ContextVar('trace_id', default=None)

T = TypeVar('T')


def json_sink(message):
    """JSONL sink for Claude Code analysis - writes to stderr."""
    record = message.record
    log_entry = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": record["level"].name.lower(),
        "component": record["function"],
        "operation": record["extra"].get("operation", "unknown"),
        "operation_status": record["extra"].get("status", None),
        "trace_id": record["extra"].get("trace_id") or trace_id_var.get(),
        "message": record["message"],
        "context": {k: v for k, v in record["extra"].items()
                   if k not in ("operation", "status", "trace_id", "metrics")},
        "metrics": record["extra"].get("metrics", {}),
        "error": None
    }

    if record["exception"]:
        exc_type, exc_value, exc_tb = record["exception"]
        tb_lines = []
        if exc_tb:
            tb_lines = traceback.format_tb(exc_tb)

        log_entry["error"] = {
            "type": exc_type.__name__ if exc_type else "Unknown",
            "message": str(exc_value) if exc_value else "Unknown error",
            "traceback_lines": tb_lines
        }

    sys.stderr.write(json.dumps(log_entry) + "\n")


def setup_logger():
    """Configure Loguru for machine-readable JSONL output."""
    logger.remove()

    # Console output (JSONL to stderr via custom sink)
    logger.add(
        json_sink,
        level="INFO"
    )

    # File output with rotation (using platformdirs for cross-platform support)
    # macOS: ~/Library/Logs/iterm2-layout/
    # Linux: ~/.local/state/iterm2-layout/log/
    log_dir = Path(platformdirs.user_log_dir(
        appname="iterm2-layout",
        ensure_exists=True
    ))

    logger.add(
        str(log_dir / "layout.jsonl"),
        format="{message}",
        serialize=True,
        rotation="10 MB",
        retention="7 days",
        compression="gz",
        level="DEBUG"
    )

    return logger

# =============================================================================
# Module: errors.py
# =============================================================================

# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Error Handling Types (Result + ErrorReport)
# =============================================================================


class ErrorType(Enum):
    FILE_NOT_FOUND = "file_not_found"
    PARSE_ERROR = "parse_error"
    VALIDATION_ERROR = "validation_error"
    ASYNC_ERROR = "async_error"
    PERMISSION_ERROR = "permission_error"
    TIMEOUT_ERROR = "timeout_error"


@dataclass
class Error:
    error_type: ErrorType
    message: str
    context: dict = field(default_factory=dict)
    original_exception: Exception = None


@dataclass
class Result(Generic[T]):
    success: bool
    value: T = None
    error: Error = None

    @staticmethod
    def ok(value: T) -> 'Result[T]':
        return Result(success=True, value=value)

    @staticmethod
    def err(error: Error) -> 'Result[T]':
        return Result(success=False, error=error)

    def is_ok(self) -> bool:
        return self.success

    def is_err(self) -> bool:
        return not self.success


@dataclass
class ErrorReport:
    errors: list[Error] = field(default_factory=list)
    warnings: list[Error] = field(default_factory=list)

    def add_error(self, error: Error):
        self.errors.append(error)
        logger.error(
            error.message,
            operation="error_report",
            status="error",
            error_type=error.error_type.value,
            **error.context
        )

    def add_warning(self, error: Error):
        self.warnings.append(error)
        logger.warning(
            error.message,
            operation="error_report",
            status="warning",
            error_type=error.error_type.value,
            **error.context
        )

    def collect_result(self, result: Result, context: str = "") -> bool:
        """Collect error from Result into report if failed."""
        if result.is_err():
            self.add_error(result.error)
            return False
        return True

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def log_summary(self, op_trace_id: str):
        """Log final summary for Claude Code analysis."""
        logger.info(
            "Operation complete",
            operation="error_report",
            status="complete",
            trace_id=op_trace_id,
            metrics={
                "total_errors": len(self.errors),
                "total_warnings": len(self.warnings)
            }
        )

# =============================================================================
# Module: config_loader.py
# =============================================================================

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

# =============================================================================
# Module: preferences.py
# =============================================================================

# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Workspace Discovery Functions
# =============================================================================


def discover_layouts() -> list[dict]:
    """
    Discover available workspace files in config directory.

    Scans CONFIG_DIR for files matching WORKSPACE_PATTERN (workspace-*.toml).

    Returns:
        List of dicts with keys: name, display, path, tab_count
        Example: [{"name": "full", "display": "full (29 tabs)",
                   "path": Path(...), "tab_count": 29}, ...]
    """
    start_time = time.perf_counter()
    layouts = []
    op_trace_id = str(uuid4())

    logger.debug(
        "Starting layout discovery",
        operation="discover_layouts",
        status="started",
        trace_id=op_trace_id,
        config_dir=str(CONFIG_DIR),
        pattern=WORKSPACE_PATTERN
    )

    for path in sorted(CONFIG_DIR.glob(WORKSPACE_PATTERN)):
        logger.debug(
            "Found layout file",
            operation="discover_layouts",
            trace_id=op_trace_id,
            file=path.name
        )

        # Extract display name: workspace-{name}.toml -> {name}
        match = re.match(r"workspace-(.+)\.toml$", path.name)
        if not match:
            logger.debug(
                "Skipping file - doesn't match pattern",
                operation="discover_layouts",
                trace_id=op_trace_id,
                file=path.name
            )
            continue

        name = match.group(1)

        # Parse file to count tabs
        try:
            with open(path, "rb") as f:
                config = tomllib.load(f)
            tab_count = len(config.get("tabs", []))

            layout = {
                "name": name,
                "display": f"{name} ({tab_count} tabs)",
                "path": path,
                "tab_count": tab_count,
            }
            layouts.append(layout)

            logger.debug(
                "Added layout",
                operation="discover_layouts",
                trace_id=op_trace_id,
                layout_name=name,
                metrics={"tab_count": tab_count}
            )

        except tomllib.TOMLDecodeError as e:
            error_context = extract_toml_error_context(e, path)
            logger.warning(
                "Skipping layout file due to invalid TOML",
                operation="discover_layouts",
                status="skip",
                trace_id=op_trace_id,
                file=path.name,
                line_number=error_context["line_number"],
                error=error_context["formatted_message"]
            )
        except (OSError, KeyError, TypeError) as e:
            logger.warning(
                "Skipping layout file due to error",
                operation="discover_layouts",
                status="skip",
                trace_id=op_trace_id,
                file=path.name,
                error=str(e),
                error_type=type(e).__name__
            )

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.debug(
        "Layout discovery complete",
        operation="discover_layouts",
        status="success",
        trace_id=op_trace_id,
        metrics={"layouts_found": len(layouts), "duration_ms": duration_ms}
    )

    return layouts


# Default directories to scan for git repos
# Empty by default for portability - users configure via Settings or first-run wizard
DEFAULT_SCAN_DIRECTORIES: list[dict[str, str | bool]] = []


def load_preferences() -> dict:
    """
    Load selector preferences from TOML file.

    Returns:
        dict with keys: remember_choice (bool), last_layout (str|None),
        scan_directories (list of {"path": str, "enabled": bool})
    """
    defaults = {
        "remember_choice": False,
        "last_layout": None,
        "scan_directories": DEFAULT_SCAN_DIRECTORIES.copy(),
        "custom_tab_names": {},  # path -> shorthand name mappings
        "disabled_layouts": [],  # layout names to hide from selector
    }

    if not PREFERENCES_PATH.exists():
        logger.debug(
            "Preferences file does not exist, using defaults",
            operation="load_preferences",
            status="default",
            file=str(PREFERENCES_PATH)
        )
        return defaults

    try:
        with open(PREFERENCES_PATH, "rb") as f:
            prefs = tomllib.load(f)

        result = {**defaults, **prefs}

        # Ensure scan_directories has proper structure
        if "scan_directories" not in prefs:
            result["scan_directories"] = DEFAULT_SCAN_DIRECTORIES.copy()

        logger.debug(
            "Preferences loaded successfully",
            operation="load_preferences",
            status="success",
            remember_choice=result.get("remember_choice"),
            last_layout=result.get("last_layout"),
            scan_directories_count=len(result.get("scan_directories", []))
        )
        return result

    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError) as e:
        logger.warning(
            "Failed to load preferences, using defaults",
            operation="load_preferences",
            status="fallback",
            file=str(PREFERENCES_PATH),
            error=str(e),
            error_type=type(e).__name__
        )
        return defaults


def atomic_write_file(path: Path, content: str) -> None:
    """
    Write file atomically using temp file → fsync → rename pattern.

    This ensures the file is never partially written, even if the system
    crashes or disk fills up during the write.

    Args:
        path: Target file path
        content: Content to write

    Raises:
        OSError: If write fails (including disk full - errno.ENOSPC)
    """
    import errno

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (for atomic rename)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp"
    )

    try:
        # Write content
        with os.fdopen(temp_fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # Ensure data hits disk

        # Atomic rename
        os.rename(temp_path, path)

        logger.debug(
            "Atomic file write successful",
            operation="atomic_write_file",
            path=str(path)
        )

    except OSError as e:
        # Clean up temp file on failure
        try:
            os.unlink(temp_path)
        except OSError as cleanup_error:
            logger.debug(
                "Could not clean up temp file",
                path=temp_path,
                error=str(cleanup_error),
                operation="atomic_write_file"
            )

        # Provide clear message for disk full
        if e.errno == errno.ENOSPC:
            raise OSError(f"Disk full - cannot write to {path}") from e
        raise


def save_preferences(prefs: dict) -> None:
    """
    Save selector preferences to TOML file atomically.

    Uses atomic write pattern (temp file → fsync → rename) to prevent
    corruption from partial writes.

    Args:
        prefs: dict with remember_choice, last_layout, scan_directories keys
    """
    lines = [
        "# Workspace Launcher Preferences",
        "# Auto-generated by workspace-launcher.py",
        "# Delete this file to reset and show selector dialog again",
        "",
        f"remember_choice = {'true' if prefs.get('remember_choice') else 'false'}",
    ]

    if prefs.get("last_layout"):
        lines.append(f'last_layout = "{prefs["last_layout"]}"')

    # Add new preference fields for Layer 2
    if prefs.get("skip_tab_customization") is not None:
        lines.append(f"skip_tab_customization = {'true' if prefs.get('skip_tab_customization') else 'false'}")

    if prefs.get("last_tab_selections"):
        # Format as TOML array
        tabs_str = ", ".join(f'"{t}"' for t in prefs["last_tab_selections"])
        lines.append(f"last_tab_selections = [{tabs_str}]")

    if prefs.get("last_tab_order"):
        # Format as TOML array of dir paths (persists reorder across sessions)
        order_str = ", ".join(f'"{d}"' for d in prefs["last_tab_order"])
        lines.append(f"last_tab_order = [{order_str}]")

    # Save disabled layouts list
    disabled_layouts = prefs.get("disabled_layouts")
    if disabled_layouts:
        layouts_str = ", ".join(f'"{name}"' for name in disabled_layouts)
        lines.append(f"disabled_layouts = [{layouts_str}]")

    # Save custom tab names as TOML inline table
    custom_names = prefs.get("custom_tab_names")
    if custom_names:
        lines.append("")
        lines.append("# Custom shorthand names for tabs (path -> name)")
        lines.append("[custom_tab_names]")
        for path, name in sorted(custom_names.items()):
            # Escape path for TOML key (use quotes for paths with special chars)
            lines.append(f'"{path}" = "{name}"')

    # Save scan directories as TOML array of tables
    scan_dirs = prefs.get("scan_directories")
    if scan_dirs:
        lines.append("")
        lines.append("# Directories to scan for git repos (auto-discovery)")
        lines.append("# Add/remove via 'Manage Directories' option in layout selector")
        for scan_dir in scan_dirs:
            lines.append("")
            lines.append("[[scan_directories]]")
            lines.append(f'path = "{scan_dir["path"]}"')
            lines.append(f"enabled = {'true' if scan_dir.get('enabled', True) else 'false'}")

    content = "\n".join(lines) + "\n"

    try:
        atomic_write_file(PREFERENCES_PATH, content)

        logger.debug(
            "Preferences saved successfully",
            operation="save_preferences",
            status="success",
            file=str(PREFERENCES_PATH),
            remember_choice=prefs.get("remember_choice"),
            last_layout=prefs.get("last_layout"),
            scan_directories_count=len(scan_dirs) if scan_dirs else 0
        )

    except OSError as e:
        logger.error(
            "Failed to save preferences - user choices may not persist",
            operation="save_preferences",
            status="failed",
            file=str(PREFERENCES_PATH),
            error=str(e)
        )


async def reset_preferences(connection, window) -> bool:
    """
    Reset selector preferences to defaults after user confirmation.

    Deletes the preferences.toml file, which will cause:
    - Workspace selector to show on next startup
    - Scan directories to reset to defaults
    - Remembered workspace choice to be cleared

    Args:
        connection: iTerm2 connection
        window: Current iTerm2 window

    Returns:
        True if preferences were reset, False if cancelled
    """
    # Confirm with user
    confirm_alert = iterm2.Alert(
        "Reset Preferences?",
        "This will reset all workspace launcher preferences:\n\n"
        "• Workspace selector will show on startup\n"
        "• Scan directories will be cleared\n"
        "• Tab selections will be forgotten\n\n"
        "Workspace config files will NOT be deleted.",
        window_id=window.window_id
    )
    confirm_alert.add_button("Reset")
    confirm_alert.add_button("Cancel")
    response = await confirm_alert.async_run(connection)

    if response == 1:  # Cancel
        logger.debug(
            "Preference reset cancelled",
            operation="reset_preferences",
            status="cancelled"
        )
        return False

    # Delete preferences file
    try:
        if PREFERENCES_PATH.exists():
            PREFERENCES_PATH.unlink()
            logger.info(
                "Preferences reset successfully",
                operation="reset_preferences",
                status="success",
                file=str(PREFERENCES_PATH)
            )

            success_alert = iterm2.Alert(
                "Preferences Reset",
                "Preferences have been reset.\n\n"
                "Restart iTerm2 for changes to take effect.",
                window_id=window.window_id
            )
            success_alert.add_button("OK")
            await success_alert.async_run(connection)
            return True
        else:
            logger.debug(
                "No preferences file to delete",
                operation="reset_preferences",
                status="no_file"
            )
            return True

    except OSError as e:
        logger.error(
            "Failed to reset preferences",
            operation="reset_preferences",
            status="failed",
            error=str(e)
        )

        error_alert = iterm2.Alert(
            "Reset Failed",
            f"Could not delete preferences file:\n{e}",
            window_id=window.window_id
        )
        error_alert.add_button("OK")
        await error_alert.async_run(connection)
        return False

# =============================================================================
# Module: selector.py
# =============================================================================

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


def discover_git_repos(
    scan_directories: list[Path] | None = None,
    exclude_dirs: set[Path] | None = None
) -> list[dict]:
    """
    Find git repositories in discovery directories.

    Args:
        scan_directories: List of directories to scan (from preferences)
        exclude_dirs: Set of paths to exclude (optional)

    Returns:
        List of dicts: {"name": "repo-name", "dir": "/path/to/repo"}
    """
    start_time = time.perf_counter()

    # Use empty list if not specified (portability - no hardcoded paths)
    if scan_directories is None:
        scan_directories = []

    if exclude_dirs is None:
        exclude_dirs = set()

    repos = []
    op_trace_id = str(uuid4())

    logger.debug(
        "Starting git repo discovery",
        operation="discover_git_repos",
        status="started",
        trace_id=op_trace_id,
        discovery_dirs=[str(d) for d in scan_directories]
    )

    for base_dir in scan_directories:
        if not base_dir.exists():
            logger.debug(
                "Discovery directory does not exist",
                operation="discover_git_repos",
                trace_id=op_trace_id,
                directory=str(base_dir)
            )
            continue

        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            if child in exclude_dirs:
                continue

            git_path = child / ".git"
            if not git_path.exists():
                continue
            # Skip git worktrees - they have .git as a file, not directory
            # Worktrees are discovered separately by discover_all_worktrees()
            if not git_path.is_dir():
                continue

            repos.append({
                "name": child.name,
                "dir": str(child)
            })

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.debug(
        "Git repo discovery complete",
        operation="discover_git_repos",
        status="success",
        trace_id=op_trace_id,
        metrics={"repos_found": len(repos), "duration_ms": duration_ms}
    )

    return sorted(repos, key=lambda x: x["name"])


def discover_untracked_folders(
    scan_directories: list[Path] | None = None,
    exclude_dirs: set[Path] | None = None
) -> list[dict]:
    """
    Find directories that are NOT git repositories (untracked folders).

    These are directories that exist but don't have a .git folder - potentially
    new projects not yet initialized with git.

    Args:
        scan_directories: List of directories to scan (from preferences)
        exclude_dirs: Set of paths to exclude (optional)

    Returns:
        List of dicts: {"name": "folder-name", "dir": "/path/to/folder"}
    """
    start_time = time.perf_counter()

    # Use empty list if not specified (portability - no hardcoded paths)
    if scan_directories is None:
        scan_directories = []

    if exclude_dirs is None:
        exclude_dirs = set()

    folders = []
    op_trace_id = str(uuid4())

    logger.debug(
        "Starting untracked folder discovery",
        operation="discover_untracked_folders",
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
            # Skip hidden directories
            if child.name.startswith("."):
                continue

            git_path = child / ".git"
            # Only include if .git does NOT exist (not a repo, not a worktree)
            if git_path.exists():
                continue

            folders.append({
                "name": child.name,
                "dir": str(child)
            })

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.debug(
        "Untracked folder discovery complete",
        operation="discover_untracked_folders",
        status="success",
        trace_id=op_trace_id,
        metrics={"folders_found": len(folders), "duration_ms": duration_ms}
    )

    return sorted(folders, key=lambda x: x["name"])


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

# =============================================================================
# Module: swiftdialog.py
# =============================================================================

# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# SwiftDialog Utilities
# =============================================================================

# SF Symbol icons per category with status-based coloring
# Format: "SF=symbol_name,colour=color_name,scale=large"
CATEGORY_ICONS = {
    # Category icons (for selectable items) - large scale for visibility
    "layout_tab": "SF=doc.text.fill,colour=blue,scale=large",
    "git_worktree": "SF=arrow.triangle.branch,colour=purple,scale=large",
    "additional_repo": "SF=folder.fill,colour=green,scale=large",
    "untracked": "SF=questionmark.folder,colour=orange,scale=large",
    # Status variants
    "missing_path": "SF=folder.fill,colour=red,scale=large",
    # Header icons (for disabled category separators)
    "header_layout": "SF=doc.text,colour=gray,scale=large",
    "header_worktree": "SF=arrow.triangle.branch,colour=gray,scale=large",
    "header_repo": "SF=folder,colour=gray,scale=large",
    "header_untracked": "SF=questionmark.folder,colour=gray,scale=large",
}

# Cached SwiftDialog path (None = not checked yet, False = not found)
_swiftdialog_path_cache: str | None | bool = None


def find_swiftdialog_path() -> str | None:
    """
    Find SwiftDialog binary across Intel and Apple Silicon Homebrew paths.

    Search order:
    1. /opt/homebrew/bin/dialog (Apple Silicon Homebrew)
    2. /usr/local/bin/dialog (Intel Homebrew)
    3. shutil.which("dialog") (fallback to PATH)

    Returns:
        Path to SwiftDialog binary, or None if not found
    """
    global _swiftdialog_path_cache

    # Return cached result if already checked
    if _swiftdialog_path_cache is not None:
        return _swiftdialog_path_cache if _swiftdialog_path_cache else None

    # Search paths in order of preference
    search_paths = [
        "/opt/homebrew/bin/dialog",  # Apple Silicon Homebrew
        "/usr/local/bin/dialog",      # Intel Homebrew
    ]

    for path in search_paths:
        if Path(path).exists():
            _swiftdialog_path_cache = path
            logger.debug(
                "Found SwiftDialog",
                path=path,
                operation="find_swiftdialog_path",
            )
            return path

    # Fallback to PATH lookup
    path_result = shutil.which("dialog")
    if path_result:
        _swiftdialog_path_cache = path_result
        logger.debug(
            "Found SwiftDialog via PATH",
            path=path_result,
            operation="find_swiftdialog_path",
        )
        return path_result

    # Not found
    _swiftdialog_path_cache = False
    logger.debug(
        "SwiftDialog not found",
        searched=search_paths,
        operation="find_swiftdialog_path",
    )
    return None


def is_swiftdialog_available() -> bool:
    """Check if SwiftDialog is installed."""
    return find_swiftdialog_path() is not None


def is_homebrew_available() -> bool:
    """
    Check if Homebrew is installed and available.

    Returns:
        True if brew command is available in PATH
    """
    return shutil.which("brew") is not None


def run_swiftdialog(config: dict) -> tuple[int, dict | None]:
    """
    Run SwiftDialog with given configuration.

    Args:
        config: Dialog configuration dict (will be written as JSON)

    Returns:
        Tuple of (return_code, parsed_output_dict or None)
        Return codes:
        - 0: Button 1 clicked (e.g., "OK", "Save")
        - 2: Button 2 clicked (e.g., "Cancel")
        - 3: Info button clicked (e.g., "Rename Tabs")
        - 4: Timeout
        - Other: Error
    """
    swiftdialog_bin = find_swiftdialog_path()
    if not swiftdialog_bin:
        logger.error("SwiftDialog not available", operation="run_swiftdialog")
        return (-1, None)

    config_path = None
    # Write config to temp file
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump(config, f)
            config_path = f.name

        # Run SwiftDialog
        cmd = [swiftdialog_bin, "--jsonfile", config_path, "--json"]
        logger.debug(
            "Running SwiftDialog",
            config_path=config_path,
            operation="run_swiftdialog"
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout
            check=False
        )

        # Parse JSON output if available
        output_dict = None
        if result.stdout.strip():
            try:
                output_dict = json.loads(result.stdout)
            except json.JSONDecodeError:
                logger.warning(
                    "Could not parse SwiftDialog output",
                    stdout=result.stdout[:200],
                    operation="run_swiftdialog"
                )

        return (result.returncode, output_dict)

    except subprocess.TimeoutExpired:
        logger.error("SwiftDialog timed out", operation="run_swiftdialog")
        return (4, None)
    except OSError as e:
        logger.error(
            "SwiftDialog OS error",
            error=str(e),
            operation="run_swiftdialog"
        )
        return (-1, None)
    finally:
        # Clean up temp file
        if config_path:
            try:
                Path(config_path).unlink(missing_ok=True)
            except OSError as e:
                logger.debug(
                    "Could not delete temp config file",
                    path=config_path,
                    error=str(e),
                    operation="run_swiftdialog"
                )


def format_tab_label(path: str, name: str, wrap_threshold: int = 50) -> str:
    """
    Format tab label as 'shorthand (path)' with shorthand name prominent.

    If path exceeds wrap_threshold characters, it wraps to a second line
    to avoid clipping by SwiftDialog's 700px checkbox area limit.

    Note: SwiftDialog checkbox area is hardcoded to 700px max width in its
    source code (dataEntryMaxWidth in MessageContentView.swift).

    Args:
        path: Directory path (will be shortened with ~ for home)
        name: Shorthand name (displayed first, prominently)
        wrap_threshold: Path length at which to wrap to second line (default 50)

    Returns:
        Formatted label string: "shorthand (path)" or "shorthand\\n(path)" if long
    """
    # Replace home directory with ~
    path_display = path.replace(str(Path.home()), "~")

    # Wrap long paths to second line to avoid clipping
    if len(path_display) > wrap_threshold:
        return f"{name}\n({path_display})"

    return f"{name} ({path_display})"

# =============================================================================
# Module: layout_toggle.py
# =============================================================================

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

# =============================================================================
# Module: scan_dirs.py
# =============================================================================

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

# =============================================================================
# Module: setup_wizard.py
# =============================================================================

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
            "Required tools (install via Homebrew):\n"
            "• brew install broot (file navigator)\n"
            "• brew install swiftdialog (workspace dialogs)",
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

# =============================================================================
# Module: tool_installer.py
# =============================================================================

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

# =============================================================================
# Module: tab_utils.py
# =============================================================================

# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Tab Utilities
# =============================================================================
# Centralized utilities for tab data handling to ensure consistency across
# all modules. This prevents bugs where display names, paths, or other tab
# properties are computed differently in different parts of the codebase.


def normalize_tab_path(path: str) -> str:
    """Normalize a tab directory path for consistent comparison.

    Expands ~ and resolves symlinks, then strips trailing slashes.
    Use this whenever comparing tab paths for equality.

    Args:
        path: Raw path string (may contain ~ or be relative).

    Returns:
        Absolute normalized path suitable for comparison.
    """
    return os.path.realpath(os.path.expanduser(path)).rstrip("/")


def expand_tab_path(path: str) -> str:
    """Expand ~ in a tab path without resolving symlinks.

    Use this when you need the actual filesystem path but want to
    preserve symlink structure (e.g., for display or cd commands).

    Args:
        path: Raw path string (may contain ~).

    Returns:
        Path with ~ expanded.
    """
    return os.path.expanduser(path)


def get_tab_display_name(
    tab: dict,
    custom_tab_names: dict[str, str] | None = None,
) -> str:
    """Get the display name for a tab with consistent priority.

    This is the SINGLE SOURCE OF TRUTH for tab display names.
    All code that needs to display a tab name should call this function.

    Priority order:
    1. custom_tab_names[dir] - User's custom shorthand name
    2. tab["name"] - Name from workspace config
    3. basename(dir) - Directory name as fallback

    Args:
        tab: Tab configuration dict (must have "dir" key, may have "name").
        custom_tab_names: Optional mapping of dir paths to custom names.

    Returns:
        Display name string for the tab.
    """
    custom_tab_names = custom_tab_names or {}
    path = tab.get("dir", "")
    return (
        custom_tab_names.get(path)
        or tab.get("name")
        or os.path.basename(expand_tab_path(path))
    )


def get_tab_dir(tab: dict) -> str:
    """Get the directory path from a tab config dict.

    Handles both "dir" and legacy "path" keys for compatibility.

    Args:
        tab: Tab configuration dict.

    Returns:
        Directory path string (may contain ~, not expanded).
    """
    return tab.get("dir") or tab.get("path", "")

# =============================================================================
# Module: tab_customization.py
# =============================================================================

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
        # Use 🗂️ emoji on both sides + double-line ═ for Level 2
        sub_header = f"🗂️ {_make_header_label(f'{parent_name}/ ({count})', '═')} 🗂️"
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
    # Level 1 headers use 📌 emoji on both sides + block characters (▓) for visual impact
    # Layout tabs and worktrees use flat list
    flat_categories = [
        (layout_tabs, "layout", f"📌 {_make_header_label('LAYOUT TABS', '▓')} 📌",
         CATEGORY_ICONS["header_layout"], CATEGORY_ICONS["layout_tab"]),
        (worktrees, "worktree", f"📌 {_make_header_label('GIT WORKTREES', '▓')} 📌",
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
    # Level 1 header with 📌 emoji on both sides, Level 2 sub-headers use ═ without emoji
    repo_checkboxes, repo_items = _build_grouped_category_checkboxes(
        additional_repos, "discovered", f"📌 {_make_header_label('ADDITIONAL REPOS', '▓')} 📌",
        CATEGORY_ICONS["header_repo"], CATEGORY_ICONS["additional_repo"],
        custom_tab_names, remembered_selections,
    )
    checkboxes.extend(repo_checkboxes)
    all_items.extend(repo_items)

    # Untracked folders use flat list with 📌 emoji on both sides
    untracked_checkboxes, untracked_items = _build_category_checkboxes(
        untracked_folders, "untracked", f"📌 {_make_header_label('UNTRACKED FOLDERS', '▓')} 📌",
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

# =============================================================================
# Module: pane_setup.py
# =============================================================================

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

# =============================================================================
# Module: tab_detection.py
# =============================================================================

# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there

# =============================================================================
# Tab Detection
# =============================================================================


async def get_open_tab_directories(window) -> set[str]:
    """Return normalized directory paths of all sessions in the current window.

    Queries each session's ``path`` variable via the iTerm2 Python API.
    Uses normalize_tab_path for consistent path comparison.

    Args:
        window: iTerm2 Window object (current terminal window).

    Returns:
        Set of absolute directory paths currently open in the window.
    """
    open_dirs: set[str] = set()
    for tab in window.tabs:
        for session in tab.sessions:
            try:
                path = await session.async_get_variable("path")
            except (iterm2.RPCException, AttributeError, TypeError):
                logger.debug(
                    "Could not query session path",
                    session_id=getattr(session, "session_id", "unknown"),
                )
                continue
            if path:
                open_dirs.add(normalize_tab_path(path))
    return open_dirs


def filter_already_open_tabs(
    all_tabs: list[dict],
    open_dirs: set[str],
    custom_tab_names: dict[str, str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Filter out tabs whose directories are already open.

    Args:
        all_tabs: List of tab config dicts (must have "dir" key).
        open_dirs: Set of normalized directory paths already open.
        custom_tab_names: Optional mapping for display name resolution.

    Returns:
        Tuple of (tabs_to_create, skipped_tab_names).
    """
    tabs_to_create: list[dict] = []
    tabs_skipped: list[str] = []

    for tab_config in all_tabs:
        tab_dir = get_tab_dir(tab_config)
        normalized = normalize_tab_path(tab_dir)
        if normalized in open_dirs:
            # Use centralized utility for consistent name resolution
            tab_name = get_tab_display_name(tab_config, custom_tab_names)
            tabs_skipped.append(tab_name)
            logger.info(
                "Tab skipped - already open",
                tab_name=tab_name,
                tab_dir=tab_dir,
            )
        else:
            tabs_to_create.append(tab_config)

    if tabs_skipped:
        logger.info(
            f"Skipped {len(tabs_skipped)} already-open tab(s)",
            skipped=tabs_skipped,
            creating=len(tabs_to_create),
        )

    return tabs_to_create, tabs_skipped


async def reorder_window_tabs(
    window,
    desired_order: list[str],
    created_tabs: dict[str, object] | None = None,
) -> None:
    """Reorder all tabs in a window to match the desired directory order.

    Uses ``window.async_set_tabs()`` to rearrange already-open tabs.
    Tabs not matching any entry in ``desired_order`` are appended at the end.

    Args:
        window: iTerm2 Window object.
        desired_order: List of directory paths in desired tab order.
        created_tabs: Optional mapping of dir_path → Tab object for newly
            created tabs. Bypasses path query which may fail for fresh tabs.
    """
    created_tabs = created_tabs or {}

    # Build map: normalized dir path → Tab object
    # First, add newly created tabs (path variable may not be set yet)
    dir_to_tab: dict[str, object] = {}
    for dir_path, tab in created_tabs.items():
        dir_to_tab[normalize_tab_path(dir_path)] = tab

    # Then query existing tabs (already-open before this session)
    for tab in window.tabs:
        if tab.tab_id in {t.tab_id for t in created_tabs.values()}:
            continue  # Already tracked via created_tabs
        for session in tab.sessions:
            try:
                path = await session.async_get_variable("path")
            except (iterm2.RPCException, AttributeError, TypeError):
                continue
            if path:
                normalized = normalize_tab_path(path)
                if normalized not in dir_to_tab:
                    dir_to_tab[normalized] = tab
                break  # Use first session's path per tab

    # Build ordered tab list
    ordered_tabs: list[object] = []
    used_tabs: set[str] = set()  # Track tab_ids to avoid duplicates

    for dir_path in desired_order:
        normalized = normalize_tab_path(dir_path)
        tab = dir_to_tab.get(normalized)
        if tab and tab.tab_id not in used_tabs:
            ordered_tabs.append(tab)
            used_tabs.add(tab.tab_id)

    # Append remaining tabs not in desired_order
    for tab in window.tabs:
        if tab.tab_id not in used_tabs:
            ordered_tabs.append(tab)
            used_tabs.add(tab.tab_id)

    if len(ordered_tabs) > 1:
        try:
            await window.async_set_tabs(ordered_tabs)
            logger.info(
                "Window tabs reordered",
                operation="reorder_window_tabs",
                tab_count=len(ordered_tabs),
            )
        except (iterm2.RPCException, AttributeError, TypeError) as e:
            logger.warning(
                "Failed to reorder window tabs",
                operation="reorder_window_tabs",
                error=str(e),
            )

# =============================================================================
# Module: main.py
# =============================================================================

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
            # Use normalize_tab_path for consistent comparison (handles ~/path vs /Users/path)
            saved_order = prefs.get("last_tab_order")
            if saved_order and len(final_tabs) > 1:
                order_map = {normalize_tab_path(d): i for i, d in enumerate(saved_order)}
                final_tabs.sort(
                    key=lambda t: order_map.get(normalize_tab_path(get_tab_dir(t)), 999)
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
                    # Use normalize_tab_path for consistent storage
                    prefs["last_tab_order"] = [
                        normalize_tab_path(get_tab_dir(t)) for t in all_tabs
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
    # Use get_tab_display_name for consistent name resolution with custom names
    all_tab_names = list(tabs_skipped) + [
        get_tab_display_name(t, custom_tab_names) for t in all_tabs
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