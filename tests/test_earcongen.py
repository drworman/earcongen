"""Tests for the generator itself.

The golden-hash test is the important one. Everything else here would
survive a change that quietly altered every sound the tool has ever
produced; that test would not.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import wave
from pathlib import Path

import pytest

import earcongen

ROOT = Path(__file__).resolve().parent.parent


def render(tmp_path: Path, argv: list[str]) -> Path:
    """Run the generator through its own command line."""
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, str(ROOT / "earcongen.py"), "--out", str(out), *argv],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    return out


# --------------------------------------------------------------------------
# Golden output
# --------------------------------------------------------------------------

#: SHA-256 of every file the default invocation produces.
#:
#: These exist so that a change to the synthesis path cannot silently move
#: the sound of the default family. Anyone who deliberately changes the
#: defaults should update these in the same commit and say so in the
#: changelog — a family that shifts under an application already shipping
#: it is a compatibility break, whatever the version number says.
DEFAULT_FAMILY_SHA256 = {
    "earcon01.wav": "053128c695befdef05080faee55ddcde642188cfbe270af58f1a5a85403f85a4",
    "earcon02.wav": "4a376e677590be59c659e7716e790a19d6f565e6a5c384cd79a26b17206f2c47",
    "earcon03.wav": "dc2ab5517a070f264133439c196f918748067f3eb5e26147ae113544f320eaee",
    "earcon04.wav": "9b4209c9eb5dc4d2abdf461c96238e1a120bfb4a81f9eeaa7383e1a78eb976a8",
    "earcon05.wav": "8d878f8b59bf46a9566446ec18497abad6443f198acb5d6e5a96c35c7838e1fc",
    "earcon06.wav": "7c16745fa4412f95d6c487f141352552c36230c2444bca6e8a19f5c69c9a76be",
    "earcon07.wav": "a3279ba2be12b4f286e78de464d08830d158b8e5a7a73365d7dd136fa24d4bbf",
    "earcon08.wav": "a5834bee134ac1acb97042338e05c1200aa3d5aa18035c7de61845aacf739e65",
}


def test_default_family_is_unchanged(tmp_path):
    out = render(tmp_path, [])
    actual = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.glob("*.wav"))
    }
    assert actual == DEFAULT_FAMILY_SHA256


# --------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------

@pytest.mark.parametrize("family", earcongen.FAMILY_NAMES)
def test_every_family_renders(tmp_path, family):
    out = render(tmp_path, ["--family", family])
    specs = earcongen.resolve_family(family)
    assert len(list(out.glob("*.wav"))) == len(specs)


def test_all_family_has_no_duplicate_slugs():
    slugs = [s.slug for s in earcongen.resolve_family("all")]
    assert len(slugs) == len(set(slugs))


def test_core_family_is_the_documented_eight():
    slugs = [s.slug for s in earcongen.resolve_family("core")]
    assert slugs == [f"earcon0{n}" for n in range(1, 9)]


def test_every_contour_referenced_by_a_family_exists():
    for name in earcongen.FAMILY_NAMES:
        for spec in earcongen.resolve_family(name):
            assert spec.contour in earcongen.CONTOURS, (name, spec.slug)


# --------------------------------------------------------------------------
# Note count
# --------------------------------------------------------------------------

def test_note_count_truncates_rather_than_redesigning():
    spec = earcongen.EarconSpec("x", "rise3")
    assert earcongen.capped_contour(spec, 2) == earcongen.CONTOURS["rise3"][:2]
    assert earcongen.capped_contour(spec, None) == earcongen.CONTOURS["rise3"]
    # A cap longer than the contour is not an error, just a no-op.
    assert earcongen.capped_contour(spec, 9) == earcongen.CONTOURS["rise3"]


def test_per_cue_note_count_wins_over_the_flag():
    spec = earcongen.EarconSpec("x", "rise3", note_count=1)
    assert earcongen.capped_contour(spec, 3) == [0]


def test_degenerate_groups_names_collapsed_cues():
    family = earcongen.resolve_family("core")
    groups = earcongen.degenerate_groups(family, 1)
    flattened = {slug for group in groups for slug in group}
    # rise3 and rise_hold share an opening, as do fall2 and fall3.
    assert {"earcon01", "earcon02"} <= flattened
    assert {"earcon04", "earcon05"} <= flattened


def test_no_collapse_without_a_cap():
    family = earcongen.resolve_family("core")
    assert earcongen.degenerate_groups(family, None) == []


def test_capped_family_produces_shorter_files(tmp_path):
    long_out = render(tmp_path / "a", [])
    short_out = render(tmp_path / "b", ["-n", "1"])

    def duration(path: Path) -> float:
        with wave.open(str(path)) as w:
            return w.getnframes() / w.getframerate()

    assert duration(short_out / "earcon01.wav") < duration(long_out / "earcon01.wav")


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------

def test_preset_fills_in_unset_options():
    parser = earcongen.build_parser()
    args = parser.parse_args(["--r2"])
    earcongen.apply_preset(args, parser, ["--r2"])
    assert args.voice == "droid"
    assert args.scale == "kumoi"
    assert args.family == "droid"


def test_explicit_flag_beats_the_preset():
    parser = earcongen.build_parser()
    argv = ["--r2", "--voice", "marimba"]
    args = parser.parse_args(argv)
    earcongen.apply_preset(args, parser, argv)
    assert args.voice == "marimba"
    assert args.scale == "kumoi"  # everything else still comes from the preset


def test_explicit_flag_set_to_its_own_default_still_wins():
    """The reason presets compare against argv rather than against values.

    `--gap-ms 95` is what the r2 preset would set anyway, so a
    value-comparison approach cannot tell it apart from "not given" — and
    would then be free to overwrite it with something else later.
    """
    parser = earcongen.build_parser()
    argv = ["--r2", "--gap-ms", "95"]
    args = parser.parse_args(argv)
    given = earcongen.explicit_dests(parser, argv)
    assert "gap_ms" in given
    earcongen.apply_preset(args, parser, argv)
    assert args.gap_ms == 95.0


def test_preset_voices_exist():
    for name, cfg in earcongen.PRESETS.items():
        assert cfg["voice"] in earcongen.VOICES, name
        assert cfg["scale"] in earcongen.SCALES, name
        assert cfg["family"] in earcongen.FAMILY_NAMES, name


# --------------------------------------------------------------------------
# Modulation
# --------------------------------------------------------------------------

def test_modulation_is_off_on_every_classic_voice():
    """The guarantee behind the unchanged golden hashes."""
    for name in ("bell", "chime", "marimba", "glass", "pluck", "alert",
                 "alarm", "sine"):
        voice = earcongen.VOICES[name]
        assert voice.glide_ms == 0.0
        assert voice.sweep_cents == 0.0
        assert voice.ring_depth == 0.0
        assert voice.vib_cents == 0.0
        assert voice.noise_amt == 0.0


def test_constant_pitch_takes_the_closed_form_path():
    """freq_track returns None when nothing modulates, which is what keeps
    the pre-existing voices bit-identical."""
    import numpy as np

    voice = earcongen.VOICES["chime"]
    t = np.arange(100) / earcongen.SR
    assert earcongen.freq_track(440.0, 400.0, voice, 500.0, 100, t) is None

    droid = earcongen.VOICES["droid"]
    track = earcongen.freq_track(440.0, 400.0, droid, 500.0, 100, t)
    assert track is not None
    # It starts at the previous pitch and arrives at the target.
    assert track[0] < 440.0


def test_droid_output_is_finite_and_bounded(tmp_path):
    """Ring modulation and noise are the two easy ways to produce NaN."""
    import numpy as np

    out = render(tmp_path, ["--r2-full"])
    for path in sorted(out.glob("*.wav")):
        with wave.open(str(path)) as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        assert np.all(np.isfinite(data))
        assert data.size > 0
        assert np.max(np.abs(data)) < 32768


# --------------------------------------------------------------------------
# Spec files
# --------------------------------------------------------------------------

def test_spec_without_note_count_still_loads(tmp_path):
    """Spec files written before the note cap existed must keep working."""
    spec = tmp_path / "legacy.json"
    spec.write_text(
        '[{"slug":"legacy","contour":"rise3","root_offset":0,'
        '"note_ms":null,"gap_ms":null,"gain":1.0,"label":"old"}]'
    )
    out = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, str(ROOT / "earcongen.py"),
         "--spec", str(spec), "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert (out / "legacy.wav").is_file()


def test_dump_spec_follows_the_family_flag():
    import json

    result = subprocess.run(
        [sys.executable, str(ROOT / "earcongen.py"), "--dump-spec",
         "--family", "progress"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr
    slugs = [d["slug"] for d in json.loads(result.stdout)]
    assert slugs == [s.slug for s in earcongen.resolve_family("progress")]


def test_every_voice_has_matching_partial_tables():
    """ratios, amps and decays are zipped strictly, so a voice whose
    tables disagree raises at render time rather than quietly dropping a
    partial. This catches it at import time instead."""
    for name, voice in earcongen.VOICES.items():
        assert len(voice.ratios) == len(voice.amps) == len(voice.decays), name


# --------------------------------------------------------------------------
# Shortening properly: reductions and register separation
# --------------------------------------------------------------------------

def test_every_contour_has_a_character():
    """The character decides which way a nudged cue moves. A contour
    missing from the table would silently be treated as level."""
    assert set(earcongen.CONTOUR_CHARACTER) == set(earcongen.CONTOURS)


def test_every_character_has_a_nudge_direction():
    for character in set(earcongen.CONTOUR_CHARACTER.values()):
        assert character in earcongen.NUDGE_DIRECTION, character


def test_reductions_are_the_length_they_claim():
    for name, table in earcongen.REDUCTIONS.items():
        assert name in earcongen.CONTOURS, name
        for length, degrees in table.items():
            assert len(degrees) == length, (name, length)
            assert length < len(earcongen.CONTOURS[name]), (name, length)


def test_reductions_preserve_direction():
    """A shortened rising cue must still rise, or the cap has changed what
    the cue means rather than only how long it takes to say it."""
    for name, table in earcongen.REDUCTIONS.items():
        character = earcongen.CONTOUR_CHARACTER[name]
        for degrees in table.values():
            if character == "rise":
                assert degrees[-1] > degrees[0], (name, degrees)
            elif character == "fall":
                assert degrees[-1] < degrees[0], (name, degrees)
            elif character == "updown":
                assert max(degrees) > degrees[0], (name, degrees)
            elif character == "downup":
                assert min(degrees) < degrees[0], (name, degrees)


def test_redesign_keeps_meaning_where_truncation_loses_it():
    spec = earcongen.EarconSpec("x", "rise3")
    # Truncation makes a big rise into a small one; the reduction keeps
    # the span and drops the middle note instead.
    assert earcongen.capped_contour(spec, 2) == [0, 2]
    assert earcongen.reduced_contour(spec, 2) == [0, 4]
    # An arch still returns to where it started.
    arch = earcongen.EarconSpec("y", "arch")
    assert earcongen.reduced_contour(arch, 3) == [0, 4, 0]


def test_one_note_is_always_a_single_note():
    for name in earcongen.CONTOURS:
        spec = earcongen.EarconSpec("x", name)
        assert earcongen.reduced_contour(spec, 1) == [0]


def test_uncapped_planning_changes_nothing():
    """The guarantee behind the golden hashes: with no cap, plan_family is
    the identity and cannot move anything."""
    for family in earcongen.FAMILY_NAMES:
        specs = earcongen.resolve_family(family)
        for plan in earcongen.plan_family(specs, None):
            assert plan.degrees == earcongen.CONTOURS[plan.spec.contour]
            assert plan.root_offset == plan.spec.root_offset
            assert not plan.moved


def test_nudged_cues_move_in_their_own_direction():
    """A rising cue that has to give way ends up higher, not merely
    elsewhere."""
    specs = [
        earcongen.EarconSpec("a", "rise2", 0),
        earcongen.EarconSpec("b", "rise2", 0),
        earcongen.EarconSpec("c", "fall2", 0),
        earcongen.EarconSpec("d", "fall2", 0),
    ]
    plans = {p.spec.slug: p for p in earcongen.plan_family(specs, 2)}
    assert plans["a"].root_offset == 0
    assert plans["b"].root_offset > 0
    assert plans["c"].root_offset == 0
    assert plans["d"].root_offset < 0


def test_separation_never_pushes_a_cue_out_of_band():
    """fit_to_range gives up after six octave shifts, so a far enough
    register comes back out of band. Those look distinct and are exactly
    the shrillness the band exists to prevent."""
    pitch = earcongen.PitchContext(523.25, earcongen.SCALES["major_pent"],
                                   480.0, 1150.0)
    for family in earcongen.FAMILY_NAMES:
        specs = earcongen.resolve_family(family)
        for cap in (1, 2, 3):
            for plan in earcongen.plan_family(specs, cap, "redesign", pitch):
                if plan.moved:
                    assert plan.in_band(pitch), (family, cap, plan.spec.slug)


def test_band_capacity_is_the_real_limit():
    """Six distinguishable pitches in the default band, because a
    pentatonic has five per octave and the band is barely wider than
    one. This is why an eight-cue family cannot survive -n 1."""
    pitch = earcongen.PitchContext(523.25, earcongen.SCALES["major_pent"],
                                   480.0, 1150.0)
    assert earcongen.distinct_pitch_capacity(pitch) == 6

    wide = earcongen.PitchContext(523.25, earcongen.SCALES["major_pent"],
                                  300.0, 2400.0)
    assert earcongen.distinct_pitch_capacity(wide) > 8


def test_exhausted_band_is_reported_not_hidden():
    pitch = earcongen.PitchContext(523.25, earcongen.SCALES["major_pent"],
                                   480.0, 1150.0)
    plans = earcongen.plan_family(earcongen.resolve_family("core"), 1,
                                  "redesign", pitch)
    stuck = [p for p in plans if p.unresolved]
    # Eight cues, six pitches: exactly two cannot be given a home.
    assert len(stuck) == 2


def test_redesign_beats_truncation_on_real_audio(tmp_path):
    """The point of the whole exercise, measured on the files themselves
    rather than on the plan."""
    def distinct(argv):
        out = render(tmp_path / "-".join(argv).replace("-", "_"), argv)
        return len({hashlib.sha256(p.read_bytes()).digest()
                    for p in out.glob("*.wav")})

    assert distinct(["-n", "2", "--cap-mode", "truncate"]) == 7
    assert distinct(["-n", "2"]) == 8


@pytest.mark.parametrize("family", ["core", "ui", "system", "message",
                                    "progress", "droid"])
@pytest.mark.parametrize("cap", [2, 3])
def test_every_shipping_family_stays_distinct_when_shortened(tmp_path, family, cap):
    out = render(tmp_path, ["--family", family, "-n", str(cap)])
    files = sorted(out.glob("*.wav"))
    digests = {hashlib.sha256(p.read_bytes()).digest() for p in files}
    assert len(digests) == len(files)


def test_cap_mode_must_be_known():
    with pytest.raises(ValueError):
        earcongen.plan_family(earcongen.resolve_family("core"), 2, "nonsense")
