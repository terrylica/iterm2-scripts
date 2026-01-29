#!/usr/bin/env python3
"""
Build script for iTerm2 Layout Manager.

ADR: docs/adr/2026-01-26-modular-source-concatenation.md

Concatenates src/*.py modules into a single default-layout.py file
that's compatible with iTerm2 AutoLaunch (which requires a single .py file).

Usage:
    python build.py           # Build default-layout.py
    python build.py --check   # Verify output matches (for CI)

Module order matters for dependencies:
1. _header.py       - PEP 723 metadata, docstring, imports, PATH augmentation
2. result.py        - Error/Result types (no deps)
3. logging_setup.py - Logger configuration (depends on result for types)
4. config.py        - Config loading, constants, shell alias introspection
5. preferences.py   - Preferences load/save
6. discovery.py     - Layout/worktree/repo discovery
7. swiftdialog.py   - SwiftDialog utilities (icons, path finding, runner)
8. dialogs.py       - Dialog functions (tab customization, directory management)
9. panes.py         - Tab/pane creation, window management
10. main.py         - Entry point (async main, iterm2.run_until_complete)
"""

import re
import sys
from pathlib import Path

# Module order (dependencies flow downward)
MODULE_ORDER = [
    "_header.py",           # Imports, PEP 723 metadata
    "logging_config.py",    # Loguru structured logging
    "errors.py",            # Error types (Result monad)
    "config_loader.py",     # TOML config loading, shell aliases
    "preferences.py",       # User preferences + layout discovery
    "selector.py",          # Layout selector dialog
    "swiftdialog.py",       # SwiftDialog utilities
    "layout_toggle.py",     # Layout enable/disable
    "scan_dirs.py",         # Scan directories management
    "setup_wizard.py",      # First-run and veteran wizards
    "tool_installer.py",    # Homebrew tool installation
    "tab_customization.py", # Tab selection dialog
    "pane_setup.py",        # Pane creation and commands
    "main.py",              # Entry point
]

SRC_DIR = Path(__file__).parent / "src"
OUTPUT_FILE = Path(__file__).parent / "default-layout.py"

# Imports that should only appear once (in _header.py)
STDLIB_IMPORTS = {
    "import asyncio",
    "import glob",
    "import json",
    "import os",
    "import re",
    "import shlex",
    "import shutil",
    "import subprocess",
    "import sys",
    "import time",
    "import tomllib",
    "import tempfile",
    "import traceback",
    "from contextvars import ContextVar",
    "from dataclasses import dataclass, field",
    "from enum import Enum",
    "from pathlib import Path",
    "from typing import Generic, TypeVar",
    "from uuid import uuid4",
}

# External imports handled specially in _header.py
EXTERNAL_IMPORTS = {
    "import iterm2",
    "import platformdirs",
    "from AppKit import NSScreen",
    "from loguru import logger",
}


def strip_module_imports(content: str) -> str:
    """Remove import statements that are already in _header.py."""
    lines = content.split("\n")
    result = []

    for line in lines:
        stripped = line.strip()
        # Skip empty import lines
        if stripped in STDLIB_IMPORTS or stripped in EXTERNAL_IMPORTS:
            continue
        # Skip common import patterns we handle in header
        if stripped.startswith("from loguru import"):
            continue
        if stripped.startswith("import iterm2"):
            continue
        result.append(line)

    return "\n".join(result)


def strip_module_docstring(content: str) -> str:
    """Remove module-level docstring (we use the one from _header.py)."""
    # Match docstring at start of file (after optional shebang/comments)
    pattern = r'^((?:#[^\n]*\n)*)\s*(?:\'\'\'[\s\S]*?\'\'\'|"""[\s\S]*?""")\s*\n'
    return re.sub(pattern, r'\1', content)


def process_module(path: Path, is_header: bool = False) -> str:
    """Process a single module file for concatenation."""
    content = path.read_text()

    if is_header:
        # Header is used as-is (contains PEP 723, imports, etc.)
        return content

    # Remove shebang if present (only header should have it)
    if content.startswith("#!"):
        content = "\n".join(content.split("\n")[1:])

    # Remove duplicate imports
    content = strip_module_imports(content)

    # Remove module docstring (header has the main one)
    content = strip_module_docstring(content)

    # Remove leading/trailing whitespace but keep internal structure
    content = content.strip()

    return content


def build() -> str:
    """Build the concatenated output."""
    parts = []

    for module_name in MODULE_ORDER:
        module_path = SRC_DIR / module_name
        if not module_path.exists():
            print(f"ERROR: Missing module: {module_path}", file=sys.stderr)
            sys.exit(1)

        is_header = module_name == "_header.py"
        content = process_module(module_path, is_header=is_header)

        if content:
            # Add section separator for readability
            if not is_header:
                separator = f"\n\n# {'=' * 77}\n# Module: {module_name}\n# {'=' * 77}\n\n"
                parts.append(separator)
            parts.append(content)

    return "".join(parts)


def main():
    check_mode = "--check" in sys.argv

    # Verify src directory exists
    if not SRC_DIR.exists():
        print(f"ERROR: src directory not found: {SRC_DIR}", file=sys.stderr)
        print("Run 'python split.py' first to create module structure.", file=sys.stderr)
        sys.exit(1)

    output = build()

    if check_mode:
        # Verify output matches existing file
        if not OUTPUT_FILE.exists():
            print(f"ERROR: Output file not found: {OUTPUT_FILE}", file=sys.stderr)
            sys.exit(1)

        existing = OUTPUT_FILE.read_text()
        if existing != output:
            print("ERROR: Built output differs from existing file.", file=sys.stderr)
            print("Run 'python build.py' to regenerate.", file=sys.stderr)
            sys.exit(1)

        print("OK: Output matches.")
        sys.exit(0)

    # Write output
    OUTPUT_FILE.write_text(output)

    # Verify syntax
    import py_compile
    try:
        py_compile.compile(str(OUTPUT_FILE), doraise=True)
        print(f"Built: {OUTPUT_FILE} ({len(output)} bytes, syntax OK)")
    except py_compile.PyCompileError as e:
        print(f"ERROR: Syntax error in output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
