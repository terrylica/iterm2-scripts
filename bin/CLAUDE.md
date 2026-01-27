# bin/ - iTerm2 Helper Scripts

Shell scripts for iTerm2 Semantic History and editor integration.

**Updated**: 2026-01-27

---

## Installation

Scripts are symlinked to `~/.local/bin/` for PATH access:

```bash
# Create symlinks (run from project root)
ln -sf "$(pwd)/bin/iterm-open" ~/.local/bin/
ln -sf "$(pwd)/bin/open-in-helix" ~/.local/bin/
ln -sf "$(pwd)/bin/add-to-dict" ~/.local/bin/
ln -sf "$(pwd)/bin/ghostty-helix" ~/.local/bin/
```

---

## Scripts

| Script                | Purpose                                                        | Symlinked |
| --------------------- | -------------------------------------------------------------- | --------- |
| `iterm-open`          | Semantic History handler - routes Cmd+click to appropriate app | Yes       |
| `open-in-helix`       | Opens file in Helix in new iTerm2 window                       | Yes       |
| `add-to-dict`         | Adds word to harper-ls user dictionary                         | Yes       |
| `ghostty-helix`       | Opens file in Helix via Ghostty terminal                       | Yes       |
| `folder-picker`       | Native macOS folder picker (osascript)                         | No        |
| `texthelix-handler`   | URL handler for `file://` schemes                              | No        |
| `get-tab-directories` | Query working directories of all iTerm2 tabs (debugging)       | No        |

---

## iterm-open

**Main Semantic History handler** - configured in iTerm2 Preferences.

**iTerm2 Configuration**: Settings > Profiles > Advanced > Semantic History

```
Run command: ~/.local/bin/iterm-open "\5" "\1" "\3" "\4"
```

**Parameters**:

- `\5` = Working directory
- `\1` = Clicked file path
- `\3` = Text before click position
- `\4` = Text after click position

**Features**:

- Resolves root-relative paths (`/docs/file.md` → workspace root)
- Expands `~` and `HOME/` prefixes
- Parses line notation (`file.py:42:10`)
- Deep search with `fd` for fuzzy path matching
- Routes by file type (PDF → Skim, images → Preview, etc.)
- Text files → Helix in new iTerm2 window

**Log**: `/tmp/iterm-open.log`

---

## open-in-helix

Opens a file in Helix editor in a **new iTerm2 window**.

```bash
open-in-helix <file> [line] [column]

# Examples
open-in-helix ~/code/main.py
open-in-helix ~/code/main.py 42      # Jump to line 42
open-in-helix ~/code/main.py 42 10   # Jump to line 42, column 10
```

**Log**: `/tmp/markdown-helix-opener.log`

---

## add-to-dict

Adds words to harper-ls (grammar checker) user dictionary.

```bash
add-to-dict <word>

# Example
add-to-dict iTerm2
```

**Dictionary location**: `~/Library/Application Support/harper-ls/dictionary.txt`

---

## folder-picker

Native macOS folder selection dialog via osascript.

```bash
folder=$(folder-picker "Select project folder:")
echo "Selected: $folder"
```

Returns path to stdout, exits 1 if cancelled.

---

## ghostty-helix

Opens file in Helix via Ghostty terminal (alternative to iTerm2).

```bash
ghostty-helix /path/to/file.py
```

---

## texthelix-handler

URL scheme handler for `file://` URLs. Used by TextHelix.app for OSC 8 hyperlink support.

Strips `file://` prefix and delegates to `open-in-helix`.

---

## get-tab-directories

Queries working directories of all iTerm2 tabs using AppleScript and shell integration variables.

```bash
./bin/get-tab-directories

# Output:
# Tab 1: /Users/terryli/eon/project-a
# Tab 2: /Users/terryli/own/scripts
# Tab 3: [unknown]
```

**Use case**: Debugging layout issues, verifying tab setup, capturing workspace state.

**Requires**: iTerm2 shell integration for accurate directory reporting.

---

_bin/ - iTerm2 Helper Scripts_
