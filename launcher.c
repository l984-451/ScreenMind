// Mach-O launcher for ScreenMind.app.
// Replaces a bash-script CFBundleExecutable so macOS treats the bundle as a
// proper UI app and grants menu bar access to the Python process it spawns.

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static const char *APP_DIR = "/Users/bain/git/ScreenMind";
static const char *PYTHON = "/Users/bain/git/ScreenMind/venv/bin/python";
static const char *SCRIPT = "/Users/bain/git/ScreenMind/tray_launcher.py";

int main(void) {
    if (chdir(APP_DIR) != 0) {
        perror("chdir");
        return 1;
    }
    execl(PYTHON, "python", SCRIPT, (char *)NULL);
    perror("execl");
    return 1;
}
