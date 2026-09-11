"""Shared PyInstaller configuration for the earcongen binary.

Imported by ``earcongen.spec`` so the build settings live somewhere a
human can read them rather than buried in a generated spec.

On excluding Qt modules
-----------------------
PySide6 ships a very large surface: WebEngine alone is hundreds of
megabytes. The GUI uses QtCore, QtGui, QtWidgets and QtMultimedia and
nothing else, so everything else is excluded explicitly. This is a size
decision, not a licensing one.

QtMultimedia is deliberately *not* excluded. It is what plays a cue back
inside the window, which is half the point of having a window; without it
every audition falls back to shelling out to whatever player the machine
happens to have.

On numpy
--------
Unlike the ED tools, numpy is a genuine runtime dependency here — it is
the synthesis engine — so it must not be excluded. Adding it to the
exclude list produces a binary that starts and then fails on the first
render, which is a slow way to discover the mistake.

On the Qt licence
-----------------
Qt is LGPL v3 and is never statically linked; PyInstaller bundles it as
ordinary shared libraries loaded at runtime. The licence texts are added
to DATA_FILES below so a copy travels inside every binary, and the
relinking requirement is met by publishing the complete source.
"""

from __future__ import annotations

from pathlib import Path

#: Repository root, derived from this file's own location. PyInstaller
#: injects SPECPATH into the spec's namespace only, not into modules the
#: spec imports, so it cannot be relied on here.
ROOT = Path(__file__).resolve().parent.parent

#: The version file is bundled so a frozen binary can report its version.
#: The release workflow's smoke test compares what it prints against the
#: tag, so this entry is load-bearing rather than cosmetic.
VERSION_FILE = ROOT / "version"

#: Files shipped alongside the code inside the bundle.
DATA_FILES = [
    (str(VERSION_FILE), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD-PARTY-NOTICES.md"), "."),
    (str(ROOT / "licenses"), "licenses"),
]

#: Qt modules earcongen never touches.
QT_EXCLUDES = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtLocation",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
]

#: Heavyweight packages that may be present in a build environment but
#: are never imported. numpy is conspicuously absent: it is required.
OTHER_EXCLUDES = [
    "IPython",
    "matplotlib",
    "pandas",
    "pytest",
    "scipy",
    "tkinter",
]

EXCLUDES = QT_EXCLUDES + OTHER_EXCLUDES

#: earcongui imports these through the package, which static analysis
#: follows, but naming them makes a missing module a build error rather
#: than a crash on first use.
HIDDEN_IMPORTS = [
    "earcongen",
    "gui.app",
    "gui.params",
    "gui.paths",
    "gui.player",
    "gui.widgets",
    "gui.worker",
    "gui.win_console",
]


def analysis_kwargs(entry_point: str = "earcongui.py") -> dict:
    """Keyword arguments for a PyInstaller ``Analysis``."""
    return {
        "scripts": [str(ROOT / entry_point)],
        # The repository root, because earcongen.py sits there as a
        # top-level module rather than inside a package.
        "pathex": [str(ROOT)],
        "binaries": [],
        "datas": DATA_FILES,
        "hiddenimports": list(HIDDEN_IMPORTS),
        "hookspath": [],
        "hooksconfig": {},
        "runtime_hooks": [],
        "excludes": EXCLUDES,
        "noarchive": False,
        "optimize": 0,
    }
