#!/bin/bash
# =============================================================================
# iTerm2 Layout Manager Setup Script
# =============================================================================
#
# This script sets up the iTerm2 Layout Manager for a new user.
# Run: bash ~/scripts/iterm2/setup.sh
#
# What it does:
# 1. Validates Python 3.11+ is installed
# 2. Checks uv package manager is installed
# 3. Installs required Python packages
# 4. Creates config directory (~/.config/iterm2/)
# 5. Creates AutoLaunch symlink
# 6. Copies example config if none exists
#
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/iterm2"
AUTOLAUNCH_DIR="$HOME/Library/Application Support/iTerm2/Scripts/AutoLaunch"
SCRIPT_NAME="default-layout.py"

# Print with color
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "=== iTerm2 Layout Manager Setup ==="
echo ""

# -----------------------------------------------------------------------------
# Step 1: Check Python version
# -----------------------------------------------------------------------------
info "Checking Python version..."

if ! command -v python3 &> /dev/null; then
    error "Python 3 not found"
    echo "  Install: brew install python@3.11"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    error "Python 3.11+ required (current: $PYTHON_VERSION)"
    echo "  Install: brew install python@3.11"
    exit 1
fi

success "Python $PYTHON_VERSION"

# -----------------------------------------------------------------------------
# Step 2: Check uv package manager
# -----------------------------------------------------------------------------
info "Checking uv package manager..."

if ! command -v uv &> /dev/null; then
    error "uv not found (required package manager)"
    echo "  Install: brew install uv"
    echo "  Or: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

UV_VERSION=$(uv --version 2>/dev/null | head -1)
success "$UV_VERSION"

# -----------------------------------------------------------------------------
# Step 3: Install Python dependencies
# -----------------------------------------------------------------------------
info "Checking Python dependencies..."

MISSING_DEPS=()

python3 -c "import iterm2" 2>/dev/null || MISSING_DEPS+=("iterm2")
python3 -c "import AppKit" 2>/dev/null || MISSING_DEPS+=("pyobjc")
python3 -c "import platformdirs" 2>/dev/null || MISSING_DEPS+=("platformdirs")
python3 -c "import loguru" 2>/dev/null || MISSING_DEPS+=("loguru")

if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    warn "Missing packages: ${MISSING_DEPS[*]}"
    info "Installing with uv..."
    uv pip install "${MISSING_DEPS[@]}"
    success "Dependencies installed"
else
    success "All dependencies present"
fi

# -----------------------------------------------------------------------------
# Step 4: Create config directory
# -----------------------------------------------------------------------------
info "Checking config directory..."

if [ ! -d "$CONFIG_DIR" ]; then
    mkdir -p "$CONFIG_DIR"
    success "Created $CONFIG_DIR"
else
    success "Config directory exists"
fi

# -----------------------------------------------------------------------------
# Step 5: Create AutoLaunch symlink
# -----------------------------------------------------------------------------
info "Checking AutoLaunch symlink..."

if [ ! -d "$AUTOLAUNCH_DIR" ]; then
    mkdir -p "$AUTOLAUNCH_DIR"
    info "Created AutoLaunch directory"
fi

SYMLINK_PATH="$AUTOLAUNCH_DIR/$SCRIPT_NAME"
SOURCE_PATH="$SCRIPT_DIR/$SCRIPT_NAME"

if [ -L "$SYMLINK_PATH" ]; then
    # Symlink exists - check if it points to the right place
    CURRENT_TARGET=$(readlink "$SYMLINK_PATH")
    if [ "$CURRENT_TARGET" = "$SOURCE_PATH" ]; then
        success "AutoLaunch symlink already configured"
    else
        warn "Symlink exists but points to: $CURRENT_TARGET"
        warn "Expected: $SOURCE_PATH"
        read -p "Update symlink? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm "$SYMLINK_PATH"
            ln -s "$SOURCE_PATH" "$SYMLINK_PATH"
            success "Updated symlink"
        fi
    fi
elif [ -f "$SYMLINK_PATH" ]; then
    warn "AutoLaunch path exists but is a regular file (not symlink)"
    warn "Location: $SYMLINK_PATH"
    echo "  Remove it manually if you want to use the symlink pattern"
else
    ln -s "$SOURCE_PATH" "$SYMLINK_PATH"
    success "Created AutoLaunch symlink"
fi

# -----------------------------------------------------------------------------
# Step 6: Copy example config if none exists
# -----------------------------------------------------------------------------
info "Checking layout configuration..."

if find "$CONFIG_DIR" -maxdepth 1 -name 'layout-*.toml' -print -quit 2>/dev/null | grep -q .; then
    LAYOUT_COUNT=$(find "$CONFIG_DIR" -maxdepth 1 -name 'layout-*.toml' 2>/dev/null | wc -l | tr -d ' ')
    success "Found $LAYOUT_COUNT layout file(s)"
else
    EXAMPLE_CONFIG="$SCRIPT_DIR/layout.example.toml"
    if [ -f "$EXAMPLE_CONFIG" ]; then
        cp "$EXAMPLE_CONFIG" "$CONFIG_DIR/layout-default.toml"
        success "Created default layout config"
        info "Edit: $CONFIG_DIR/layout-default.toml"
    else
        warn "No example config found at $EXAMPLE_CONFIG"
        warn "You'll need to create a layout-*.toml file manually"
    fi
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=== Setup Complete ==="
echo ""
success "iTerm2 Layout Manager is ready!"
echo ""
echo "Next steps:"
echo "  1. Enable Python API in iTerm2:"
echo "     Settings → General → Magic → Enable Python API"
echo ""
echo "  2. Edit your layout config:"
echo "     $CONFIG_DIR/layout-default.toml"
echo ""
echo "  3. Restart iTerm2"
echo ""
echo "Optional enhancements:"
echo "  - brew install swiftdialog  (better UI for tab selection)"
echo "  - brew install broot        (file navigator in left pane)"
echo ""
