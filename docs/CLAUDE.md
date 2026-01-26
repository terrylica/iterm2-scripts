# Documentation Hub

Detailed documentation for iTerm2 Layout Manager.

**Updated**: 2026-01-18

---

## Architecture

### Reverse Symlink Pattern

The layout manager uses a reverse symlink pattern for version control:

```
Git repo (real files):
  <clone-path>/default-layout.py
  <clone-path>/claude-orphan-cleanup.py

Symlinks (iTerm2 reads):
  ~/Library/Application Support/iTerm2/Scripts/AutoLaunch/default-layout.py
    → <clone-path>/default-layout.py
```

**Benefits**:

- SSoT (git-tracked)
- Changes take effect on iTerm2 restart
- Easy cross-machine sync via git clone

### Multi-Layer Selection System

**Layer 1**: Layout Selection

- Scans `~/.config/iterm2/layout-*.toml` for available layouts
- Shows macOS native dialog via `iterm2.Alert` API
- Remembers choice via `remember_choice` preference

**Layer 2**: Tab Customization

- SwiftDialog checkbox interface (modern UI)
- Falls back to `iterm2.PolyModalAlert` if SwiftDialog not installed
- Three categories: Layout tabs, Worktrees, Additional repos

---

## ADRs

| Decision               | Document                                                                             | Status      |
| ---------------------- | ------------------------------------------------------------------------------------ | ----------- |
| PATH Augmentation      | [2026-01-17-iterm2-path-augmentation.md](adr/2026-01-17-iterm2-path-augmentation.md) | Implemented |
| Shell Alias Resolution | [2026-01-17-shell-alias-resolution.md](adr/2026-01-17-shell-alias-resolution.md)     | Implemented |
| Window Ordering        | [2026-01-17-iterm2-window-ordering.md](adr/2026-01-17-iterm2-window-ordering.md)     | Implemented |

---

## Configuration

### Layout Files

Location: `~/.config/iterm2/layout-*.toml`

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

Location: `~/.config/iterm2/selector-preferences.toml`

| Key                      | Type   | Description                       |
| ------------------------ | ------ | --------------------------------- |
| `remember_choice`        | bool   | Skip layout selector on startup   |
| `last_layout`            | string | Name of remembered layout         |
| `skip_tab_customization` | bool   | Skip Layer 2 dialog               |
| `scan_directories`       | array  | Directories to scan for git repos |

---

## Troubleshooting

### Common Issues

See [SMART_SELECTION_ROOT_RELATIVE_PATHS.md](SMART_SELECTION_ROOT_RELATIVE_PATHS.md) for Cmd+click path handling.

### Logs

- Console: stderr (visible in iTerm2 Script Console)
- File: `~/Library/Logs/iterm2-layout/layout.jsonl`

---

_Documentation Hub - iTerm2 Layout Manager_
