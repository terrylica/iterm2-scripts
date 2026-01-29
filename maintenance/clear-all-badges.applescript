#!/usr/bin/osascript
-- Clear all badge text from iTerm2 sessions

tell application "iTerm"
	if (count of windows) = 0 then
		return "No windows open"
	end if

	set currentWindow to current window
	set output to ""

	repeat with currentTab in tabs of currentWindow
		repeat with currentSession in sessions of currentTab
			tell currentSession
				-- Check current badge
				try
					set currentBadge to (get variable named "user.badge")
					set output to output & "Found badge: " & currentBadge & return
				on error
					set output to output & "No badge variable" & return
				end try

				-- Clear the badge
				set variable named "user.badge" to ""
			end tell
		end repeat
	end repeat

	return output & return & "✅ All badges cleared"
end tell
