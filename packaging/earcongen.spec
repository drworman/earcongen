# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the earcongen GUI binary.

Build with:
    pyinstaller packaging/earcongen.spec --noconfirm

The command-line tools are not frozen. earcongen.py and earconcheck.py
need numpy and nothing else, run anywhere Python does, and are meant to
be read and edited — wrapping them in a 60 MB binary would take something
away rather than add to it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH)))
from build_common import ROOT, analysis_kwargs  # noqa: E402

APP_NAME = "EarconGen"
ICON = ROOT / "packaging" / "icons" / "earcongen.ico"
ICNS = ROOT / "packaging" / "icons" / "earcongen.icns"

a = Analysis(**analysis_kwargs("earcongui.py"))
pyz = PYZ(a.pure)

# Icons are optional: a build without them is correct, just plain. See
# packaging/icons/README.md.
icon = None
if sys.platform == "win32" and ICON.is_file():
    icon = str(ICON)
elif sys.platform == "darwin" and ICNS.is_file():
    icon = str(ICNS)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX corrupts signed Qt libraries on Windows
    runtime_tmpdir=None,
    console=False,      # GUI application: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="net.indevlin.earcongen",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": "earcongen",
            "CFBundleShortVersionString": (ROOT / "version").read_text().strip(),
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": (
                "MIT licensed. Uses Qt for Python under the LGPL v3."
            ),
        },
    )
