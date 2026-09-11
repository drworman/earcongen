"""Controls built from the metadata in params.py.

Each control owns one setting, exposes it as ``value`` (None where the
parameter is optional and switched off), and emits ``changed`` when the
user moves it. Nothing here knows what a preset is or how audio is
rendered; the window wires that up.

Every control carries the parameter's tooltip on every one of its child
widgets, because a tooltip on the label only is a tooltip most people
never find.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QWidget,
)

from .params import Param

#: Width reserved for the label column, so every control in the window
#: lines up regardless of which group it sits in.
LABEL_WIDTH = 132

#: Width of the numeric entry beside each slider.
ENTRY_WIDTH = 118


class ControlBase(QWidget):
    """Common plumbing: a label, a tooltip, and a lock."""

    changed = Signal()

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.param = param
        self._locked = False

        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(0, 2, 0, 2)
        self.row.setSpacing(8)

        self.label = QLabel(param.label)
        self.label.setMinimumWidth(LABEL_WIDTH)
        self.label.setMaximumWidth(LABEL_WIDTH)
        self.label.setWordWrap(True)
        self.row.addWidget(self.label)

        self.setToolTip(param.tooltip)
        self.label.setToolTip(param.tooltip)

    def set_locked(self, locked: bool) -> None:
        """Show the value but refuse edits.

        Locking rather than hiding is the point of the preset mode: the
        user is meant to see exactly which settings a preset moved and
        where it put them.
        """
        self._locked = locked
        self._apply_enabled()

    def _apply_enabled(self) -> None:  # pragma: no cover - overridden
        pass

    # -- interface used by the window ------------------------------------
    @property
    def value(self):  # pragma: no cover - overridden
        raise NotImplementedError

    def set_value(self, value) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class NumberControl(ControlBase):
    """A slider and a spin box over the same value, optionally switchable.

    The slider works in units of the parameter's step, which keeps its
    integer range small and makes every notch a value the spin box can
    represent exactly. The two are kept in sync with signals blocked, so
    neither can drive the other into a loop.
    """

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(param, parent)
        self._is_int = param.kind == "int"
        self._step = param.step if param.step else 1.0

        self.toggle: QCheckBox | None = None
        if param.optional:
            self.toggle = QCheckBox()
            self.toggle.setToolTip(
                f"{param.optional_label}\n\nUnticked, earcongen uses the "
                f"value built into the chosen voice. Tick to set it "
                f"yourself.\n\n{param.tooltip}"
            )
            self.toggle.toggled.connect(self._on_toggled)
            self.row.addWidget(self.toggle)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(self._to_units(param.minimum))
        self.slider.setMaximum(self._to_units(param.maximum))
        self.slider.setToolTip(param.tooltip)
        self.slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.slider.valueChanged.connect(self._on_slider)
        self.row.addWidget(self.slider, 1)

        self.spin: QSpinBox | QDoubleSpinBox
        if self._is_int:
            self.spin = QSpinBox()
            self.spin.setRange(int(param.minimum), int(param.maximum))
            self.spin.setSingleStep(int(self._step) or 1)
        else:
            self.spin = QDoubleSpinBox()
            self.spin.setDecimals(param.decimals)
            self.spin.setRange(param.minimum, param.maximum)
            self.spin.setSingleStep(self._step)
        self.spin.setSuffix(param.suffix)
        self.spin.setToolTip(param.tooltip)
        self.spin.setFixedWidth(ENTRY_WIDTH)
        self.spin.setAlignment(Qt.AlignRight)
        self.spin.valueChanged.connect(self._on_spin)
        self.row.addWidget(self.spin)

        default = param.default
        self.set_value(default if default is not None else param.minimum)
        if param.optional:
            self.toggle.setChecked(default is not None)
            self._apply_enabled()

    # -- unit conversion --------------------------------------------------
    def _to_units(self, value: float) -> int:
        return int(round(value / self._step))

    def _from_units(self, units: int) -> float:
        value = units * self._step
        return int(round(value)) if self._is_int else value

    # -- signal handling --------------------------------------------------
    def _on_slider(self, units: int) -> None:
        value = self._from_units(units)
        self.spin.blockSignals(True)
        self.spin.setValue(value)
        self.spin.blockSignals(False)
        self.changed.emit()

    def _on_spin(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(self._to_units(value))
        self.slider.blockSignals(False)
        self.changed.emit()

    def _on_toggled(self, _checked: bool) -> None:
        self._apply_enabled()
        self.changed.emit()

    def _apply_enabled(self) -> None:
        active = not self._locked and (self.toggle is None or self.toggle.isChecked())
        self.slider.setEnabled(active)
        self.spin.setEnabled(active)
        if self.toggle is not None:
            self.toggle.setEnabled(not self._locked)
        self.label.setEnabled(not self._locked)

    # -- value ------------------------------------------------------------
    @property
    def value(self):
        if self.toggle is not None and not self.toggle.isChecked():
            return None
        return int(self.spin.value()) if self._is_int else float(self.spin.value())

    def set_value(self, value) -> None:
        if value is None:
            if self.toggle is not None:
                self.toggle.blockSignals(True)
                self.toggle.setChecked(False)
                self.toggle.blockSignals(False)
                self._apply_enabled()
            return

        if self.toggle is not None:
            self.toggle.blockSignals(True)
            self.toggle.setChecked(True)
            self.toggle.blockSignals(False)

        # Clamped rather than rejected: a preset may legitimately sit
        # outside a slider's comfortable range, and silently refusing to
        # show the value it set would be worse than showing it pinned.
        numeric = max(self.param.minimum, min(self.param.maximum, float(value)))
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(int(round(numeric)) if self._is_int else numeric)
        self.slider.setValue(self._to_units(numeric))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)
        self._apply_enabled()


class ChoiceControl(ControlBase):
    """A dropdown, with a description of the selected item underneath."""

    def __init__(self, param: Param, blurbs: dict[str, str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(param, parent)
        self._blurbs = blurbs or {}

        self.combo = QComboBox()
        self.combo.addItems(param.choices)
        self.combo.setToolTip(param.tooltip)
        self.combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for index, name in enumerate(param.choices):
            if name in self._blurbs:
                self.combo.setItemData(index, self._blurbs[name], Qt.ToolTipRole)
        self.combo.currentTextChanged.connect(self._on_changed)
        self.row.addWidget(self.combo, 1)

        self.description = QLabel("")
        self.description.setWordWrap(True)
        self.description.setMinimumWidth(240)
        self.description.setToolTip(param.tooltip)
        self.description.setStyleSheet("color: palette(mid);")
        self.row.addWidget(self.description, 1)

        if param.default in param.choices:
            self.combo.setCurrentText(param.default)
        self._refresh_description()

    def _on_changed(self, _text: str) -> None:
        self._refresh_description()
        self.changed.emit()

    def _refresh_description(self) -> None:
        self.description.setText(self._blurbs.get(self.combo.currentText(), ""))

    def _apply_enabled(self) -> None:
        self.combo.setEnabled(not self._locked)
        self.label.setEnabled(not self._locked)
        self.description.setEnabled(not self._locked)

    @property
    def value(self) -> str:
        return self.combo.currentText()

    def set_value(self, value) -> None:
        if value is None:
            return
        self.combo.blockSignals(True)
        self.combo.setCurrentText(str(value))
        self.combo.blockSignals(False)
        self._refresh_description()


class BoolControl(ControlBase):
    """A single checkbox."""

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(param, parent)
        self.box = QCheckBox(param.label)
        self.box.setToolTip(param.tooltip)
        self.box.setChecked(bool(param.default))
        self.box.toggled.connect(lambda _: self.changed.emit())

        # The checkbox carries its own text, so the label column would be
        # a duplicate. It stays in the layout as a spacer to keep this row
        # aligned with every other row.
        self.label.setText("")
        self.row.addWidget(self.box, 1)

    def _apply_enabled(self) -> None:
        self.box.setEnabled(not self._locked)

    @property
    def value(self) -> bool:
        return self.box.isChecked()

    def set_value(self, value) -> None:
        if value is None:
            return
        self.box.blockSignals(True)
        self.box.setChecked(bool(value))
        self.box.blockSignals(False)


def build_control(param: Param, blurbs: dict[str, str] | None = None) -> ControlBase:
    """The right control for a parameter's kind."""
    if param.kind == "choice":
        return ChoiceControl(param, blurbs)
    if param.kind == "bool":
        return BoolControl(param)
    return NumberControl(param)
