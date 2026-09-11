#!/usr/bin/env python3
"""earcongui -- the graphical front end for earcongen.

    ./earcongui.py                 open the window
    ./earcongui.py --cli version   print the version and exit

The CLI branch exists for the release workflow, which starts the built
binary and checks that the version it reports matches the tag. It runs
before Qt is imported, so a machine with no display can still verify a
build.

Requires PySide6 in addition to numpy. The command-line tool does not;
see requirements.txt.
"""

from __future__ import annotations

import sys
from pathlib import Path

# A frozen build has the repository root on sys.path already. From a
# checkout it does not, and `import earcongen` must work from any working
# directory, so the root is added explicitly.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gui import paths
from gui.win_console import enable_console_output

USAGE = """\
usage: earcongui [--cli version]

With no arguments, opens the earcongen window.

  --cli version   print the version datestamp and exit

Every generation option lives in the window. For scripted or batch use,
earcongen.py is the command-line tool and takes the same settings as
flags.
"""


def run_cli(argv: list[str]) -> int:
    """The non-graphical commands. Never imports Qt."""
    enable_console_output()
    if argv == ["version"]:
        print(paths.read_version())
        return 0
    print(USAGE, file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "--cli":
        return run_cli(argv[1:])
    if argv and argv[0] in ("-h", "--help"):
        enable_console_output()
        print(USAGE)
        return 0
    if argv and argv[0] in ("-V", "--version"):
        enable_console_output()
        print(paths.read_version())
        return 0
    if argv:
        enable_console_output()
        print(f"Unrecognised argument: {argv[0]}\n", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 2

    # Imported here so that --cli works on a machine with no Qt platform
    # plugin available, which is exactly the situation in CI.
    from PySide6.QtWidgets import QApplication

    from gui.app import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("earcongen")
    app.setApplicationVersion(paths.read_version())
    app.setOrganizationName("earcongen")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
