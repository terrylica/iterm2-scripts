---
status: implemented
date: 2026-01-17
decision-maker: Terry Li
consulted: [Claude Opus 4.5]
research-method: incident-investigation
---

# iTerm2 PATH Augmentation for AutoLaunch Scripts

## Context and Problem Statement

iTerm2 AutoLaunch scripts run with a minimal macOS PATH that only includes system directories (`/usr/bin:/bin:/usr/sbin:/sbin`). This causes `shutil.which()` to fail for tools installed via Homebrew, cargo, or other package managers.

**Observed symptom**: `br` command (broot alias) fell back to `ls -la` because `shutil.which("broot")` returned `None`.

## Decision

Prepend common tool directories to PATH at module load time, before any command resolution occurs.

```python
_ADDITIONAL_PATHS = [
    "/opt/homebrew/bin",      # Homebrew on Apple Silicon
    "/opt/homebrew/sbin",
    "/usr/local/bin",         # Homebrew on Intel
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/.cargo/bin"),
]

def _augment_path() -> None:
    # Prepend paths that exist and aren't already in PATH
    ...

_augment_path()  # Called at module load
```

## Consequences

**Positive**:
- All Homebrew, cargo, uv, and user-local tools are discoverable
- No changes needed to iTerm2 configuration
- Works for any command resolution in the script

**Negative**:
- Slightly longer PATH than necessary (includes paths that may not exist)
- Must be maintained if new package managers add different locations

## Alternatives Considered

1. **Hardcode full paths**: Rejected - not portable across machines
2. **Launch subshell with user's shell**: Rejected - performance overhead
3. **Use `source ~/.zshrc`**: Rejected - side effects, slow
