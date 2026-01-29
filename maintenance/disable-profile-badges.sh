#!/bin/bash
# Disable iTerm2 profile badges (the "B" circles you see)

echo "🔧 Disabling iTerm2 profile badges..."
echo ""

osascript <<'EOF'
tell application "iTerm"
    if (count of windows) = 0 then
        display dialog "No iTerm2 windows found"
        return
    end if

    set currentWindow to current window

    repeat with currentTab in tabs of currentWindow
        repeat with currentSession in sessions of currentTab
            tell currentSession
                -- Set badge to empty string to remove it
                set variable named "user.show_badge" to "0"
            end tell
        end repeat
    end repeat

    return "✅ Disabled profile badges"
end tell
EOF

# Also update iTerm2 preferences to disable badges globally
defaults write com.googlecode.iterm2 ShowBadge -bool false

echo ""
echo "✅ Profile badges disabled!"
echo "💡 If still visible, go to iTerm2 → Settings → Profiles → General → Badge"
echo "   and clear the badge text field for each profile."
