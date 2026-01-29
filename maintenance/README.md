# Maintenance Scripts

Optional utilities for iTerm2 customization and troubleshooting.

These scripts are **not installed by default** - they're personal-use utilities for specific maintenance tasks.

## Scripts

| Script                         | Purpose                                   |
| ------------------------------ | ----------------------------------------- |
| `clear-all-badges.applescript` | Clear badge text from all iTerm2 sessions |
| `disable-profile-badges.sh`    | Disable profile badge icons globally      |
| `remove-all-emojis.sh`         | Remove emoji prefixes from tab titles     |

## Usage

### Clear All Badges

Removes badge text (user.badge variable) from all sessions:

```bash
osascript <clone-path>/maintenance/clear-all-badges.applescript
```

### Disable Profile Badges

Disables the profile badge icons (circled letters) in tabs:

```bash
<clone-path>/maintenance/disable-profile-badges.sh
```

**Note**: For permanent fix, go to iTerm2 Settings > Profiles > General > Icon > select "No Icon".

### Remove All Emojis

Strips emoji prefixes from tab titles:

```bash
<clone-path>/maintenance/remove-all-emojis.sh
```

**Note**: This script has hardcoded tab names - customize `tabNames` array for your workflow.

## When to Use

- **Badges appearing unexpectedly**: Run `clear-all-badges.applescript`
- **Profile icons (B, C circles) in tabs**: Run `disable-profile-badges.sh` and update Settings
- **Want plain text tab names**: Run `remove-all-emojis.sh` (customize first)

## Not Installed by Default

These are **not** symlinked to `~/.local/bin/` by `setup.sh` because:

1. They're rarely needed (one-time fixes)
2. Some have hardcoded values (need customization)
3. They're troubleshooting tools, not daily-use scripts
