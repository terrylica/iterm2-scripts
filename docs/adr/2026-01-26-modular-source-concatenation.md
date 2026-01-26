# Modular Source with Build Concatenation

## Status

Accepted

## Context

The `default-layout.py` script has grown to ~3,700 lines, making it difficult to navigate, test, and maintain. However, iTerm2 AutoLaunch requires a single `.py` file in `~/Library/Application Support/iTerm2/Scripts/AutoLaunch/`.

We need to balance:

1. **Developer experience**: Small, focused modules for editing
2. **iTerm2 compatibility**: Single file for AutoLaunch symlink
3. **Testability**: Isolated modules can be unit tested

## Decision

Use a **build concatenation** approach:

```
src/
├── _header.py        # PEP 723 metadata, imports, PATH augmentation
├── result.py         # Error/Result types
├── logging_setup.py  # Logger configuration
├── config.py         # Config loading, constants
├── shell.py          # Shell alias introspection
├── preferences.py    # Preferences load/save
├── discovery.py      # Layout/worktree/repo discovery
├── dialogs.py        # SwiftDialog, wizards, selectors
├── panes.py          # Tab/pane creation
└── main.py           # Entry point
```

`build.py` concatenates these into `default-layout.py` with:

- Deduplicated imports (all in `_header.py`)
- Module section separators for navigation
- Syntax validation after build

## Consequences

### Positive

- Edit 100-600 line files instead of 3,700 lines
- Modules can be tested in isolation
- Clear dependency order prevents circular imports
- IDE performance improved (faster linting, autocomplete)
- `--check` mode enables CI validation

### Negative

- Extra build step required after edits
- Must run `python build.py` before testing in iTerm2
- Debugging shows concatenated line numbers (not source module lines)

### Neutral

- Symlink to AutoLaunch unchanged
- PEP 723 metadata preserved in output

## Module Dependency Order

```
_header.py
    ↓
result.py (no deps)
    ↓
logging_setup.py (uses result types)
    ↓
config.py (uses logging)
    ↓
shell.py (uses logging, config)
    ↓
preferences.py (uses logging, config)
    ↓
discovery.py (uses logging, config, preferences)
    ↓
dialogs.py (uses all above + iterm2)
    ↓
panes.py (uses all above + iterm2)
    ↓
main.py (orchestrates everything)
```
