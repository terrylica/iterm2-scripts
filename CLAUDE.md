# CLAUDE.md

iTerm2 workspace automation using the official Python API.

**Updated**: 2026-01-26

---

## Navigation

| Topic        | Document                           |
| ------------ | ---------------------------------- |
| Architecture | [docs/CLAUDE.md](./docs/CLAUDE.md) |
| ADRs         | [docs/adr/](./docs/adr/)           |
| Setup        | [README.md](./README.md)           |
| Source       | [src/](./src/)                     |

---

## Quick Start

```bash
# Clone and setup
git clone https://github.com/terrylica/iterm2-scripts
cd iterm2-scripts && bash setup.sh

# Enable Python API in iTerm2
# iTerm2 → Settings → General → Magic → Enable Python API

# Restart iTerm2
```

---

## Architecture

**Build concatenation pattern**: Modular `src/*.py` → Single `default-layout.py`

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

**Build**: `python build.py` → Concatenates to `default-layout.py`

**Symlink**: `<clone-path>/default-layout.py` → `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/`

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

## Development

```bash
# Build from source modules
python build.py

# Run with uv (PEP 723 inline metadata)
uv run default-layout.py

# Validate shell alias introspection
python3 -c "import subprocess; print(subprocess.run(['zsh', '-ic', 'alias -L'], capture_output=True, text=True, timeout=2).stdout[:500])"

# Release (requires .mise.local.toml with GH_TOKEN)
mise release full
```

### Secrets Setup

Create `.mise.local.toml` (gitignored) for releases:

```toml
[env]
GH_TOKEN = "{{ read_file(path=env.HOME ~ '/.claude/.secrets/gh-token-<account>') | trim }}"
GITHUB_TOKEN = "{{ env.GH_TOKEN }}"
```

---

## Distribution Methods

| Priority           | Method                       | Install Command            |
| ------------------ | ---------------------------- | -------------------------- |
| **1. PRIMARY**     | Git clone + setup.sh         | `git clone` + `./setup.sh` |
| **2. Alternative** | Direct `uv run` with PEP 723 | `uv run default-layout.py` |

---

_Claude Code Agent Memory - iTerm2 Automation_
