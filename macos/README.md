# ScreenMind on macOS

A drop-in macOS app bundle for ScreenMind that:

- Lives in `~/Applications/ScreenMind.app` (no `sudo` ever, no `/Applications` write needed).
- Shows a **brain glyph in the menu bar** (top-right) — not the Dock.
- Spawns `main.py` as a managed subprocess. Menu provides Open Dashboard / Pause / Bookmark / Quit.
- Auto-starts at login via a user LaunchAgent.
- Has a stable bundle identifier (`com.bain.screenmind`) so TCC grants for Screen Recording, Microphone, Input Monitoring, and Accessibility **persist** across Python updates.

Tested on macOS 26.5 (Tahoe), Apple Silicon, Python 3.12 venv.

---

## Why a custom bundle?

The default `python main.py` invocation breaks on macOS in several ways:

1. **`keyboard` library is non-functional on macOS.** It can't parse modifier+letter hotkeys; even with `sudo` it fails. `pynput` handles macOS natively — see `capture/hotkey.py`.
2. **Homebrew Python is ad-hoc signed.** Every brew update changes its signature, which invalidates TCC permission grants. Re-prompts on every launch.
3. **Bash-script `CFBundleExecutable` doesn't get menu bar UI rights on Tahoe.** macOS's WindowServer silently refuses to draw NSStatusItems from these "wrapped" processes. We use a compiled C launcher (`launcher.c`) instead.
4. **`rumps` (the obvious menu bar library) renders nothing on Tahoe.** API calls succeed; the WindowServer doesn't draw. We call `NSStatusBar` directly via PyObjC in `tray_launcher.py`.

The bundle in this directory solves all four.

---

## Prerequisites

- macOS 13+ (tested on 26.5).
- Xcode Command Line Tools (`xcode-select --install`) — provides `clang` and `codesign`.
- A working Python 3.12 venv at the repo root (`./venv`) with `requirements.txt` installed.
- `llama-server` reachable. Either local (`brew install llama.cpp`) or remote (set `LLAMA_SERVER_HOST` in `.env`).

---

## Build

From the repo root:

```bash
./macos/build_macos.sh           # build .app (icon must exist)
./macos/build_macos.sh --icon    # also (re)generate ScreenMind.icns
./macos/build_macos.sh --launch  # build + start in background
```

The script:

1. Compiles `launcher.c` → Mach-O arm64 binary.
2. Assembles `~/Applications/ScreenMind.app/` with `Contents/Info.plist`, `Contents/MacOS/ScreenMind`, `Contents/Resources/ScreenMind.icns`.
3. Ad-hoc-signs the bundle with identifier `com.bain.screenmind`.
4. Re-registers with LaunchServices.

---

## Auto-start at login

```bash
./macos/install_launch_agent.sh
```

This writes `~/Library/LaunchAgents/com.bain.screenmind.plist` and `launchctl load`s it. The .app will launch at every login. Logs go to `~/Library/Logs/ScreenMind/launchd.log`.

To stop and remove:

```bash
./macos/install_launch_agent.sh uninstall
```

---

## Permissions

The first time the .app captures the screen, records audio, or fires a hotkey, macOS will prompt. Grant each — they attach to `com.bain.screenmind` and persist:

| Prompt | What it covers |
|---|---|
| Screen & System Audio Recording | `mss` screenshot capture |
| Microphone | `sounddevice` voice memo + meeting recording |
| Accessibility | Active window/app detection (`platform_support/macos.py`) |
| Apple Events | Active window title reads |
| Input Monitoring | Global hotkeys via `pynput` |

Check what's granted:

```bash
sqlite3 ~/Library/Application\ Support/com.apple.TCC/TCC.db \
  "SELECT service, auth_value FROM access WHERE client='com.bain.screenmind';"
```

`auth_value=2` means allowed.

---

## Files in this directory

| File | Purpose |
|---|---|
| `build_macos.sh` | One-command build of `~/Applications/ScreenMind.app`. |
| `install_launch_agent.sh` | Install/uninstall the LaunchAgent that auto-starts at login. |
| `generate_icon.py` | Renders `brain.head.profile` SF Symbol on a purple background and assembles `ScreenMind.icns`. |
| `Info.plist` | Bundle metadata + TCC usage descriptions. Copied into the .app at build time. |
| `ScreenMind.icns` | App icon (generated). |
| `ScreenMind.iconset/` | PNG source for `ScreenMind.icns` (generated; gitignored). |

The two source files referenced by the build live at the repo root: `launcher.c` (Mach-O entry point) and `tray_launcher.py` (PyObjC menu bar + subprocess shepherd).

---

## Troubleshooting

**Menu bar icon doesn't show.** Check `~/Library/Logs/ScreenMind/tray.log`. If you see `NSStatusItem created; button frame=...` but no icon visible, you're hitting a Tahoe WindowServer bug — confirm by running `tray_launcher.py` directly from Terminal (the brain should appear). The .app version requires the Mach-O launcher; if Finder shows a Python file icon for `Contents/MacOS/ScreenMind`, rebuild with `./macos/build_macos.sh`.

**TCC re-prompts every launch.** The bundle is ad-hoc-signed, which is normally fine, but the signature must be stable. If you rebuild often, set `--identifier com.bain.screenmind` (the build script already does). To inspect: `codesign -dvv ~/Applications/ScreenMind.app`.

**Port 7777 already in use.** Another ScreenMind is alive. `pkill -f "tray_launcher.py"` then `pkill -f "Python main.py"`.

**LaunchAgent loaded but nothing happens at login.** Check `launchctl list | grep screenmind`. Exit code 0 = running. Logs at `~/Library/Logs/ScreenMind/launchd.log`. Reload with `launchctl unload ... && launchctl load ...`.

**Hotkeys do nothing.** Grant Input Monitoring permission in System Settings → Privacy & Security. The first hotkey press triggers the prompt; if you dismissed it, manually add `ScreenMind` under Privacy & Security → Input Monitoring.

---

## Future work

- **`py2app` packaging** to embed Python and all deps inside the .app, eliminating the venv dependency. Currently the .app's launcher hard-codes `/Users/bain/git/ScreenMind/venv/bin/python`.
- **Notarization** via Apple Developer Program ($99/yr) for Gatekeeper-clean distribution.
- **Sparkle** for in-app auto-updates.
- **`ScreenCaptureKit`** in place of `mss` for native screen capture (better perf on Apple Silicon, future-proofed against deprecation).
