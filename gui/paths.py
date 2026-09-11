"""Platform-aware filesystem locations and version resolution.

earcongen writes audio somewhere the user will look for it and remembers
its own settings somewhere the user will never have to. Both of those
locations differ per platform, and neither is guessable from `Path.home()`
alone.

Everything here is read at start-up and again whenever the user changes
the output directory, so it stays cheap.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "earcongen"

#: Directory name created under the chosen output base for each run.
#: Keeping generated audio in a named subfolder means pointing the tool at
#: Documents does not scatter thirty WAVs across it.
DEFAULT_OUTPUT_DIRNAME = "earcons"

#: Dropped beside a frozen binary to keep settings and output next to the
#: executable rather than in the user profile — the usual arrangement for
#: a tool carried on a USB stick between machines.
PORTABLE_MARKER = "earcongen-portable.txt"


def is_frozen() -> bool:
    """Whether we are running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def resource_root() -> Path:
    """Where bundled data files live.

    Frozen, that is PyInstaller's extraction directory. From a checkout,
    it is the repository root — this file's parent's parent.
    """
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def binary_dir() -> Path:
    """The directory holding the running executable or entry script."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def is_portable() -> bool:
    """Whether a portable marker sits beside the binary."""
    try:
        return (binary_dir() / PORTABLE_MARKER).is_file()
    except OSError:
        return False


def read_version() -> str:
    """The contents of the `version` file, or a placeholder.

    Versions are bare YYYYMMDD datestamps. The file is bundled into the
    binary by packaging/build_common.py so a frozen build can report the
    same string the release was tagged with; the release workflow's smoke
    test compares the two.
    """
    for candidate in (resource_root() / "version", binary_dir() / "version"):
        try:
            text = candidate.read_text().strip()
        except OSError:
            continue
        if text:
            return text
    return "0"


def _windows_documents() -> Path:
    # USERPROFILE is set on every supported Windows version; the fallback
    # is for the stripped environments CI sometimes provides.
    profile = os.environ.get("USERPROFILE")
    base = Path(profile) if profile else Path.home()
    return base / "Documents"


def _windows_appdata() -> Path:
    appdata = os.environ.get("APPDATA")
    return Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"


def config_dir() -> Path:
    """Where the GUI remembers its settings.

    Linux honours XDG_CONFIG_HOME, because a user who has set it has said
    where they want this. Windows uses Roaming AppData and macOS uses
    Application Support, which is where each platform's users look.
    """
    if is_portable():
        return binary_dir() / "config"
    if sys.platform == "win32":
        return _windows_appdata() / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME


def settings_file() -> Path:
    """The JSON file holding the last-used settings."""
    return config_dir() / "settings.json"


def default_output_base() -> Path:
    """The output directory offered on a first run.

    Documents on Windows and macOS. On Linux, XDG_DOCUMENTS_DIR if the
    user has one and it exists, otherwise ~/Music, which is where a
    freedesktop system will already have a folder — falling back to the
    home directory only if neither is there.
    """
    if is_portable():
        return binary_dir() / DEFAULT_OUTPUT_DIRNAME
    if sys.platform == "win32":
        return _windows_documents() / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Documents" / APP_NAME

    xdg_docs = os.environ.get("XDG_DOCUMENTS_DIR")
    if xdg_docs:
        candidate = Path(os.path.expandvars(xdg_docs)).expanduser()
        if candidate.is_dir():
            return candidate / APP_NAME
    for candidate in (Path.home() / "Documents", Path.home() / "Music"):
        if candidate.is_dir():
            return candidate / APP_NAME
    return Path.home() / APP_NAME


def reveal(path: Path) -> bool:
    """Open a directory in the platform's file manager.

    Returns False rather than raising: not being able to open a file
    manager is a mild disappointment, not an error worth a dialog. A
    headless Linux box legitimately has no file manager at all.
    """
    target = path if path.is_dir() else path.parent
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
            return True
        command = ["open"] if sys.platform == "darwin" else ["xdg-open"]
        # Detached: a file manager launched here must not die with us, and
        # its chatter must not land in our stdout.
        subprocess.Popen(
            command + [str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=sys.platform != "win32",
        )
        return True
    except (OSError, AttributeError):
        return False
