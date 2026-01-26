# CLAUDE.md

iTerm2 workspace automation using the official Python API.

**Updated**: 2026-01-17

---

## Navigation

| Topic        | Document                          |
| ------------ | --------------------------------- |
| Architecture | [docs/CLAUDE.md](/docs/CLAUDE.md) |
| ADRs         | [docs/adr/](/docs/adr/)           |
| Setup        | [README.md](/README.md)           |

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

**Reverse symlink pattern**: Git repo → AutoLaunch directory symlink

- Real file: `<clone-path>/default-layout.py`
- Symlink: `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/default-layout.py`

**Configuration**: `~/.config/iterm2/layout-*.toml` (XDG standard, chezmoi-tracked)

---

## Key Technical Decisions

| Decision               | ADR                                                                                 | Summary                               |
| ---------------------- | ----------------------------------------------------------------------------------- | ------------------------------------- |
| PATH augmentation      | [2026-01-17-path-augmentation](/docs/adr/2026-01-17-iterm2-path-augmentation.md)    | Prepend Homebrew paths at module load |
| Shell alias resolution | [2026-01-17-shell-alias-resolution](/docs/adr/2026-01-17-shell-alias-resolution.md) | Query zsh for aliases at runtime      |
| Window ordering        | [2026-01-17-window-ordering](/docs/adr/2026-01-17-iterm2-window-ordering.md)        | Acquire window early for dialogs      |

---

## Dependencies

**Python** (managed by Homebrew formula or uv):

- iterm2, pyobjc, loguru, platformdirs

**Homebrew**:

- broot, swiftdialog (optional)

---

## Development

```bash
# Run with uv (PEP 723 inline metadata)
uv run default-layout.py

# Validate aliases introspection
python3 -c "import subprocess; print(subprocess.run(['zsh', '-ic', 'alias -L'], capture_output=True, text=True, timeout=2).stdout[:500])"
```

---

## Distribution Methods

| Priority           | Method                       | Install Command            |
| ------------------ | ---------------------------- | -------------------------- |
| **1. PRIMARY**     | Homebrew formula + Brewfile  | `brew bundle`              |
| **2. Alternative** | Direct `uv run` with PEP 723 | `uv run https://...`       |
| **3. Fallback**    | Git clone + setup.sh         | `git clone` + `./setup.sh` |

---

_Claude Code Agent Memory - iTerm2 Automation_
