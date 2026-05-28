#!/bin/bash
# Install / reinstall the ScreenMind LaunchAgent so the .app starts at login.
#
# Usage: ./macos/install_launch_agent.sh [uninstall]
#
# The agent runs ~/Applications/ScreenMind.app (the menu bar wrapper) at user
# login. macOS LaunchServices still attributes TCC grants to com.bain.screenmind
# because the executable is inside a properly-bundled .app.

set -euo pipefail

LABEL="com.bain.screenmind"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
APP_BIN="$HOME/Applications/ScreenMind.app/Contents/MacOS/ScreenMind"
LOG_DIR="$HOME/Library/Logs/ScreenMind"

if [[ "${1:-}" == "uninstall" ]]; then
    if [[ -f "$PLIST" ]]; then
        launchctl unload "$PLIST" 2>/dev/null || true
        rm -f "$PLIST"
        echo "Uninstalled $PLIST"
    else
        echo "Nothing to uninstall — $PLIST not present."
    fi
    exit 0
fi

if [[ ! -x "$APP_BIN" ]]; then
    echo "ERROR: $APP_BIN not found or not executable." >&2
    echo "Build ScreenMind.app first (see macos/README.md)." >&2
    exit 1
fi

mkdir -p "$LOG_DIR"
mkdir -p "$(dirname "$PLIST")"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$APP_BIN</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/launchd.log</string>
</dict>
</plist>
EOF

# Reload if already loaded.
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed $PLIST"
echo "ScreenMind will start automatically at login."
echo "To start now without rebooting:   launchctl start $LABEL"
echo "To uninstall:                     $0 uninstall"
