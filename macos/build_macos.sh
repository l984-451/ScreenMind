#!/bin/bash
# Build ~/Applications/ScreenMind.app from sources in this repo.
#
# Assembles:
#   - Contents/MacOS/ScreenMind   ← compiled launcher.c (Mach-O entry point)
#   - Contents/Info.plist         ← macos/Info.plist
#   - Contents/Resources/         ← ScreenMind.icns
#
# Then ad-hoc-signs the bundle so TCC grants attach to com.bain.screenmind.
#
# Prereqs:
#   - Xcode CLT (for `clang` and `codesign`)
#   - venv set up at ./venv (only needed for generate_icon.py if regenerating)
#
# Usage:
#   ./macos/build_macos.sh             # build (assumes icon exists)
#   ./macos/build_macos.sh --icon      # also regenerate ScreenMind.icns
#   ./macos/build_macos.sh --launch    # build + start via launchctl

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_PATH="$HOME/Applications/ScreenMind.app"
BUNDLE_ID="com.bain.screenmind"

REGEN_ICON=0
DO_LAUNCH=0
for arg in "$@"; do
    case "$arg" in
        --icon) REGEN_ICON=1 ;;
        --launch) DO_LAUNCH=1 ;;
        *) echo "unknown flag: $arg" >&2; exit 1 ;;
    esac
done

cd "$REPO_ROOT"

echo "==> Compile launcher"
clang -O2 -o "$REPO_ROOT/macos/.build_launcher" "$REPO_ROOT/launcher.c"
file "$REPO_ROOT/macos/.build_launcher"

if [[ "$REGEN_ICON" -eq 1 ]]; then
    echo "==> Regenerate ScreenMind.icns"
    if [[ ! -x venv/bin/python ]]; then
        echo "ERROR: venv/bin/python not found. Create the venv first." >&2
        exit 1
    fi
    venv/bin/python macos/generate_icon.py
fi

if [[ ! -f "$REPO_ROOT/macos/ScreenMind.icns" ]]; then
    echo "ERROR: macos/ScreenMind.icns missing. Run with --icon to generate." >&2
    exit 1
fi

echo "==> Assemble $APP_PATH"
mkdir -p "$APP_PATH/Contents/MacOS" "$APP_PATH/Contents/Resources"
cp "$REPO_ROOT/macos/Info.plist" "$APP_PATH/Contents/Info.plist"
cp "$REPO_ROOT/macos/.build_launcher" "$APP_PATH/Contents/MacOS/ScreenMind"
chmod +x "$APP_PATH/Contents/MacOS/ScreenMind"
cp "$REPO_ROOT/macos/ScreenMind.icns" "$APP_PATH/Contents/Resources/ScreenMind.icns"
rm -f "$REPO_ROOT/macos/.build_launcher"

echo "==> Code sign"
codesign --force --deep --sign - --identifier "$BUNDLE_ID" "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"

echo "==> Re-register with LaunchServices"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
    -f "$APP_PATH" >/dev/null

echo
echo "Built $APP_PATH"
echo "  identifier: $BUNDLE_ID"
echo "  signature : $(codesign -dv "$APP_PATH" 2>&1 | grep '^Signature=' || echo '?')"

if [[ "$DO_LAUNCH" -eq 1 ]]; then
    echo "==> Launch"
    # Stop any running instance first
    pkill -f "tray_launcher.py" 2>/dev/null || true
    pkill -f "Python main.py" 2>/dev/null || true
    sleep 1
    "$APP_PATH/Contents/MacOS/ScreenMind" &
    disown
    echo "ScreenMind launched (background)."
fi
