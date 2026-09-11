"""Rendering off the interface thread.

A family of eight short cues renders in well under a second, but the
settings that make it slow are exactly the ones people reach for while
exploring: a long note length, a wide ring-out, and the `all` set is
thirty-four cues. Rendering on the GUI thread would freeze the window
during precisely the experiments the tool exists to support.

On object lifetimes
-------------------
The worker and its thread are both held by the window for as long as the
run lasts. A QThread whose only reference is a local variable is collected
while still running, and the process dies with it — this is the most
common way to crash a Qt application that otherwise works. `finished`
drives `quit`, then `deleteLater` on both objects, and the window drops
its references only after the thread has actually stopped.
"""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal

import earcongen


class GenerateWorker(QObject):
    """Renders one family, reporting each file as it is written."""

    #: path, duration in seconds, contour name, note count, label
    file_written = Signal(Path, float, str, int, str)
    #: index of the cue just finished, and the total
    progress = Signal(int, int)
    #: every file, in order, once the run has succeeded
    finished_ok = Signal(list)
    #: a message suitable for showing the user
    failed = Signal(str)
    #: always emitted last, success or failure
    finished = Signal()

    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self._args = args
        self._cancelled = False

    def cancel(self) -> None:
        """Ask the run to stop after the current cue.

        Rendering a single cue is fast enough that interrupting it midway
        would buy nothing and risk a half-written WAV, so cancellation is
        checked between files only.
        """
        self._cancelled = True

    def run(self) -> None:
        try:
            specs = earcongen.resolve_specs(self._args)
            total = len(specs)
            written: list[Path] = []
            index = 0

            def on_file(item: earcongen.Rendered) -> None:
                nonlocal index
                index += 1
                written.append(item.path)
                self.file_written.emit(
                    item.path, item.duration, item.spec.contour,
                    item.notes, item.spec.label,
                )
                self.progress.emit(index, total)
                if self._cancelled:
                    raise _Cancelled

            earcongen.generate_family(self._args, on_file=on_file)
            self.finished_ok.emit(written)

        except _Cancelled:
            self.failed.emit("Cancelled. Files written so far have been kept.")
        except FileNotFoundError as exc:
            self.failed.emit(f"Could not write to that location: {exc}")
        except PermissionError as exc:
            self.failed.emit(f"Permission denied: {exc}")
        except Exception as exc:
            # The traceback goes to stderr for anyone running from a
            # terminal; the user gets the message. Losing the detail
            # entirely would make a bug report useless.
            traceback.print_exc()
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class _Cancelled(Exception):
    """Internal: unwinds the render loop when the user cancels."""
