"""The earcongen window.

Layout is two columns. The left is every setting, grouped and scrollable.
The right is where the files went and a way to listen to them, because the
loop this tool is built around is generate, listen, change one thing,
generate again — and that loop is only as fast as its slowest step.

On the preset mode
------------------
Choosing a preset fills in every control with the value that preset sets
and then locks the lot. It does not hide them. The point is that someone
who picks "r2" and wonders why it sounds like that can read the answer off
the form: the voice changed, the scale changed, the band widened, the
spacing tightened. Switching to Custom unlocks everything and reveals a
Base dropdown, which loads a preset's values as a starting point without
locking them.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import earcongen

from . import paths
from .params import (
    CUSTOM,
    FAMILY_BLURBS,
    GROUPS,
    PRESET_BLURBS,
    VOICE_BLURBS,
    default_values,
    preset_values,
)
from .player import Player
from .widgets import build_control
from .worker import GenerateWorker

#: Offered in the Base dropdown above the presets themselves.
BASE_NONE = "Command-line defaults"


class MainWindow(QMainWindow):
    """Everything. This tool is not big enough to want more windows."""

    settings_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.version = paths.read_version()
        self.setWindowTitle(f"earcongen {self.version}")
        self.resize(1180, 820)

        self.controls: dict[str, object] = {}
        self._thread: QThread | None = None
        self._worker: GenerateWorker | None = None
        self._subfolder_edited = False
        self._loading = False

        self.player = Player(self)
        self.player.failed.connect(self._on_playback_failed)

        self._build_menu()
        self._build_ui()
        self._load_settings()
        self._on_preset_changed(self.preset_combo.currentText())
        self._refresh_output_label()

        self.status = self.statusBar()
        self.status.showMessage(
            f"Ready. {self.player.describe()}. "
            f"Output: {self._output_dir()}"
        )

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build_menu(self) -> None:
        # Held on self: a QMenu created as a local and added to the bar is
        # a well-known way to have menus vanish once Python collects them.
        self.file_menu = self.menuBar().addMenu("&File")

        self.action_generate = QAction("&Generate", self)
        self.action_generate.setShortcut(QKeySequence("Ctrl+G"))
        self.action_generate.triggered.connect(self.generate)
        self.file_menu.addAction(self.action_generate)

        self.action_open = QAction("Open &output folder", self)
        self.action_open.setShortcut(QKeySequence("Ctrl+O"))
        self.action_open.triggered.connect(self._reveal_output)
        self.file_menu.addAction(self.action_open)

        self.file_menu.addSeparator()
        self.action_quit = QAction("&Quit", self)
        self.action_quit.setShortcut(QKeySequence.Quit)
        self.action_quit.triggered.connect(self.close)
        self.file_menu.addAction(self.action_quit)

        self.help_menu = self.menuBar().addMenu("&Help")
        self.action_notes = QAction("Design &notes", self)
        self.action_notes.triggered.connect(self._show_notes)
        self.help_menu.addAction(self.action_notes)
        self.action_about = QAction("&About", self)
        self.action_about.triggered.connect(self._show_about)
        self.help_menu.addAction(self.action_about)

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_settings_panel())
        splitter.addWidget(self._build_output_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(10, 10, 6, 10)

        outer.addWidget(self._build_preset_box())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 6, 0)

        blurbs = {"voice": VOICE_BLURBS, "family": FAMILY_BLURBS}
        for group in GROUPS:
            box = QGroupBox(group.title)
            box.setToolTip(group.blurb)
            box_layout = QVBoxLayout(box)

            caption = QLabel(group.blurb)
            caption.setWordWrap(True)
            caption.setStyleSheet("color: palette(mid);")
            box_layout.addWidget(caption)

            for param in group.params:
                control = build_control(param, blurbs.get(param.key))
                control.changed.connect(self._on_control_changed)
                self.controls[param.key] = control
                box_layout.addWidget(control)
            layout.addWidget(box)

        layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        return panel

    def _build_preset_box(self) -> QWidget:
        box = QGroupBox("Preset")
        box.setToolTip(
            "A preset is a named bundle of settings. Choosing one fills in "
            "every control below so you can see exactly what it changed, and "
            "locks them so the bundle stays intact.\n\n"
            "Custom unlocks everything and lets you start from a preset "
            "without being held to it."
        )
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        label = QLabel("Preset")
        label.setMinimumWidth(132)
        row.addWidget(label)

        self.preset_combo = QComboBox()
        self.preset_combo.addItem(CUSTOM)
        for name in sorted(earcongen.PRESETS):
            self.preset_combo.addItem(name)
            index = self.preset_combo.count() - 1
            self.preset_combo.setItemData(
                index, PRESET_BLURBS.get(name, ""), Qt.ToolTipRole
            )
        self.preset_combo.setToolTip(
            "Custom leaves every setting to you.\n\n"
            "r2 is astromech phrasing that still behaves like a notification "
            "set: in band, pentatonic, phrases kept short.\n\n"
            "r2-full is the unleashed version — chromatic, up into the 2-4 kHz "
            "band, six and seven note phrases. Characterful, and tiring if it "
            "fires forty times a day."
        )
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        row.addWidget(self.preset_combo, 1)

        self.preset_blurb = QLabel("")
        self.preset_blurb.setWordWrap(True)
        self.preset_blurb.setStyleSheet("color: palette(mid);")
        row.addWidget(self.preset_blurb, 2)
        layout.addLayout(row)

        # Only meaningful in Custom mode, so it is hidden the rest of the
        # time rather than disabled: a control that can never apply is
        # clutter, not information.
        self.base_row = QWidget()
        base_layout = QHBoxLayout(self.base_row)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_label = QLabel("Start from")
        base_label.setMinimumWidth(132)
        base_layout.addWidget(base_label)

        self.base_combo = QComboBox()
        self.base_combo.addItem(BASE_NONE)
        for name in sorted(earcongen.PRESETS):
            self.base_combo.addItem(name)
        self.base_combo.setToolTip(
            "Load a preset's settings as a starting point, then change "
            "whatever you like — nothing is locked.\n\n"
            "This overwrites every control below, so it is a starting point "
            "rather than a modifier. Pick it first, then adjust."
        )
        base_layout.addWidget(self.base_combo, 1)

        self.base_apply = QPushButton("Load as baseline")
        self.base_apply.setToolTip(
            "Copy the selected baseline into every control below."
        )
        self.base_apply.clicked.connect(self._apply_baseline)
        base_layout.addWidget(self.base_apply)
        layout.addWidget(self.base_row)

        return box

    def _build_output_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 10, 10, 10)

        dest = QGroupBox("Destination")
        dest.setToolTip(
            "Files are written to a named subfolder inside the base "
            "directory, so pointing this at Documents does not scatter "
            "thirty WAV files across it."
        )
        dest_layout = QVBoxLayout(dest)

        base_row = QHBoxLayout()
        base_row.addWidget(QLabel("Base folder"))
        self.base_dir_edit = QLineEdit(str(paths.default_output_base()))
        self.base_dir_edit.setToolTip(
            "The directory everything is written under. Defaults to the "
            "conventional documents location for this platform, or beside "
            "the binary if a portable marker file is present."
        )
        self.base_dir_edit.textChanged.connect(self._refresh_output_label)
        base_row.addWidget(self.base_dir_edit, 1)
        browse = QPushButton("Browse...")
        browse.setToolTip("Choose the base directory.")
        browse.clicked.connect(self._choose_directory)
        base_row.addWidget(browse)
        dest_layout.addLayout(base_row)

        sub_row = QHBoxLayout()
        sub_row.addWidget(QLabel("Subfolder"))
        self.subfolder_edit = QLineEdit("")
        self.subfolder_edit.setToolTip(
            "Created inside the base folder. Follows the preset or voice "
            "name until you type your own, after which it is left alone.\n\n"
            "Existing files of the same name are overwritten, which is what "
            "makes the generate-listen-adjust loop quick."
        )
        self.subfolder_edit.textEdited.connect(self._on_subfolder_edited)
        self.subfolder_edit.textChanged.connect(self._refresh_output_label)
        sub_row.addWidget(self.subfolder_edit, 1)
        dest_layout.addLayout(sub_row)

        self.output_label = QLabel("")
        self.output_label.setWordWrap(True)
        self.output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.output_label.setStyleSheet("color: palette(mid);")
        dest_layout.addWidget(self.output_label)
        layout.addWidget(dest)

        action_row = QHBoxLayout()
        self.generate_button = QPushButton("Generate")
        self.generate_button.setDefault(True)
        self.generate_button.setToolTip(
            "Render the whole set and write it to the folder above (Ctrl+G)."
        )
        self.generate_button.clicked.connect(self.generate)
        action_row.addWidget(self.generate_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setToolTip(
            "Stop after the cue currently being rendered. Files already "
            "written are kept."
        )
        self.cancel_button.clicked.connect(self._cancel)
        action_row.addWidget(self.cancel_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        results = QGroupBox("Generated cues")
        results.setToolTip(
            "Select a cue to hear it. Contour and note count are shown "
            "because two cues that sound alike usually share both."
        )
        results_layout = QVBoxLayout(results)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["File", "Length", "Contour", "Meaning"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(lambda *_: self._play_selected())
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        results_layout.addWidget(self.tree, 1)

        play_row = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setEnabled(False)
        self.play_button.setToolTip(
            "Play the selected cue. Double-clicking a row does the same."
        )
        self.play_button.clicked.connect(self._play_selected)
        play_row.addWidget(self.play_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_playback)
        play_row.addWidget(self.stop_button)

        self.reveal_button = QPushButton("Open folder")
        self.reveal_button.setToolTip(
            "Open the output folder in the system file manager."
        )
        self.reveal_button.clicked.connect(self._reveal_output)
        play_row.addWidget(self.reveal_button)
        play_row.addStretch(1)
        results_layout.addLayout(play_row)

        layout.addWidget(results, 1)
        return panel

    # ------------------------------------------------------------------ #
    # Preset handling
    # ------------------------------------------------------------------ #

    def _on_preset_changed(self, name: str) -> None:
        custom = name == CUSTOM
        self.base_row.setVisible(custom)
        self.preset_blurb.setText(
            "Every setting is yours to change."
            if custom else PRESET_BLURBS.get(name, "")
        )

        if not custom:
            # Show the preset's own values, starting from the defaults so
            # that settings the preset does not mention are visibly at
            # their normal values rather than left over from a previous
            # experiment.
            self._apply_values(default_values())
            self._apply_values(preset_values(name))

        for control in self.controls.values():
            control.set_locked(not custom)

        if not self._subfolder_edited:
            self._suggest_subfolder()
        self._refresh_output_label()

    def _apply_baseline(self) -> None:
        choice = self.base_combo.currentText()
        if choice == BASE_NONE:
            self._apply_values(default_values())
        else:
            self._apply_values(default_values())
            self._apply_values(preset_values(choice))
        if not self._subfolder_edited:
            self._suggest_subfolder()
        self._refresh_output_label()
        self.statusBar().showMessage(f"Loaded {choice} as a starting point.")

    def _apply_values(self, values: dict) -> None:
        self._loading = True
        try:
            for key, value in values.items():
                control = self.controls.get(key)
                if control is not None:
                    control.set_value(value)
        finally:
            self._loading = False

    def _on_control_changed(self) -> None:
        if self._loading:
            return
        if not self._subfolder_edited:
            self._suggest_subfolder()
        self._refresh_output_label()

    # ------------------------------------------------------------------ #
    # Destination
    # ------------------------------------------------------------------ #

    def _suggest_subfolder(self) -> None:
        preset = self.preset_combo.currentText()
        if preset != CUSTOM:
            name = preset
        else:
            voice = self.controls["voice"].value
            family = self.controls["family"].value
            # "droid-droid" helps nobody: the droid family and the droid
            # voice are the same idea named twice.
            if family == "core" or family == voice or family.startswith(voice):
                name = voice
            else:
                name = f"{family}-{voice}"
        self.subfolder_edit.blockSignals(True)
        self.subfolder_edit.setText(name)
        self.subfolder_edit.blockSignals(False)

    def _on_subfolder_edited(self, _text: str) -> None:
        self._subfolder_edited = True

    def _output_dir(self) -> Path:
        base = Path(self.base_dir_edit.text()).expanduser()
        sub = self.subfolder_edit.text().strip()
        # Anything with a separator in it would silently escape the base
        # directory, so only the final component is honoured.
        sub = Path(sub).name if sub else ""
        return base / sub if sub else base

    def _refresh_output_label(self) -> None:
        target = self._output_dir()
        exists = " (exists; matching files will be overwritten)" if target.is_dir() else ""
        self.output_label.setText(f"Writing to: {target}{exists}")

    def _choose_directory(self) -> None:
        start = self.base_dir_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose the base output folder", start
        )
        if chosen:
            self.base_dir_edit.setText(chosen)

    def _reveal_output(self) -> None:
        target = self._output_dir()
        if not target.is_dir():
            target = target.parent
        if not target.is_dir():
            self.statusBar().showMessage("Nothing to open yet — generate first.")
            return
        if not paths.reveal(target):
            self.statusBar().showMessage(f"No file manager available. {target}")

    # ------------------------------------------------------------------ #
    # Generation
    # ------------------------------------------------------------------ #

    def build_args(self) -> argparse.Namespace:
        """The same Namespace the command line would have produced.

        Going through argparse's own defaults means every option the GUI
        does not expose still has the value earcongen expects, rather than
        being absent and failing deep inside a render.
        """
        args = earcongen.build_parser().parse_args([])
        for key, control in self.controls.items():
            setattr(args, key, control.value)
        args.out = str(self._output_dir())
        args.play = False
        args.spec = None
        args.preset = None
        return args

    def generate(self) -> None:
        if self._thread is not None:
            return

        args = self.build_args()
        try:
            Path(args.out).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(
                self, "Cannot write there",
                f"{args.out}\n\n{exc}\n\nChoose another folder.",
            )
            return

        notices = self._shortening_notices(args)
        self.tree.clear()
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        # Both objects are held for the duration. A QThread referenced
        # only by a local goes out of scope while running and takes the
        # process with it.
        self._thread = QThread(self)
        self._worker = GenerateWorker(args)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.file_written.connect(self._on_file_written)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(
            lambda files: self._on_success(files, notices)
        )
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

        self.statusBar().showMessage("Rendering...")

    def _on_progress(self, index: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(index)

    def _on_file_written(self, path: Path, duration: float, contour: str,
                         notes: int, label: str) -> None:
        item = QTreeWidgetItem([
            path.name,
            f"{duration:.2f} s",
            f"{contour} ({notes}n)",
            label,
        ])
        item.setData(0, Qt.UserRole, str(path))
        item.setToolTip(0, str(path))
        self.tree.addTopLevelItem(item)

    def _shortening_notices(self, args) -> list[str]:
        """What the note cap did, in words, before anything is rendered.

        Worth saying out loud: a cap can quietly turn two cues into one
        sound, and the number of one-note cues a band can hold is a hard
        physical limit rather than something the tool can work around.
        """
        if not args.note_count:
            return []
        specs = earcongen.resolve_specs(args)

        if args.cap_mode == "truncate":
            groups = earcongen.degenerate_groups(
                specs, args.note_count, earcongen.pitch_context(args), "truncate"
            )
            if not groups:
                return []
            listed = "; ".join(", ".join(g) for g in groups)
            return [f"truncation made these identical: {listed} "
                    f"(redesign would separate them)"]

        pitch = earcongen.pitch_context(args)
        plans = earcongen.plan_family(specs, args.note_count, args.cap_mode, pitch)
        notices = []
        moved = [p for p in plans if p.moved and not p.unresolved]
        if moved:
            listed = ", ".join(p.spec.slug for p in moved)
            notices.append(f"separated by register: {listed}")
        stuck = [p for p in plans if p.unresolved]
        if stuck:
            capacity = earcongen.distinct_pitch_capacity(pitch)
            notices.append(
                f"no register left for {', '.join(p.spec.slug for p in stuck)} "
                f"-- this band holds {capacity} distinguishable pitches and "
                f"{len(specs)} cues need more. Widen the band or raise the cap."
            )
        return notices

    def _on_success(self, files: list, notices: list) -> None:
        message = f"Wrote {len(files)} cues to {self._output_dir()}"
        if notices:
            message += "  --  " + "  --  ".join(notices)
        self.statusBar().showMessage(message)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _on_failed(self, message: str) -> None:
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "Generation stopped", message)

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.statusBar().showMessage("Stopping after the current cue...")

    def _on_thread_finished(self) -> None:
        # Cleared only once the thread has actually stopped; dropping the
        # references while it runs is the crash this ordering avoids.
        self._thread = None
        self._worker = None
        self.progress.setVisible(False)
        self.generate_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    # ------------------------------------------------------------------ #
    # Playback
    # ------------------------------------------------------------------ #

    def _on_selection_changed(self) -> None:
        has = self.tree.currentItem() is not None
        self.play_button.setEnabled(has)
        self.stop_button.setEnabled(has)

    def _selected_path(self) -> Path | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        stored = item.data(0, Qt.UserRole)
        return Path(stored) if stored else None

    def _play_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        self.player.play(path)
        self.statusBar().showMessage(f"Playing {path.name}  ({self.player.describe()})")

    def _stop_playback(self) -> None:
        self.player.stop()

    def _on_playback_failed(self, message: str) -> None:
        self.statusBar().showMessage(message)

    # ------------------------------------------------------------------ #
    # Help
    # ------------------------------------------------------------------ #

    def _show_notes(self) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Design notes")
        dialog.setIcon(QMessageBox.NoIcon)
        dialog.setText("Why the defaults are what they are")
        browser = QTextBrowser()
        browser.setPlainText(earcongen.NOTES)
        browser.setMinimumSize(720, 520)
        layout = dialog.layout()
        layout.addWidget(browser, 1, 0, 1, layout.columnCount())
        dialog.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About earcongen",
            f"<b>earcongen {self.version}</b><br><br>"
            "Generate a family of notification sounds that belong together, "
            "stay individually distinguishable, and do not make people want "
            "to turn them off.<br><br>"
            f"{self.player.describe()}<br>"
            f"Settings: {paths.settings_file()}<br><br>"
            "Qt is used under the LGPL v3; see THIRD-PARTY-NOTICES.md."
        )

    # ------------------------------------------------------------------ #
    # Settings persistence
    # ------------------------------------------------------------------ #

    def _load_settings(self) -> None:
        try:
            data = json.loads(paths.settings_file().read_text())
        except (OSError, ValueError):
            self._suggest_subfolder()
            return

        base = data.get("base_dir")
        if base:
            self.base_dir_edit.setText(base)

        preset = data.get("preset", CUSTOM)
        if preset == CUSTOM or preset in earcongen.PRESETS:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText(preset)
            self.preset_combo.blockSignals(False)

        # Values are restored before the preset lock is applied, so a
        # saved Custom session comes back exactly as it was left.
        values = data.get("values") or {}
        self._apply_values({k: v for k, v in values.items() if k in self.controls})

        subfolder = data.get("subfolder")
        if subfolder:
            self.subfolder_edit.setText(subfolder)
            self._subfolder_edited = bool(data.get("subfolder_edited", False))
        else:
            self._suggest_subfolder()

    def _save_settings(self) -> None:
        payload = {
            "version": self.version,
            "preset": self.preset_combo.currentText(),
            "base_dir": self.base_dir_edit.text(),
            "subfolder": self.subfolder_edit.text(),
            "subfolder_edited": self._subfolder_edited,
            "values": {k: c.value for k, c in self.controls.items()},
        }
        try:
            paths.config_dir().mkdir(parents=True, exist_ok=True)
            paths.settings_file().write_text(json.dumps(payload, indent=2))
        except OSError:
            # Losing preferences is a nuisance; refusing to close over it
            # would be worse.
            pass

    def closeEvent(self, event) -> None:
        if self._thread is not None:
            self._worker.cancel() if self._worker else None
            self._thread.quit()
            self._thread.wait(3000)
        self.player.stop()
        self._save_settings()
        super().closeEvent(event)
