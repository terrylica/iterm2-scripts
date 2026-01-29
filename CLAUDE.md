# CLAUDE.md

iTerm2 workspace automation using the official Python API.

**Updated**: 2026-01-29

---

## Agent Instructions (Claude Code CLI)

When a user clones this repository and runs Claude Code, follow these steps:

### First-Time Setup

1. **Check prerequisites**:

   ```bash
   python3 --version  # Requires 3.11+
   uv --version       # Package manager
   ```

2. **Run setup script** (installs dependencies, creates symlinks):

   ```bash
   bash setup.sh
   ```

3. **Verify iTerm2 Python API** is enabled:
   - iTerm2 → Settings → General → Magic → Enable Python API
   - If not enabled, inform user and wait for confirmation

4. **Restart iTerm2** to activate the workspace launcher

### Verification Commands

```bash
# Check AutoLaunch symlink exists
ls -la ~/Library/Application\ Support/iTerm2/Scripts/AutoLaunch/workspace-launcher.py

# Check config directory exists
ls -la ~/.config/workspace-launcher/

# Verify Python dependencies
python3 -c "import iterm2, loguru, platformdirs; print('OK')"
```

### Common Tasks

| Task              | Command                            |
| ----------------- | ---------------------------------- |
| Build from source | `python build.py`                  |
| Run setup         | `bash setup.sh`                    |
| Check syntax      | `ruff check workspace-launcher.py` |
| Test locally      | Restart iTerm2                     |

---

## Navigation

| Topic             | Document                                         |
| ----------------- | ------------------------------------------------ |
| Architecture      | [docs/CLAUDE.md](./docs/CLAUDE.md)               |
| ADRs              | [docs/adr/](./docs/adr/)                         |
| Helper Scripts    | [bin/CLAUDE.md](./bin/CLAUDE.md)                 |
| TextHelix.app     | [platypus/README.md](./platypus/README.md)       |
| Maintenance Utils | [maintenance/README.md](./maintenance/README.md) |
| Setup             | [README.md](./README.md)                         |
| Source            | [src/](./src/)                                   |

---

## Quick Start

```bash
# Clone and setup
git clone https://github.com/terrylica/iterm2-scripts
cd iterm2-scripts && bash setup.sh

# Enable Python API in iTerm2
# iTerm2 > Settings > General > Magic > Enable Python API

# Restart iTerm2
```

---

## Architecture

**Build concatenation pattern**: Modular `src/*.py` -> Single `workspace-launcher.py`

iTerm2 AutoLaunch requires a single `.py` file. Source is modular for maintainability:

```
src/
├── _header.py           # PEP 723 metadata + imports
├── logging_config.py    # Loguru configuration
├── errors.py            # Error types (Result monad)
├── config_loader.py     # TOML parsing + shell resolution
├── preferences.py       # User preferences + workspace discovery
├── selector.py          # Workspace selector dialog
├── swiftdialog.py       # SwiftDialog utilities
├── layout_toggle.py     # Workspace enable/disable
├── scan_dirs.py         # Scan directories management
├── setup_wizard.py      # First-run and veteran wizards
├── tool_installer.py    # Homebrew tool installation
├── tab_customization.py # Tab selection dialog
├── pane_setup.py        # Pane creation + command execution
└── main.py              # Entry point + orchestration
```

**Build**: `python build.py` -> Concatenates to `workspace-launcher.py`

**Symlink**: `<clone-path>/workspace-launcher.py` -> `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/`

**Configuration**: `~/.config/workspace-launcher/workspace-*.toml`

**Migration**: Existing users with `~/.config/iterm2/layout-*.toml` will be prompted to migrate.

---

## Key Technical Decisions

| Decision               | ADR                                                                                              | Summary                                 |
| ---------------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------- |
| PATH augmentation      | [2026-01-17-path-augmentation](./docs/adr/2026-01-17-iterm2-path-augmentation.md)                | Prepend Homebrew paths at module load   |
| Shell alias resolution | [2026-01-17-shell-alias-resolution](./docs/adr/2026-01-17-shell-alias-resolution.md)             | Query zsh for aliases at runtime        |
| Window ordering        | [2026-01-17-window-ordering](./docs/adr/2026-01-17-iterm2-window-ordering.md)                    | Acquire window early for dialogs        |
| Modular source         | [2026-01-26-modular-source-concatenation](./docs/adr/2026-01-26-modular-source-concatenation.md) | Build-time concatenation for AutoLaunch |

---

## Dependencies

**Python** (managed by uv or Homebrew):

- iterm2, pyobjc, loguru, platformdirs

**Homebrew** (required):

- swiftdialog (workspace selector and tab customization dialogs)
- broot (file navigator for left pane)

---

## Development with mise

This project uses [mise](https://mise.jdx.dev/) for task orchestration. If you have Claude Code with [cc-skills](https://github.com/terrylica/cc-skills), use:

- `Skill(itp:mise-tasks)` - Task patterns and orchestration
- `Skill(itp:mise-configuration)` - Environment configuration

### Setup with mise

```bash
# Install mise (if not installed)
curl https://mise.run | sh

# Install project tools
mise install

# Run tasks
mise run build          # Build workspace-launcher.py from src/
mise run setup          # Run setup script
mise run test-aliases   # Test shell alias introspection
```

### Secrets Setup (for releases)

Create `.mise.local.toml` (gitignored) for releases:

```toml
[env]
GH_TOKEN = "{{ read_file(path=env.HOME ~ '/.claude/.secrets/gh-token-<your-account>') | trim }}"
GITHUB_TOKEN = "{{ env.GH_TOKEN }}"
```

Or set environment variables directly:

```bash
export GH_TOKEN="your-github-token"
mise run release:full
```

---

## Helper Scripts

Shell scripts in `bin/` provide iTerm2 Semantic History integration. See [bin/CLAUDE.md](./bin/CLAUDE.md) for details.

**Installation** (symlink to PATH):

```bash
# From project root
ln -sf "$(pwd)/bin/iterm-open" ~/.local/bin/
ln -sf "$(pwd)/bin/open-in-helix" ~/.local/bin/
```

**iTerm2 Semantic History Configuration**:

Settings > Profiles > Advanced > Semantic History:

```
Run command: ~/.local/bin/iterm-open "\5" "\1" "\3" "\4"
```

---

## TextHelix.app

macOS application for opening text files in Helix editor via iTerm2.

**Setup**: See [platypus/README.md](./platypus/README.md) for build instructions.

**Symlink pattern**:

```
/Applications/TextHelix.app/Contents/Resources/script
  → <clone-path>/bin/texthelix-handler
```

---

## Maintenance Utilities

Optional scripts for iTerm2 customization. See [maintenance/README.md](./maintenance/README.md).

- `clear-all-badges.applescript` - Clear badge text from all sessions
- `disable-profile-badges.sh` - Disable profile badge icons
- `remove-all-emojis.sh` - Remove emoji from tab titles

---

## Distribution Methods

| Priority           | Method                       | Install Command                |
| ------------------ | ---------------------------- | ------------------------------ |
| **1. PRIMARY**     | Git clone + setup.sh         | `git clone` + `./setup.sh`     |
| **2. Alternative** | Direct `uv run` with PEP 723 | `uv run workspace-launcher.py` |

---

## For Contributors

1. **Fork and clone** the repository
2. **Install dependencies**: `mise install` or `uv sync`
3. **Make changes** to `src/*.py` modules
4. **Build**: `python build.py`
5. **Test**: Restart iTerm2 to test AutoLaunch

---

_Claude Code Agent Memory - iTerm2 Automation_
