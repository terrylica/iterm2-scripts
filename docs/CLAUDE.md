# Documentation Hub

Detailed documentation for iTerm2 Workspace Launcher.

**Updated**: 2026-01-30

---

## Architecture

### Reverse Symlink Pattern

The workspace launcher uses a reverse symlink pattern for version control:

```
Git repo (real files):
  <clone-path>/workspace-launcher.py

Symlinks (iTerm2 reads):
  ~/Library/Application Support/iTerm2/Scripts/AutoLaunch/workspace-launcher.py
    → <clone-path>/workspace-launcher.py
```

**Benefits**:

- SSoT (git-tracked)
- Changes take effect on iTerm2 restart
- Easy cross-machine sync via git clone

### Multi-Layer Selection System

**Layer 1**: Workspace Selection

- Scans `~/.config/workspace-launcher/workspace-*.toml` for available workspaces
- Shows SwiftDialog selector (or falls back to `iterm2.Alert`)
- Auto-opens last workspace with countdown dialog
- Remembers choice via `last_layout` preference

**Layer 2**: Tab Customization

- SwiftDialog checkbox interface (modern UI)
- Falls back to `iterm2.PolyModalAlert` if SwiftDialog not installed
- Four categories: Workspace tabs, Worktrees, Additional repos, Untracked folders

**Layer 3**: Tab Reorder

- SwiftDialog dropdown interface for reordering tabs
- 10x spacing (defaults at 10, 20, 30...) for easy insertion
- Persists order via `last_tab_order` preference
- Reorders both existing and newly created tabs via `window.async_set_tabs()`

---

## ADRs

| Decision               | Document                                                                                     | Status      |
| ---------------------- | -------------------------------------------------------------------------------------------- | ----------- |
| PATH Augmentation      | [2026-01-17-iterm2-path-augmentation.md](adr/2026-01-17-iterm2-path-augmentation.md)         | Implemented |
| Shell Alias Resolution | [2026-01-17-shell-alias-resolution.md](adr/2026-01-17-shell-alias-resolution.md)             | Implemented |
| Window Ordering        | [2026-01-17-iterm2-window-ordering.md](adr/2026-01-17-iterm2-window-ordering.md)             | Implemented |
| Modular Source         | [2026-01-26-modular-source-concatenation.md](adr/2026-01-26-modular-source-concatenation.md) | Implemented |

---

## Configuration

### Workspace Files

Location: `~/.config/workspace-launcher/workspace-*.toml`

```toml
[layout]
left_pane_ratio = 0.20
settle_time = 0.3

[commands]
left = "br --sort-by-type-dirs-first"
right = "zsh"

[[tabs]]
name = "home"
dir = "~"
```

### Preferences

Location: `~/.config/workspace-launcher/preferences.toml`

| Key                      | Type   | Description                           |
| ------------------------ | ------ | ------------------------------------- |
| `remember_choice`        | bool   | Skip workspace selector on startup    |
| `last_layout`            | string | Name of last selected workspace       |
| `skip_tab_customization` | bool   | Skip Layer 2 dialog                   |
| `last_tab_selections`    | array  | Tab names from last session           |
| `last_tab_order`         | array  | Directory paths in reordered order    |
| `custom_tab_names`       | table  | Path → shorthand name mappings        |
| `disabled_layouts`       | array  | Workspace names to hide from selector |
| `scan_directories`       | array  | Directories to scan for git repos     |

---

## Troubleshooting

### Common Issues

See [SMART_SELECTION_ROOT_RELATIVE_PATHS.md](SMART_SELECTION_ROOT_RELATIVE_PATHS.md) for Cmd+click path handling.

### Logs

- Console: stderr (visible in iTerm2 Script Console)
- File: `~/Library/Logs/workspace-launcher/launcher.jsonl`

---

_Documentation Hub - iTerm2 Workspace Launcher_
