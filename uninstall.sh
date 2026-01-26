#!/bin/bash
# uninstall.sh - Complete removal of iTerm2 Layout Manager

set -euo pipefail

AUTOLAUNCH_SYMLINK="$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch/default-layout.py"

echo "=== iTerm2 Layout Manager Uninstall ==="

# Remove AutoLaunch symlink
if [ -L "$AUTOLAUNCH_SYMLINK" ]; then
    rm -f "$AUTOLAUNCH_SYMLINK"
    echo "Removed: $AUTOLAUNCH_SYMLINK"
elif [ -f "$AUTOLAUNCH_SYMLINK" ]; then
    echo "Warning: $AUTOLAUNCH_SYMLINK is a regular file, not removing"
fi

# Uninstall Homebrew formula
if brew list iterm2-layout-manager &>/dev/null; then
    brew uninstall iterm2-layout-manager
    echo "Uninstalled: iterm2-layout-manager formula"
fi

# Optionally remove config
read -p "Remove config files (~/.config/iterm2/)? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf "$HOME/.config/iterm2"
    echo "Removed: ~/.config/iterm2/"
fi

echo "=== Uninstall Complete ==="
