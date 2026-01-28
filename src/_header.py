#!/usr/bin/env python3
# ruff: noqa: F401
# /// script
# requires-python = ">=3.11"
# dependencies = ["iterm2", "pyobjc", "loguru", "platformdirs"]
# ///
"""
Default iTerm2 Layout Script
Creates tabs with left/right splits (left pane narrow, right pane wide)
Maximizes window to fill screen

Configuration: ~/.config/iterm2/layout-*.toml (XDG standard)
ADR: cc-skills/docs/adr/2025-12-15-iterm2-layout-config.md

Features:
- Layout selector dialog for multiple configurations
- Multi-layer selection: layout choice + tab customization
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
    title = "iTerm2 Layout Manager - Import Error"

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
