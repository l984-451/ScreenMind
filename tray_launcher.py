"""
ScreenMind menu bar launcher (direct PyObjC).

Replaces rumps with raw AppKit NSStatusBar calls because rumps 0.4.0 silently
fails to register a visible status item on macOS Tahoe with ad-hoc-signed
bundles launched through the Homebrew Python.app wrapper.

Architecture:
- This process owns the NSApplication main thread.
- It spawns `main.py` as a child subprocess and shepherds its lifecycle.
- An NSTimer polls the dashboard API every 5s to refresh status text.
"""
import logging
import subprocess
import webbrowser
from pathlib import Path

import httpx
import objc
from AppKit import (
    NSApplication,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSObject,
    NSStatusBar,
    NSTimer,
    NSUserNotification,
    NSUserNotificationCenter,
)

NSApplicationActivationPolicyAccessory = 1
NSVariableStatusItemLength = -1.0

APP_DIR = Path(__file__).resolve().parent
PYTHON = APP_DIR / "venv" / "bin" / "python"
DASHBOARD = "http://127.0.0.1:7777"
LOG_DIR = Path.home() / "Library" / "Logs" / "ScreenMind"
LOG_DIR.mkdir(parents=True, exist_ok=True)
SCREENMIND_LOG = LOG_DIR / "screenmind.log"
TRAY_LOG = LOG_DIR / "tray.log"

logging.basicConfig(
    filename=str(TRAY_LOG),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def _notify(title: str, body: str) -> None:
    try:
        n = NSUserNotification.alloc().init()
        n.setTitle_(title)
        n.setInformativeText_(body)
        NSUserNotificationCenter.defaultUserNotificationCenter().deliverNotification_(n)
    except Exception as e:
        logging.warning(f"notification failed: {e}")


def _post(path: str) -> bool:
    try:
        httpx.post(DASHBOARD + path, timeout=3.0)
        return True
    except Exception as e:
        logging.warning(f"POST {path} failed: {e}")
        return False


class ScreenMindController(NSObject):
    """Holds the ObjC-callable selectors that NSMenuItem actions and NSTimer target."""

    def initWithApp_(self, app):
        self = objc.super(ScreenMindController, self).init()
        if self is None:
            return None
        self.app = app
        return self

    def openDashboard_(self, sender):
        webbrowser.open(DASHBOARD)

    def togglePause_(self, sender):
        path = "/api/capture/resume" if self.app.paused else "/api/capture/pause"
        if _post(path):
            self.app.paused = not self.app.paused
            self.app.pause_item.setTitle_(
                "Resume Capture" if self.app.paused else "Pause Capture"
            )
        else:
            _notify("ScreenMind", "Pause/Resume failed — API unreachable")

    def bookmark_(self, sender):
        if _post("/api/capture/bookmark"):
            _notify("ScreenMind", "Bookmark captured")
        else:
            _notify("ScreenMind", "Bookmark failed — API unreachable")

    def quitApp_(self, sender):
        logging.info("Quit requested via menu")
        proc = self.app.proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        NSApplication.sharedApplication().terminate_(self)

    def heartbeat_(self, timer):
        self.app.heartbeat()


class ScreenMindApp:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.paused = False

        nsapp = NSApplication.sharedApplication()
        nsapp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        logging.info("activation policy: accessory")

        self.controller = ScreenMindController.alloc().initWithApp_(self)

        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        button = self.status_item.button()
        # Set both an SF Symbol image AND a fallback title. Image alone is the
        # most reliable rendering on modern macOS; title is a backup if the
        # symbol isn't found.
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "brain.head.profile", "ScreenMind"
        )
        if image is None:
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "circle.circle.fill", "ScreenMind"
            )
        if image is not None:
            image.setTemplate_(True)  # respects menu bar dark/light mode
            button.setImage_(image)
            logging.info("NSStatusItem button image set (SF Symbol)")
        button.setTitle_("SM")
        logging.info(
            f"NSStatusItem created; button frame={button.frame()}"
        )

        menu = NSMenu.alloc().init()

        open_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Dashboard", b"openDashboard:", ""
        )
        open_item.setTarget_(self.controller)
        menu.addItem_(open_item)

        menu.addItem_(NSMenuItem.separatorItem())

        self.pause_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Pause Capture", b"togglePause:", ""
        )
        self.pause_item.setTarget_(self.controller)
        menu.addItem_(self.pause_item)

        bookmark_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Bookmark Now", b"bookmark:", ""
        )
        bookmark_item.setTarget_(self.controller)
        menu.addItem_(bookmark_item)

        menu.addItem_(NSMenuItem.separatorItem())

        self.status_label = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Status: booting…", None, ""
        )
        self.status_label.setEnabled_(False)
        menu.addItem_(self.status_label)

        menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit ScreenMind", b"quitApp:", "q"
        )
        quit_item.setTarget_(self.controller)
        menu.addItem_(quit_item)

        self.status_item.setMenu_(menu)
        logging.info("menu attached to status item")

        self._start_backend()

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            5.0, self.controller, b"heartbeat:", None, True
        )
        logging.info("heartbeat timer scheduled (5s)")

    def _start_backend(self) -> None:
        log_handle = open(SCREENMIND_LOG, "a", buffering=1)
        self.proc = subprocess.Popen(
            [str(PYTHON), "main.py"],
            cwd=str(APP_DIR),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        logging.info(f"spawned main.py as PID {self.proc.pid}")

    def heartbeat(self) -> None:
        button = self.status_item.button()
        if self.proc and self.proc.poll() is not None:
            button.setTitle_("SM!")
            self.status_label.setTitle_(
                f"Status: stopped (exit {self.proc.returncode})"
            )
            return
        try:
            r = httpx.get(DASHBOARD + "/api/status", timeout=1.5)
            if r.status_code == 200:
                button.setTitle_("SM")
                try:
                    data = r.json()
                    self.paused = bool(data.get("paused", self.paused))
                except Exception:
                    pass
                self.pause_item.setTitle_(
                    "Resume Capture" if self.paused else "Pause Capture"
                )
                self.status_label.setTitle_(
                    "Status: paused" if self.paused else "Status: capturing"
                )
            else:
                button.setTitle_("SM…")
                self.status_label.setTitle_(f"Status: HTTP {r.status_code}")
        except Exception:
            button.setTitle_("SM…")
            self.status_label.setTitle_("Status: booting…")

    def run(self) -> None:
        logging.info("entering NSApplication.run()")
        NSApplication.sharedApplication().run()


if __name__ == "__main__":
    logging.info("tray_launcher (pyobjc) starting")
    ScreenMindApp().run()
