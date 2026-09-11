"""Tests for the graphical front end.

These run under the offscreen platform plugin, so they need no display and
no xvfb. The value is mostly in the first two: they are what stops the GUI
and the command line drifting apart, which is the failure this design was
arranged to prevent and which no amount of clicking would reveal quickly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PySide6", reason="GUI tests need PySide6")

import earcongen
from gui import params


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    # Redirected so a test run cannot overwrite a real user's settings.
    # gui.app calls these through the module, so patching here reaches it.
    from gui import paths as gui_paths

    monkeypatch.setattr(gui_paths, "config_dir", lambda: tmp_path / "config")
    monkeypatch.setattr(gui_paths, "settings_file",
                        lambda: tmp_path / "config" / "settings.json")
    monkeypatch.setattr(gui_paths, "default_output_base", lambda: tmp_path / "out")

    from gui.app import MainWindow

    win = MainWindow()
    yield win
    win.close()


# --------------------------------------------------------------------------
# The GUI and the CLI must agree
# --------------------------------------------------------------------------

def test_every_gui_setting_is_a_real_cli_option():
    """A control for an option earcongen does not have would be ignored
    silently, which is worse than a crash."""
    for key in params.ALL_PARAMS:
        assert key in params.CLI_DEFAULTS, key


def test_choice_controls_offer_exactly_the_cli_choices():
    for key in ("voice", "scale", "family"):
        param = params.ALL_PARAMS[key]
        assert param.choices, key
        assert param.choices == params.choices_for(key)


def test_defaults_come_from_the_parser_not_a_copy():
    assert params.ALL_PARAMS["root"].default == 523.25
    assert params.ALL_PARAMS["gap_ms"].default == 150.0
    # Optional settings default to None, which is what makes the
    # "use the voice's own value" checkbox start unticked.
    assert params.ALL_PARAMS["attack_ms"].default is None


def test_defaults_sit_inside_their_slider_bounds():
    """A default outside its own bounds would be silently clamped, so the
    form would open showing a value the tool would not actually use."""
    for key, param in params.ALL_PARAMS.items():
        if param.kind not in ("float", "int"):
            continue
        if param.default is None:
            continue
        assert param.minimum <= param.default <= param.maximum, key


def test_preset_values_are_all_controllable():
    """Every setting a preset moves must have a control, or the preset
    would change something the user cannot see."""
    for name in earcongen.PRESETS:
        cfg = earcongen.PRESETS[name]
        controllable = set(params.preset_values(name))
        uncontrolled = set(cfg) - controllable - {"blurb", "out"}
        assert not uncontrolled, (name, uncontrolled)


def test_every_param_has_a_real_tooltip():
    for key, param in params.ALL_PARAMS.items():
        assert len(param.tooltip) > 80, key


# --------------------------------------------------------------------------
# Preset behaviour
# --------------------------------------------------------------------------

def test_choosing_a_preset_shows_its_values_and_locks_them(window):
    window.preset_combo.setCurrentText("r2-full")
    assert window.controls["voice"].value == "droid_wild"
    assert window.controls["scale"].value == "chromatic"
    assert window.controls["ceiling"].value == 3200.0
    # Visible but not editable: the point is that the user can read what
    # the preset did.
    assert not window.controls["voice"].combo.isEnabled()
    assert not window.controls["ceiling"].slider.isEnabled()


def test_custom_unlocks_and_reveals_the_baseline_picker(window):
    window.preset_combo.setCurrentText("r2")
    assert not window.base_row.isVisibleTo(window)

    window.preset_combo.setCurrentText(params.CUSTOM)
    assert window.controls["voice"].combo.isEnabled()
    assert window.base_row.isVisibleTo(window)


def test_baseline_loads_a_preset_without_locking(window):
    window.preset_combo.setCurrentText(params.CUSTOM)
    window.base_combo.setCurrentText("r2")
    window._apply_baseline()
    assert window.controls["voice"].value == "droid"
    assert window.controls["root"].value == 587.33
    assert window.controls["root"].slider.isEnabled()


def test_preset_resets_settings_it_does_not_mention(window):
    """Otherwise a preset inherits whatever the previous experiment left
    behind, and no two runs of the same preset match."""
    window.preset_combo.setCurrentText(params.CUSTOM)
    window.controls["gain"].set_value(1.9)
    window.preset_combo.setCurrentText("r2")
    assert window.controls["gain"].value == params.ALL_PARAMS["gain"].default


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------

def test_optional_control_reports_none_when_unticked(window):
    control = window.controls["attack_ms"]
    control.set_value(None)
    assert control.value is None
    control.set_value(18.0)
    assert control.value == 18.0


def test_slider_and_spinbox_stay_in_step(window):
    control = window.controls["gap_ms"]
    control.spin.setValue(240.0)
    assert control.slider.value() == control._to_units(240.0)
    control.slider.setValue(control._to_units(300.0))
    assert control.spin.value() == pytest.approx(300.0)


def test_out_of_range_preset_value_is_clamped_not_dropped(window):
    control = window.controls["ceiling"]
    control.set_value(99999.0)
    assert control.value == params.ALL_PARAMS["ceiling"].maximum


# --------------------------------------------------------------------------
# Destination and rendering
# --------------------------------------------------------------------------

def test_subfolder_cannot_escape_the_base_directory(window, tmp_path):
    window.base_dir_edit.setText(str(tmp_path))
    window.subfolder_edit.setText("../../etc")
    assert window._output_dir().parent == tmp_path


def test_build_args_matches_the_parser(window, tmp_path):
    window.base_dir_edit.setText(str(tmp_path))
    window.preset_combo.setCurrentText("r2")
    args = window.build_args()

    reference = earcongen.build_parser().parse_args([])
    # Every attribute the parser knows about is present, so nothing can be
    # missing when a render reads it.
    for key in vars(reference):
        assert hasattr(args, key), key
    assert args.voice == "droid"
    assert Path(args.out).is_relative_to(tmp_path)


def test_generated_family_matches_the_selected_set(window, tmp_path):
    window.base_dir_edit.setText(str(tmp_path))
    window.preset_combo.setCurrentText(params.CUSTOM)
    window.controls["family"].set_value("progress")
    args = window.build_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    written = earcongen.generate_family(args)
    assert [r.spec.slug for r in written] == [
        s.slug for s in earcongen.resolve_family("progress")
    ]
    assert all(r.path.is_file() for r in written)


def test_settings_round_trip(window, tmp_path):
    window.base_dir_edit.setText(str(tmp_path / "chosen"))
    window.preset_combo.setCurrentText(params.CUSTOM)
    window.controls["gain"].set_value(1.25)
    window.subfolder_edit.setText("mine")
    window._subfolder_edited = True
    window._save_settings()

    from gui.app import MainWindow

    reopened = MainWindow()
    try:
        assert reopened.base_dir_edit.text() == str(tmp_path / "chosen")
        assert reopened.controls["gain"].value == 1.25
        assert reopened.subfolder_edit.text() == "mine"
    finally:
        reopened.close()
