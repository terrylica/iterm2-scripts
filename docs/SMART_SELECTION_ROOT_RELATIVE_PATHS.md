# iTerm2 Smart Selection for File Paths

Configure iTerm2 to open file paths via Cmd+click, including root-relative (`/docs/...`) and bare relative (`skills/foo/bar.md`) paths.

## Problem

1. **Root-relative paths** (e.g., `/docs/decisions/0008-foo.md`) don't exist as absolute filesystem paths
2. **Bare relative paths** (e.g., `skills/semantic-release/references/local-release-workflow.md`) aren't detected by default regex

Both require Smart Selection with a custom action and improved regex pattern.

## Solution

### Step 1: Update Regex Pattern

The improved regex uses a **layered matching strategy**:

| Path Type                       | Rule                   | Examples                              |
| ------------------------------- | ---------------------- | ------------------------------------- |
| Absolute (`/...`)               | Always match           | `/docs/file.md`, `/tmp`               |
| Home (`~/...`)                  | Always match           | `~/.bashrc`, `~/scripts`              |
| Explicit relative (`./`, `../`) | Always match           | `./config.json`, `../parent`          |
| Bare 3+ components              | Always match           | `a/b/c` (high confidence it's a path) |
| Bare 2 components               | Require file extension | `src/main.py` ✓, `foo/bar` ✗          |
| Single file                     | Require file extension | `README.md` ✓, `Makefile` ✗           |

**Regex pattern (extended extensions)**:

```
(/[[:letter:][:number:]._-]+(?:/[[:letter:][:number:]._-]+)*/?)|(\~/?(?:[[:letter:][:number:]._-]+/)*[[:letter:][:number:]._-]*/?)|(\.(?:\.(?:/(?:[[:letter:][:number:]._-]+/)*[[:letter:][:number:]._-]*)?|/(?:[[:letter:][:number:]._-]+/)*[[:letter:][:number:]._-]+)?/?)|([[:letter:][:number:]._-]+/[[:letter:][:number:]._-]+/[[:letter:][:number:]._-]+(?:/[[:letter:][:number:]._-]+)*/?)|([[:letter:][:number:]._-]+/[[:letter:][:number:]._-]+\.(?:md|py|sh|json|yml|yaml|toml|txt|js|ts|jsx|tsx|rs|go|c|cpp|h|hpp|java|rb|html|css|scss|sql|log|conf|cfg|xml|csv|mq5|mq4|ex5|ex4|ipynb|pdf|png|jpg|svg|lock|sum|mod))|([[:letter:][:number:]._-]+\.(?:md|py|sh|json|yml|yaml|toml|txt|js|ts|jsx|tsx|rs|go|c|cpp|h|hpp|java|rb|html|css|scss|sql|log|conf|cfg|xml|csv|mq5|mq4|ex5|ex4|ipynb|pdf|png|jpg|svg|lock|sum|mod))
```

### Step 2: Configure Smart Selection (GUI Only)

**Important**: Plist edits are overwritten by iTerm2 on restart. Must use GUI.

1. **Settings → Profiles → Advanced → Smart Selection → Edit**
2. Select **"Paths"** rule → Click **Edit**
3. Replace the **Regular Expression** with the pattern above
4. Click **"Actions (1)..."** button
5. Verify **"Use interpolated strings for parameters"** checkbox is **checked**
6. Set Command to:

   ```
   ~/.local/bin/iterm-open "\(path)" "\(matches[0])"
   ```

7. Click **Ok** → **Close**

### Critical: Syntax Must Match Checkbox State

| Checkbox State             | Syntax                     | Example                                |
| -------------------------- | -------------------------- | -------------------------------------- |
| **Checked** (interpolated) | `\(path)`, `\(matches[0])` | `iterm-open "\(path)" "\(matches[0])"` |
| **Unchecked** (legacy)     | `\d`, `\0`                 | `iterm-open "\d" "\0"`                 |

**Using wrong syntax = variables pass as literals.**

## What Gets Matched

**Correctly matches**:

- `/docs/file.md` - Absolute path
- `~/scripts/file.md` - Home path
- `./config.json` - Explicit relative
- `skills/semantic-release/references/local-release-workflow.md` - Bare 3+ components
- `src/main.py` - Bare 2 components with extension
- `README.md` - Single file with extension

**Correctly rejects**:

- `yes/no` - No extension, only 2 components
- `and/or` - Common phrase, not a path
- `true/false` - Common phrase, not a path
- `foo/bar` - Ambiguous without extension

## How iterm-open Resolves Paths

The `iterm-open` script handles path resolution:

1. **Absolute paths** (`/Users/...`): Used as-is
2. **Root-relative paths** (`/docs/...`): Tries multiple workspace roots:
   - Current directory (`$pwd`)
   - `~/.claude/` (hardcoded known workspace)
   - Parent directories containing `CLAUDE.md` or `.git`
3. **Home paths** (`~/...`): Expands tilde to `$HOME`
4. **Bare relative paths** (`skills/foo/bar.md`): Prefixed with working directory

## Verification

```bash
# After Cmd+clicking on a path, check log:
tail -5 /tmp/iterm-open.log

# Should show actual resolved paths, NOT:
# pwd_arg='\d' file='\0'  (legacy syntax with interpolated checkbox)
# pwd_arg='d' file='0'    (mangled by shell)
```

## Test Cases

After configuration, Cmd+click should work on these:

```
/docs/decisions/0008-foo.md          # Root-relative
~/scripts/file.md                     # Home path
./config.json                         # Explicit relative
skills/semantic-release/SKILL.md      # Bare 3+ components
src/main.py                           # Bare 2 + extension
README.md                             # Single + extension
```

## Path Enhancements (v1.5.0)

### Trailing Punctuation Handling

When a path appears at the end of a sentence, iTerm2 may include trailing punctuation. The script now handles this with a **try-with-then-without fallback**:

```
Input: "publish-to-pypi.sh."
         ↓
1. Check if "publish-to-pypi.sh." exists → No
2. Strip trailing punctuation → "publish-to-pypi.sh"
3. Check if stripped version exists → Yes
4. Use stripped version
```

**Punctuation stripped**: `. , ; ? !`

**NOT stripped**: `:` (reserved for line notation)

**Safety**: Original path is used if it exists. Stripping only occurs when:

- Original path doesn't exist
- Stripped version exists

This preserves intentional punctuation in filenames like `log.2025.txt`.

### Line/Column Notation

Developer tools often output paths with line numbers (e.g., `file.py:42:5`). The script now parses this notation and opens the file at the specified position:

| Input          | Opens     | Line | Column |
| -------------- | --------- | ---- | ------ |
| `file.py:42`   | `file.py` | 42   | -      |
| `file.py:42:5` | `file.py` | 42   | 5      |
| `file.py:42:`  | `file.py` | 42   | -      |
| `file.py:42.`  | `file.py` | 42   | -      |

**Processing order**:

1. Strip trailing punctuation (`file.py:42.` → `file.py:42`)
2. Parse line notation (`file.py:42` → file=`file.py`, line=42)
3. Resolve path
4. Open in Helix with line:col syntax

### Test Cases (Enhanced)

```
publish-to-pypi.sh.        # Strip trailing period
file.py:42                 # Open at line 42
file.py:42:5               # Open at line 42, column 5
file.py:42.                # Strip period, open at line 42
README.md??                # Strip multiple punctuation
log.2025.txt               # Keep (file exists with periods)
```

## Reference

- **Script**: `bin/iterm-open` (symlink to `~/.local/bin/iterm-open`)
- **Helix opener**: `~/.local/bin/open-in-helix` (accepts line/column args)
- **iTerm2 Docs**: <https://iterm2.com/documentation-smart-selection.html>
