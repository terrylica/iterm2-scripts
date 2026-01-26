---
status: accepted
date: 2026-01-17
decision-maker: Terry Li
consulted: [Claude Opus 4.5]
research-method: multi-agent
---

# Shell Alias Resolution via Runtime Query

## Context and Problem Statement

Users configure shell aliases (e.g., `br` -> `broot`, `hx` -> `helix`) in their `.zshrc`. Python's `shutil.which()` cannot resolve these aliases - it only checks PATH for actual executables.

**Previous approach**: Hardcoded `KNOWN_ALIASES` dict requiring manual maintenance.

## Decision

Query the user's shell for aliases at runtime using `zsh -ic "alias -L"`.

```python
def get_shell_aliases() -> dict[str, str]:
    result = subprocess.run(
        ["zsh", "-ic", "alias -L"],
        capture_output=True, text=True, timeout=2,
        env={**os.environ, "TERM": "dumb"}
    )
    return _parse_alias_output(result.stdout)
```

**Key design choices**:
- 2-second timeout prevents hanging on slow shell initialization
- `TERM=dumb` suppresses escape codes in output
- Results cached for session (single query per iTerm2 launch)
- Fallback to empty dict on failure (graceful degradation)

## Consequences

**Positive**:
- Zero maintenance - auto-discovers user's aliases
- Works for any shell alias user configures
- Portable across machines with different alias setups

**Negative**:
- ~100ms overhead on first resolution (cached thereafter)
- Depends on zsh being available (fallback to no aliases)
- Interactive shell startup may have side effects

## Alternatives Considered

1. **Maintain KNOWN_ALIASES dict**: Rejected - doesn't scale, manual maintenance
2. **Read `.zshrc` directly**: Rejected - complex parsing, may miss sourced files
3. **Use `type` command**: Rejected - less reliable output format
