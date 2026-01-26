# iTerm2 Layout Manager

Workspace automation for iTerm2 using the official Python API. Creates consistent split-pane layouts on iTerm2 startup.

## Installation

### Option 1: Homebrew (Recommended)

```bash
# One-liner
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/terrylica/iterm2-scripts/main/install.sh)"

# Or manual
brew tap terrylica/iterm2-scripts https://github.com/terrylica/iterm2-scripts
brew install iterm2-layout-manager
```

### Option 2: Direct Execution

```bash
# Run directly with uv (no installation needed)
uv run https://raw.githubusercontent.com/terrylica/iterm2-scripts/main/default-layout.py
```

### Option 3: Git Clone

```bash
git clone https://github.com/terrylica/iterm2-scripts
cd iterm2-scripts && bash setup.sh
```

## Setup

1. **Enable Python API in iTerm2**:
   iTerm2 → Settings → General → Magic → Enable Python API

2. **Restart iTerm2**

## Configuration

Configuration files live in `~/.config/iterm2/`:

```toml
# ~/.config/iterm2/layout-default.toml
[layout]
name = "default"
columns = 3
left_ratio = 0.25

[panes.left]
command = "br --sort-by-type-dirs-first"

[panes.center]
command = "hx ."

[panes.right]
command = "bash"
```

## License

MIT
