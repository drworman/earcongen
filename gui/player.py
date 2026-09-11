"""Playing a generated cue from inside the application.

Two paths, tried in order.

``QSoundEffect`` is the right tool: it is built for exactly this — short,
uncompressed, low-latency samples — and it plays without blocking the
interface. It is used whenever QtMultimedia is present and reports a
working backend.

The fallback shells out to whatever the platform provides, the same way
``earcongen.play()`` does from the command line. That path exists because
QtMultimedia's Linux backend depends on a running sound server, and a
machine that has ``paplay`` but no working Qt audio plugin is a real
configuration rather than a hypothetical one.

Either way the caller sees the same three methods, so the window does not
have to care which is in use.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal

try:  # QtMultimedia is a separate wheel component and can be absent.
    from PySide6.QtMultimedia import QSoundEffect
except ImportError:  # pragma: no cover - depends on the install
    QSoundEffect = None  # type: ignore[assignment]


def external_player() -> list[str] | None:
    """The best available command-line player, or None.

    Ordered by how likely each is to be both present and correct.
    ``winsound`` is handled separately since it is a module, not a
    command.
    """
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay"]
    for command in (["paplay"], ["pw-play"], ["aplay", "-q"],
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if shutil.which(command[0]):
            return command
    return None


class Player(QObject):
    """Plays one file at a time, stopping whatever was already playing."""

    #: Emitted with a human-readable reason when playback could not start.
    failed = Signal(str)
    #: Emitted with the path when playback begins.
    started = Signal(Path)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._effect = None
        self._process: subprocess.Popen | None = None
        self._backend = "none"

        if QSoundEffect is not None:
            # Held as an attribute for the lifetime of the Player. A
            # QSoundEffect that goes out of scope stops mid-sample and
            # can take the process with it, which is the standard Qt
            # object-lifetime trap.
            self._effect = QSoundEffect(self)
            self._backend = "qt"
        elif external_player() or sys.platform == "win32":
            self._backend = "external"

    @property
    def backend(self) -> str:
        """Which path is in use: ``qt``, ``external`` or ``none``."""
        return self._backend

    def describe(self) -> str:
        """One line for the status bar, so the user knows what is playing."""
        if self._backend == "qt":
            return "audio: Qt"
        if self._backend == "external":
            command = external_player()
            return f"audio: {command[0]}" if command else "audio: system"
        return "audio: unavailable"

    def play(self, path: Path) -> None:
        self.stop()
        if not path.is_file():
            self.failed.emit(f"{path.name} is no longer on disk.")
            return

        if self._effect is not None:
            self._effect.setSource(QUrl.fromLocalFile(str(path)))
            self._effect.setVolume(1.0)
            self._effect.play()
            # A backend that failed to load leaves the effect in an error
            # state rather than raising, so fall through to the external
            # player rather than sitting in silence.
            if self._effect.status() == QSoundEffect.Error:
                self._backend = "external"
                self._play_external(path)
                return
            self.started.emit(path)
            return

        self._play_external(path)

    def _play_external(self, path: Path) -> None:
        if sys.platform == "win32":
            try:
                import winsound

                # Asynchronous, so the interface stays responsive. This
                # returns immediately and the sound plays on.
                winsound.PlaySound(
                    str(path), winsound.SND_FILENAME | winsound.SND_ASYNC
                )
                self.started.emit(path)
                return
            except (ImportError, RuntimeError) as exc:
                self.failed.emit(f"Windows playback failed: {exc}")
                return

        command = external_player()
        if command is None:
            self.failed.emit(
                "No audio backend found. Install a player such as paplay, "
                "aplay or ffplay, or open the output folder and listen there."
            )
            return
        try:
            self._process = subprocess.Popen(
                command + [str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.started.emit(path)
        except OSError as exc:
            self.failed.emit(f"Could not start {command[0]}: {exc}")

    def stop(self) -> None:
        if self._effect is not None:
            self._effect.stop()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self._process.kill()
        self._process = None
        if sys.platform == "win32" and self._effect is None:
            try:
                import winsound

                winsound.PlaySound(None, winsound.SND_PURGE)
            except (ImportError, RuntimeError):  # pragma: no cover
                pass
