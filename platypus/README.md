# TextHelix.app - Platypus Configuration

macOS application that opens text files in Helix editor via iTerm2.

## Purpose

TextHelix.app is a Platypus-generated macOS application bundle that:

- Registers as handler for text file types (`.md`, `.py`, `.toml`, etc.)
- Opens files in Helix editor via new iTerm2 window
- Supports `file://` URL scheme for OSC 8 hyperlinks

## Architecture

**Delegation chain**:

1. macOS opens file with TextHelix.app
2. App bundle executes `texthelix-handler` script
3. Script strips `file://` URL scheme if present
4. Delegates to `open-in-helix` for iTerm2 + Helix integration

**Symlink pattern** (reverse symlink):

```
/Applications/TextHelix.app/Contents/Resources/script
  → ~/eon/iterm2-scripts/bin/texthelix-handler
```

## Files

| File                   | Purpose                                                  |
| ---------------------- | -------------------------------------------------------- |
| `TextHelix.platypus`   | Platypus project export (for reference)                  |
| `TextHelix-Info.plist` | App Info.plist with comprehensive file type associations |

**Note**: The plist contains `CFBundleIdentifier` (`com.terryli.TextHelix`) - customize this for your own builds.

## Supported File Types

See `TextHelix-Info.plist` for complete list. Includes:

- Markdown: `.md`, `.markdown`, `.rst`, `.org`
- Code: `.py`, `.rs`, `.go`, `.js`, `.ts`, `.tsx`, `.rb`, `.java`, `.c`, `.cpp`, `.swift`
- Config: `.toml`, `.yaml`, `.yml`, `.json`, `.xml`, `.ini`, `.cfg`, `.env`
- Shell: `.sh`, `.bash`, `.zsh`, `.fish`
- And many more (90+ extensions)

## Building TextHelix.app

### Prerequisites

```bash
brew install --cask platypus
```

### Build Steps

1. Open Platypus.app
2. Configure settings:
   - **App Name**: TextHelix
   - **Script Type**: Shell (/bin/sh)
   - **Script Path**: `<clone-path>/bin/texthelix-handler`
   - **Interface**: None (run in background)
   - **Identifier**: `com.yourname.TextHelix` (customize)
3. Add document types from `TextHelix-Info.plist`:
   - Click "Document Types" in Platypus
   - Add UTIs: `public.plain-text`, `public.text`, `public.source-code`
4. Build to `/Applications/TextHelix.app`

### Post-Build Setup

Create symlink so app uses git-tracked script:

```bash
# Remove embedded script
rm /Applications/TextHelix.app/Contents/Resources/script

# Create symlink to repo
ln -s <clone-path>/bin/texthelix-handler \
      /Applications/TextHelix.app/Contents/Resources/script

# Re-sign app (required after modifying bundle)
codesign --force --deep --sign - /Applications/TextHelix.app
```

## Troubleshooting

### App shows error -50 or won't launch

```bash
codesign --force --deep --sign - /Applications/TextHelix.app
```

### Symlink not working

```bash
# Verify symlink
ls -la /Applications/TextHelix.app/Contents/Resources/script

# Should show:
# script -> <clone-path>/bin/texthelix-handler

# Recreate if needed:
ln -sf <clone-path>/bin/texthelix-handler \
       /Applications/TextHelix.app/Contents/Resources/script
```

### Set as default app for file type

```bash
# Use duti (brew install duti)
duti -s com.yourname.TextHelix .md all
```
