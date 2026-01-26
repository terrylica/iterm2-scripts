#!/bin/bash
# install.sh - One-liner installation for coworkers
# Usage: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/terrylica/iterm2-scripts/main/install.sh)"

set -euo pipefail

echo "=== iTerm2 Layout Manager Installation ==="

# Check/install Homebrew
if ! command -v brew &>/dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

# Install via Brewfile
echo "Installing dependencies and formula..."
brew bundle --file=<(curl -fsSL https://raw.githubusercontent.com/terrylica/iterm2-scripts/main/Brewfile)

echo ""
echo "=== Installation Complete ==="
echo "Enable Python API: iTerm2 → Settings → General → Magic"
echo "Then restart iTerm2."
