# CLAUDE.md

iTerm2 workspace automation using the official Python API.

**Updated**: 2026-01-27

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

**Build concatenation pattern**: Modular `src/*.py` -> Single `default-layout.py`

iTerm2 AutoLaunch requires a single `.py` file. Source is modular for maintainability:

```
src/
├── _header.py       # PEP 723 metadata + imports
├── logging_setup.py # Loguru configuration
├── result.py        # Result[T] monad
├── config.py        # TOML parsing + shell resolution
├── preferences.py   # User preferences persistence
├── discovery.py     # Git worktree + repo discovery
├── dialogs.py       # SwiftDialog + iTerm2 Alert UI
├── panes.py         # Pane creation + command execution
└── main.py          # Entry point + orchestration
```

**Build**: `python build.py` -> Concatenates to `default-layout.py`

**Symlink**: `<clone-path>/default-layout.py` -> `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/`

**Configuration**: `~/.config/iterm2/layout-*.toml` (XDG standard)

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

**Homebrew** (optional):

- broot (file navigator)
- swiftdialog (enhanced dialogs)

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
mise run build          # Build default-layout.py from src/
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

| Priority           | Method                       | Install Command            |
| ------------------ | ---------------------------- | -------------------------- |
| **1. PRIMARY**     | Git clone + setup.sh         | `git clone` + `./setup.sh` |
| **2. Alternative** | Direct `uv run` with PEP 723 | `uv run default-layout.py` |

---

## For Contributors

1. **Fork and clone** the repository
2. **Install dependencies**: `mise install` or `uv sync`
3. **Make changes** to `src/*.py` modules
4. **Build**: `python build.py`
5. **Test**: Restart iTerm2 to test AutoLaunch

---

_Claude Code Agent Memory - iTerm2 Automation_
