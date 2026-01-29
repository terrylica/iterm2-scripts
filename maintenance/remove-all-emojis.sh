#!/bin/bash
# Remove all emojis from iTerm2 tab titles
# Sets clean tab names matching the directory names

echo "🧹 Removing emojis from all iTerm2 tabs..."
echo ""

osascript <<'EOF'
tell application "iTerm"
    if (count of windows) = 0 then
        display dialog "No iTerm2 windows found"
        return
    end if

    set currentWindow to current window
    set tabNames to {"claude", "scripts", "ml-feature-set", "mql5-root", "backtesting", "atr-adaptive-laguerre", "gapless-crypto-data", "gapless-network-data", "exness-data-preprocess", "rangebar", "mql5", "legal-docs", "insurance", "netstrata"}

    repeat with i from 1 to count of tabs of currentWindow
        if i ≤ (count of tabNames) then
            set currentTab to tab i of currentWindow
            tell currentTab
                set current session's name to item i of tabNames
            end tell
        end if
    end repeat

    return "✅ Removed emojis from " & (count of tabs of currentWindow) & " tabs"
end tell
EOF

echo ""
echo "✅ Done! All tab titles updated without emojis."
