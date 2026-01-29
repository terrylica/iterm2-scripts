# Workspace Launcher for iTerm2

Workspace automation for iTerm2 using the official Python API. Creates consistent split-pane layouts on iTerm2 startup with workspace selector, tab customization, and git worktree discovery.

## Quick Start (Claude Code CLI)

If you're using Anthropic's Claude Code CLI, simply clone and let Claude handle the setup:

```bash
git clone https://github.com/terrylica/iterm2-scripts
cd iterm2-scripts

# Claude Code will read CLAUDE.md and can run setup autonomously
claude
```

Claude Code will:

1. Run `bash setup.sh` to install dependencies and create symlinks
2. Guide you through iTerm2 Python API configuration
3. Help customize your workspace configuration

## Manual Installation

### Option 1: Git Clone (Recommended)

```bash
git clone https://github.com/terrylica/iterm2-scripts
cd iterm2-scripts && bash setup.sh
```

### Option 2: Direct Execution

```bash
# Run directly with uv (no installation needed)
uv run https://raw.githubusercontent.com/terrylica/iterm2-scripts/main/workspace-launcher.py
```

### Option 3: Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/terrylica/iterm2-scripts/main/install.sh)"
```

## Prerequisites

- **macOS** (tested on macOS 14+)
- **iTerm2** (version 3.5+)
- **Python 3.11+** (`brew install python@3.11`)
- **uv** package manager (`brew install uv`)

## Setup

1. **Enable Python API in iTerm2**:
   iTerm2 → Settings → General → Magic → Enable Python API

2. **Restart iTerm2** - the workspace launcher will run automatically

## Configuration

Configuration files live in `~/.config/workspace-launcher/`:

```toml
# ~/.config/workspace-launcher/workspace-default.toml

[layout]
left_pane_ratio = 0.25
settle_time = 0.3

[commands]
left = "ls -la"    # Or: br --sort-by-type-dirs-first (requires broot)
right = "zsh"      # Or: claude (requires Claude Code CLI)

[[tabs]]
name = "home"
dir = "~"

[[tabs]]
name = "projects"
dir = "~/projects"
```

## Features

- **Workspace Selector**: Choose from multiple workspace configurations on startup
- **Tab Customization**: Select which tabs to open each session
- **Git Worktree Discovery**: Automatically discovers worktrees from all git repos
- **Migration Support**: Automatically migrates from legacy `~/.config/iterm2/` path
- **SwiftDialog UI**: Enhanced dialogs when SwiftDialog is installed

## Required Homebrew Packages

```bash
brew install swiftdialog  # Workspace selector and tab customization dialogs
brew install broot        # File navigator for left pane
```

These are installed automatically by `setup.sh` if Homebrew is available.

## For Claude Code CLI Users

See [CLAUDE.md](./CLAUDE.md) for detailed instructions on:

- Project architecture and build system
- Development workflow with mise
- Contribution guidelines

## License

MIT
