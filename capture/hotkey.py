"""
Global Hotkey Module
Listens for configurable keyboard shortcuts for bookmarking, pause/resume,
and voice memos.

Cross-platform backend:
- macOS uses `pynput` (the `keyboard` library has no real macOS support).
- Linux/Windows continue to use `keyboard` (existing behavior, unchanged).
"""

import sys
import time
from typing import Callable, Optional

from config import settings


# ── Helpers ────────────────────────────────────────────────────────────────


def _normalize_hotkey(s: str) -> str:
    """Lowercase + strip whitespace. Both backends operate on this form."""
    return "+".join(p.strip().lower() for p in s.split("+"))


# ── pynput backend (macOS) ──────────────────────────────────────────────────


class _PynputBackend:
    """macOS hotkeys via pynput. Translates 'ctrl+shift+b' → '<ctrl>+<shift>+b'."""

    _MODIFIERS = {"ctrl", "shift", "alt", "cmd", "super", "meta"}

    def __init__(self, owner: "HotkeyListener") -> None:
        self._owner = owner
        self._global_hotkeys = None
        self._voice_listener = None
        self._mods_held: set[str] = set()

    @staticmethod
    def _to_pynput_combo(hotkey: str) -> str:
        parts = []
        for p in _normalize_hotkey(hotkey).split("+"):
            parts.append(f"<{p}>" if p in _PynputBackend._MODIFIERS else p)
        return "+".join(parts)

    def start(self) -> None:
        from pynput import keyboard as pyk  # imported lazily so non-mac installs don't pay

        owner = self._owner

        hotkey_map = {
            self._to_pynput_combo(owner._bookmark_hotkey): owner._on_bookmark,
        }
        if owner._pause_callback:
            hotkey_map[self._to_pynput_combo(owner._pause_hotkey)] = owner._on_pause

        self._global_hotkeys = pyk.GlobalHotKeys(hotkey_map)
        self._global_hotkeys.start()
        print(f"[Hotkey] Registered bookmark hotkey: {owner._bookmark_hotkey}")
        if owner._pause_callback:
            print(f"[Hotkey] Registered pause hotkey: {owner._pause_hotkey}")

        if owner._voice_start_callback and owner._voice_stop_callback:
            self._voice_listener = pyk.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
            )
            self._voice_listener.start()
            print(f"[Hotkey] Registered voice memo hotkey: {owner._voice_hotkey}")

    def _required_mods(self) -> set[str]:
        return set(_normalize_hotkey(self._owner._voice_hotkey).split("+")[:-1])

    def _voice_letter(self) -> str:
        return _normalize_hotkey(self._owner._voice_hotkey).split("+")[-1]

    def _on_press(self, key) -> None:
        from pynput import keyboard as pyk

        if key in (pyk.Key.ctrl, pyk.Key.ctrl_l, pyk.Key.ctrl_r):
            self._mods_held.add("ctrl")
            return
        if key in (pyk.Key.shift, pyk.Key.shift_l, pyk.Key.shift_r):
            self._mods_held.add("shift")
            return
        if key in (pyk.Key.alt, pyk.Key.alt_l, pyk.Key.alt_r):
            self._mods_held.add("alt")
            return
        if key in (pyk.Key.cmd, pyk.Key.cmd_l, pyk.Key.cmd_r):
            self._mods_held.update({"cmd", "super", "meta"})
            return

        ch = getattr(key, "char", None)
        if ch and ch.lower() == self._voice_letter():
            if self._required_mods().issubset(self._mods_held):
                self._owner._handle_voice_down()

    def _on_release(self, key) -> None:
        from pynput import keyboard as pyk

        if key in (pyk.Key.ctrl, pyk.Key.ctrl_l, pyk.Key.ctrl_r):
            self._mods_held.discard("ctrl")
            self._owner._handle_voice_up_if_recording()
            return
        if key in (pyk.Key.shift, pyk.Key.shift_l, pyk.Key.shift_r):
            self._mods_held.discard("shift")
            self._owner._handle_voice_up_if_recording()
            return
        if key in (pyk.Key.alt, pyk.Key.alt_l, pyk.Key.alt_r):
            self._mods_held.discard("alt")
            self._owner._handle_voice_up_if_recording()
            return
        if key in (pyk.Key.cmd, pyk.Key.cmd_l, pyk.Key.cmd_r):
            self._mods_held.difference_update({"cmd", "super", "meta"})
            self._owner._handle_voice_up_if_recording()
            return

        ch = getattr(key, "char", None)
        if ch and ch.lower() == self._voice_letter():
            self._owner._handle_voice_up_if_recording()

    def stop(self) -> None:
        if self._global_hotkeys is not None:
            self._global_hotkeys.stop()
            self._global_hotkeys = None
        if self._voice_listener is not None:
            self._voice_listener.stop()
            self._voice_listener = None


# ── `keyboard` backend (Linux/Windows) ──────────────────────────────────────


class _KeyboardBackend:
    """Original `keyboard`-library backend. Used on Linux and Windows."""

    def __init__(self, owner: "HotkeyListener") -> None:
        self._owner = owner
        self._voice_hooks: list = []

    def start(self) -> None:
        import keyboard

        owner = self._owner
        keyboard.add_hotkey(owner._bookmark_hotkey, owner._on_bookmark, suppress=False)
        print(f"[Hotkey] Registered bookmark hotkey: {owner._bookmark_hotkey}")

        if owner._pause_callback:
            keyboard.add_hotkey(owner._pause_hotkey, owner._on_pause, suppress=False)
            print(f"[Hotkey] Registered pause hotkey: {owner._pause_hotkey}")

        if owner._voice_start_callback and owner._voice_stop_callback:
            last = owner._voice_hotkey.split("+")[-1]
            hook1 = keyboard.on_press_key(last, self._voice_key_down, suppress=False)
            hook2 = keyboard.on_release_key(last, self._voice_key_up, suppress=False)
            self._voice_hooks = [hook1, hook2]
            print(f"[Hotkey] Registered voice memo hotkey: {owner._voice_hotkey}")

    def _voice_key_down(self, _event) -> None:
        import keyboard

        owner = self._owner
        modifiers = owner._voice_hotkey.split("+")[:-1]
        if all(keyboard.is_pressed(m) for m in modifiers):
            owner._handle_voice_down()

    def _voice_key_up(self, _event) -> None:
        self._owner._handle_voice_up_if_recording()

    def stop(self) -> None:
        try:
            import keyboard

            keyboard.remove_hotkey(self._owner._bookmark_hotkey)
            if self._owner._pause_callback:
                keyboard.remove_hotkey(self._owner._pause_hotkey)
            for hook in self._voice_hooks:
                keyboard.unhook(hook)
        except Exception:
            pass
        self._voice_hooks = []


# ── Public listener ─────────────────────────────────────────────────────────


class HotkeyListener:
    """
    Listens for global hotkeys and triggers callbacks:
    - Ctrl+Shift+B: Bookmark current moment (instant capture)
    - Ctrl+Shift+P: Pause/resume capture toggle
    - Ctrl+Shift+V: Voice memo (hold to record, release to stop)
    """

    def __init__(
        self,
        bookmark_callback: Callable[[], None],
        pause_callback: Optional[Callable[[], None]] = None,
        voice_start_callback: Optional[Callable[[], None]] = None,
        voice_stop_callback: Optional[Callable[[], None]] = None,
    ):
        self._bookmark_callback = bookmark_callback
        self._pause_callback = pause_callback
        self._voice_start_callback = voice_start_callback
        self._voice_stop_callback = voice_stop_callback
        self._bookmark_hotkey = _normalize_hotkey(settings.bookmark_hotkey)
        self._pause_hotkey = _normalize_hotkey(settings.pause_hotkey)
        self._voice_hotkey = _normalize_hotkey(settings.voice_hotkey)
        self._running = False
        self._voice_recording = False
        self._voice_cooldown = 0.0  # ignore starts until this time (anti-key-repeat)

        if sys.platform == "darwin":
            self._backend = _PynputBackend(self)
        else:
            self._backend = _KeyboardBackend(self)

    def start(self) -> None:
        if self._running:
            return
        try:
            self._backend.start()
            self._running = True
        except Exception as e:
            print(f"[Hotkey] Failed to register hotkey: {e}")
            if sys.platform == "darwin":
                print(
                    "[Hotkey] On macOS, grant Input Monitoring permission to ScreenMind in "
                    "System Settings → Privacy & Security → Input Monitoring."
                )
            else:
                print("[Hotkey] Try running as administrator for global hotkey support.")

    def stop(self) -> None:
        if not self._running:
            return
        try:
            self._backend.stop()
        except Exception:
            pass
        self._running = False
        print("[Hotkey] Stopped listening.")

    # ── internal callbacks invoked by backends ──

    def _on_bookmark(self) -> None:
        print(f"[Hotkey] Bookmark triggered! ({self._bookmark_hotkey})")
        try:
            self._bookmark_callback()
        except Exception as e:
            print(f"[Hotkey] Error in bookmark callback: {e}")

    def _on_pause(self) -> None:
        if not self._pause_callback:
            return
        print(f"[Hotkey] Pause toggle triggered! ({self._pause_hotkey})")
        try:
            self._pause_callback()
        except Exception as e:
            print(f"[Hotkey] Error in pause callback: {e}")

    def _handle_voice_down(self) -> None:
        if self._voice_recording:
            return
        if time.time() < self._voice_cooldown:
            return
        if not self._voice_start_callback:
            return
        self._voice_recording = True
        print(f"[Hotkey] Voice memo started ({self._voice_hotkey})")
        try:
            self._voice_start_callback()
        except Exception as e:
            print(f"[Hotkey] Error in voice start callback: {e}")
            self._voice_recording = False

    def _handle_voice_up_if_recording(self) -> None:
        if not self._voice_recording:
            return
        if not self._voice_stop_callback:
            self._voice_recording = False
            return
        self._voice_recording = False
        self._voice_cooldown = time.time() + 2.0  # anti key-repeat
        print(f"[Hotkey] Voice memo stopped ({self._voice_hotkey})")
        try:
            self._voice_stop_callback()
        except Exception as e:
            print(f"[Hotkey] Error in voice stop callback: {e}")

    @property
    def is_running(self) -> bool:
        return self._running
