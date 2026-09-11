# Third-party notices

earcongen itself is MIT licensed; see [LICENSE](LICENSE).

The command-line tools — `earcongen.py` and `earconcheck.py` — depend on
numpy and nothing else. The graphical front end and the binaries built
from it additionally bundle Qt, which carries obligations that a source
checkout does not. Those obligations are the reason this file exists.

## NumPy

- **Licence:** BSD-3-Clause
- **Used for:** synthesis and analysis, in both scripts and the GUI
- **Linked:** dynamically, as an ordinary Python dependency
- **Source:** https://github.com/numpy/numpy

BSD-3-Clause requires the copyright notice and disclaimer to accompany
binary redistributions. NumPy ships its licence inside the installed
package, and PyInstaller carries it into the bundle.

## Qt for Python (PySide6)

- **Licence:** LGPL v3 — see [licenses/LGPL-3.0-only.txt](licenses/LGPL-3.0-only.txt)
- **Also relevant:** [licenses/GPL-3.0-only.txt](licenses/GPL-3.0-only.txt),
  which LGPLv3 incorporates by reference
- **Used for:** the entire graphical front end, and audio playback via
  QtMultimedia
- **Linked:** dynamically. PyInstaller bundles Qt as ordinary shared
  libraries loaded at runtime; nothing is statically linked
- **Source:** https://code.qt.io/cgit/pyside/pyside-setup.git/

### How the LGPL obligations are met

**Section 4(b) — a copy of the licence must accompany the binary.** The
texts in `licenses/` are bundled inside every binary and are also placed
in every release archive alongside it. A link would not satisfy this.

**Section 4(d)(1) — the user must be able to relink against a modified
Qt.** The complete source of this application is public, the PyInstaller
build configuration is in `packaging/`, and PySide6 is a `pip install`
away. Anyone can therefore rebuild these binaries against their own build
of Qt, using `scripts/build_local.sh`, which is the same build the release
workflow runs.

**Modifications.** Qt is used unmodified.

### Excluded Qt modules

Most of Qt is excluded from the build; see `packaging/build_common.py` for
the list. That is a size decision — WebEngine alone is hundreds of
megabytes — and does not change the licensing position for what remains.

QtMultimedia is deliberately kept, because it is what plays a cue back
inside the window. Note that Qt's FFmpeg-based multimedia backend may
report its own licence terms at start-up; earcongen only ever plays
uncompressed 16-bit PCM WAV files it has just written itself, and does not
use any codec beyond that.

## PyInstaller

- **Licence:** GPL-2.0 with a bootloader exception
- **Used for:** producing the binaries; not a runtime dependency

The exception explicitly permits distributing works built with it under
any licence, including proprietary ones. No PyInstaller code beyond the
bootloader ends up in the artefact, and the bootloader is covered by that
exception.

## Development-only dependencies

`pytest` (MIT) and `ruff` (MIT) are used to test and lint the project.
Neither is bundled or redistributed.
