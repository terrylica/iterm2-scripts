#!/usr/bin/env python3
"""
Split default-layout.py into modular source files.

ADR: docs/adr/2026-01-26-modular-source-concatenation.md

One-time script to extract sections from the monolithic file into src/ modules.
After running, use build.py to concatenate back.

Usage:
    python split.py           # Split into src/
    python split.py --dry-run # Show what would be created
"""

import sys
from pathlib import Path

SOURCE_FILE = Path(__file__).parent / "default-layout.py"
SRC_DIR = Path(__file__).parent / "src"

# Section markers in original file -> target module
# Order matters - first match wins
SECTION_MAPPING = [
    # Header: everything before first section marker
    (None, "_header.py", 0, 145),  # Lines 1-145 (imports + PATH augmentation)

    # Explicit sections by line ranges (from grep output)
    ("Structured Logging", "logging_setup.py", 147, 218),
    ("Error Handling Types", "result.py", 220, 310),
    ("Configuration Loading", "config.py", 312, 352),
    ("Shell Alias Introspection", "shell.py", 354, 683),
    ("Layout Selector Functions", "preferences.py", 684, 1056),
    ("First-Run Detection", "discovery.py", 1057, 1531),  # includes wizards
    ("Git Worktree Detection", "discovery.py", 1532, 1666),  # worktrees
    ("Universal Worktree Detection", "discovery.py", 1667, 1980),
    ("Layer 2: Tab Customization", "dialogs.py", 1981, 2002),
    ("SwiftDialog Integration", "dialogs.py", 2003, 2683),
    ("Directory Management", "dialogs.py", 2684, 3010),
    ("Pane Setup", "panes.py", 3011, 3229),
    # main() function to end
]

NOQA_HEADER = """\
# ruff: noqa: F821
# ADR: docs/adr/2026-01-26-modular-source-concatenation.md
# This module is concatenated with _header.py - imports come from there
"""


def extract_section(content: str, start_line: int, end_line: int) -> str:
    """Extract lines from content (1-indexed, inclusive)."""
    lines = content.split("\n")
    # Convert to 0-indexed
    section = lines[start_line - 1:end_line]
    return "\n".join(section)


def main():
    dry_run = "--dry-run" in sys.argv

    if not SOURCE_FILE.exists():
        print(f"ERROR: Source file not found: {SOURCE_FILE}", file=sys.stderr)
        sys.exit(1)

    content = SOURCE_FILE.read_text()
    lines = content.split("\n")
    total_lines = len(lines)

    print(f"Source: {SOURCE_FILE} ({total_lines} lines)")

    if not dry_run:
        SRC_DIR.mkdir(exist_ok=True)

    # Track which modules get content
    modules = {}

    # Special case: _header.py (lines 1-145)
    header_content = extract_section(content, 1, 145)
    modules["_header.py"] = header_content

    # Special case: main.py (async main to end)
    # Find "async def main(connection):" line
    main_start = None
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("async def main(connection)"):
            main_start = i
            break

    if main_start:
        # Include some context before main (the section header)
        main_content = extract_section(content, main_start - 5, total_lines)
        modules["main.py"] = NOQA_HEADER + "\n" + main_content

    # Extract other sections based on line ranges
    section_ranges = {
        "logging_setup.py": (147, 218),
        "result.py": (220, 310),
        "config.py": (312, 683),  # Includes config loading + shell alias
        "preferences.py": (684, 1056),
        "discovery.py": (1057, 1980),  # First-run + worktree discovery
        "dialogs.py": (1981, 3010),  # All dialog functions
        "panes.py": (3011, main_start - 6 if main_start else 3229),  # Up to main
    }

    for module_name, (start, end) in section_ranges.items():
        section_content = extract_section(content, start, end)
        if module_name != "_header.py":
            section_content = NOQA_HEADER + "\n" + section_content
        modules[module_name] = section_content

    # Write or preview modules
    for module_name, module_content in modules.items():
        module_path = SRC_DIR / module_name
        line_count = len(module_content.split("\n"))

        if dry_run:
            print(f"  Would create: {module_path} ({line_count} lines)")
        else:
            module_path.write_text(module_content)
            print(f"  Created: {module_path} ({line_count} lines)")

    if not dry_run:
        print("\nDone! Run 'python build.py' to concatenate back.")


if __name__ == "__main__":
    main()
