---
status: implemented
date: 2026-01-17
decision-maker: Terry Li
consulted: [Claude Opus 4.5]
research-method: incident-investigation
---

# iTerm2 Window Ordering for Python API Dialogs

## Context and Problem Statement

The iTerm2 Python API's `Alert` dialogs require a window context. If no window exists when the dialog is created, the dialog may:
- Appear behind other windows
- Not receive focus
- Cause race conditions with window creation

## Decision

Acquire or create the main iTerm2 window early in `main()`, before any dialog operations.

```python
async def main(connection: iterm2.Connection) -> None:
    app = await iterm2.async_get_app(connection)

    # Acquire window FIRST, before any dialogs
    window = app.current_terminal_window
    if not window:
        window = await iterm2.Window.async_create(connection)

    # NOW safe to show dialogs
    await show_layout_selector(window)
```

## Consequences

**Positive**:
- Dialogs always appear in front
- Consistent user experience
- No race conditions between window and dialog creation

**Negative**:
- Window created even if user cancels (acceptable tradeoff)
- Slightly more complex flow in main()
