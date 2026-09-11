"""What the GUI knows about each setting.

Defaults and choices are not written down here. They are read from
``earcongen.build_parser()`` at import time, so the command line stays the
single source of truth: add a voice or move a default in earcongen.py and
the GUI follows without being edited. What lives here is everything the
parser has no opinion about — the slider bounds, the grouping, and the
explanation shown on hover.

On slider bounds
----------------
Related settings deliberately share a range, so that three sliders sitting
above one another can be compared by eye rather than by reading their
numbers. The frequency controls all run 100-4000 Hz; the two note-length
controls both run 40-2000 ms; spacing and ring-out share 0-1200 ms; attack
and release share 0-300 ms. A slider is a coarse instrument in any case —
the spin box beside it accepts values the slider cannot reach precisely,
and both are clamped to the same bounds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import earcongen

#: The parser, built once. Introspecting it is how defaults and choices
#: reach the GUI without being copied.
PARSER = earcongen.build_parser()

#: Every default, as a plain namespace. `parse_args([])` is the documented
#: way to ask argparse what it would do with no arguments at all.
CLI_DEFAULTS = vars(PARSER.parse_args([]))


def choices_for(dest: str) -> list[str]:
    """The permitted values of a choice argument, in the parser's order."""
    for action in PARSER._actions:
        if action.dest == dest and action.choices:
            return list(action.choices)
    return []


@dataclass(frozen=True)
class Param:
    """One setting, and everything needed to draw a control for it."""

    key: str                  # matches the argparse dest exactly
    label: str
    kind: str                 # "float" | "int" | "choice" | "bool"
    tooltip: str
    minimum: float = 0.0
    maximum: float = 1.0
    step: float = 1.0
    decimals: int = 0
    suffix: str = ""
    #: True when None is meaningful — "leave this to the voice". These get
    #: a checkbox that enables the rest of the control.
    optional: bool = False
    optional_label: str = "override"
    #: Shown under the control for choice parameters whose members carry
    #: their own descriptions (voices, families, presets).
    describes: str = ""

    @property
    def default(self):
        return CLI_DEFAULTS.get(self.key)

    @property
    def choices(self) -> list[str]:
        return choices_for(self.key)


@dataclass(frozen=True)
class Group:
    title: str
    blurb: str
    params: list[Param] = field(default_factory=list)


# --------------------------------------------------------------------------
# The settings themselves. Tooltip text is the condensed form of the
# reasoning in README.md and `earcongen.py --notes`; if you change the
# behaviour, change the tooltip in the same commit.
# --------------------------------------------------------------------------

IDENTITY = Group(
    "Family identity",
    "What makes these cues sound like siblings. Change these and the whole "
    "set moves together.",
    [
        Param(
            "voice", "Voice", "choice", describes="voice",
            tooltip=(
                "The timbre: which partials sound above the fundamental, and "
                "how fast each one fades.\n\n"
                "Harmonic voices (chime, pluck) sound pitched and musical. "
                "Inharmonic ones (bell, glass) sound metallic. marimba is the "
                "most legible over background noise without being sharp, "
                "which is usually a timbre problem rather than a volume one.\n\n"
                "droid and droid_wild add ring modulation, pitch glides and "
                "warble. They are the astromech voices and are not restful."
            ),
        ),
        Param(
            "family", "Cue set", "choice", describes="family",
            tooltip=(
                "Which set of cues to generate.\n\n"
                "core is the original eight, with generic slugs that drop "
                "into any project. ui, system, message and progress are "
                "curated for those domains and use namespaced filenames, so "
                "several sets can share one output folder.\n\n"
                "all concatenates every non-droid cue for auditioning. It is "
                "not a set to ship: past about eight cues people stop telling "
                "members apart and start ignoring the whole vocabulary."
            ),
        ),
        Param(
            "scale", "Scale", "choice",
            tooltip=(
                "The pitch set every note is drawn from.\n\n"
                "The pentatonics are a practical choice rather than an "
                "aesthetic one: two cues will eventually fire within a second "
                "of each other, and any two notes drawn from a pentatonic "
                "sound fine together.\n\n"
                "minor_pent reads as more serious than major_pent without "
                "being mournful. hirajoshi is ceremonial. whole_tone has no "
                "tonal centre, which suits products wanting neutrality.\n\n"
                "chromatic discards the consonance guarantee entirely. It is "
                "here for the unleashed droid preset, where speech-like "
                "arbitrariness is the point."
            ),
        ),
        Param(
            "root", "Root pitch", "float", minimum=100.0, maximum=4000.0,
            step=1.0, decimals=2, suffix=" Hz",
            tooltip=(
                "The reference pitch every scale degree is measured from. "
                "The default is C5, 523.25 Hz.\n\n"
                "Raising it lifts the whole family together, preserving the "
                "intervals that make each motif recognisable. Useful "
                "reference pitches: G4 392.00, A4 440.00, C5 523.25, "
                "D5 587.33, E5 659.25, G5 783.99."
            ),
        ),
        Param(
            "floor", "Band floor", "float", minimum=100.0, maximum=4000.0,
            step=1.0, decimals=1, suffix=" Hz",
            tooltip=(
                "The lowest fundamental allowed. A motif that falls below it "
                "is transposed up by whole octaves until it fits, as a unit, "
                "so its interval structure survives.\n\n"
                "The default of 480 Hz sits above most low-frequency ambient "
                "noise — engines, HVAC, traffic, room tone — so cues stay "
                "legible without being loud."
            ),
        ),
        Param(
            "ceiling", "Band ceiling", "float", minimum=100.0, maximum=4000.0,
            step=1.0, decimals=1, suffix=" Hz",
            tooltip=(
                "The highest fundamental allowed, applied the same way as the "
                "floor.\n\n"
                "The default of 1150 Hz keeps fundamentals below the 2-4 kHz "
                "band where the ear is most sensitive and where alarms and "
                "sirens live. Cues can be clearly audible there without being "
                "shrill. Raising the ceiling into that band is what makes a "
                "notification sound tiring over months."
            ),
        ),
        Param(
            "note_count", "Cap notes at", "int", minimum=0, maximum=8,
            step=1, suffix=" notes",
            tooltip=(
                "Cap every motif at this many notes. Zero leaves each contour "
                "at its natural length.\n\n"
                "How the shortening is done is set below. Either way, a "
                "single-note cue is distinguishable by register and timbre "
                "alone, both of which survive noise and cheap speakers badly, "
                "and it carries none of the rising/falling meaning that makes "
                "a set learnable. Use 1 when something forces your hand, not "
                "because shorter looks tidier.\n\n"
                "The number of one-note cues a family can hold is fixed by "
                "the band and the scale, not by cleverness: the default "
                "480-1150 Hz on a pentatonic gives six distinguishable "
                "pitches. Asking for eight will say so."
            ),
        ),
        Param(
            "cap_mode", "When shortening", "choice",
            tooltip=(
                "How a note cap shortens each motif.\n\n"
                "redesign swaps in a purpose-built shape of the requested "
                "length that still means what the original meant -- a big "
                "rise stays a big rise, an arch still returns to where it "
                "started -- and then moves any cues that still collide into "
                "different registers, upward for a rising cue and downward "
                "for a falling one.\n\n"
                "truncate simply cuts each contour short. It keeps every "
                "cue's opening exactly as designed, at the cost of making "
                "cues that differ only after the cut point identical. That "
                "is sometimes what you want; it is never a surprise, because "
                "the status line names the casualties."
            ),
        ),
    ],
)

TIMING = Group(
    "Timing and envelope",
    "How long each note lasts and how the notes are spaced. Attack time is "
    "the single biggest lever on whether a cue is pleasant.",
    [
        Param(
            "note_ms", "Note length", "float", minimum=40.0, maximum=2000.0,
            step=10.0, decimals=1, suffix=" ms", optional=True,
            optional_label="use the voice's own decay",
            tooltip=(
                "The decay time of each note — not a truncation point. Notes "
                "always render through to the end of the buffer, so nothing "
                "is ever cut off mid-oscillation.\n\n"
                "Lower makes notes tighter and more businesslike; higher "
                "makes them ring. Left unticked, each voice uses its own "
                "decay, which is part of what gives it character."
            ),
        ),
        Param(
            "gap_ms", "Note spacing", "float", minimum=0.0, maximum=1200.0,
            step=5.0, decimals=1, suffix=" ms",
            tooltip=(
                "Onset-to-onset spacing between notes in a motif.\n\n"
                "Below the note length, notes overlap and blend, which is "
                "what a real instrument does and generally sounds better. "
                "Above it, notes are separated by silence, which reads as "
                "more deliberate and more urgent."
            ),
        ),
        Param(
            "tail_ms", "Ring-out", "float", minimum=0.0, maximum=1200.0,
            step=10.0, decimals=1, suffix=" ms",
            tooltip=(
                "How much time is appended after the last note begins.\n\n"
                "This is genuine ring-out, not padding: the notes are still "
                "decaying through it. Too little and the file ends while the "
                "sound is still audible, which the release below then has to "
                "rescue."
            ),
        ),
        Param(
            "attack_ms", "Attack", "float", minimum=0.0, maximum=300.0,
            step=1.0, decimals=1, suffix=" ms", optional=True,
            optional_label="use the voice's own attack",
            tooltip=(
                "How long each note takes to reach full amplitude. This is "
                "the biggest single lever and the one people reach for last.\n\n"
                "Under about 5 ms the onset reads as a click and produces a "
                "small startle response every time. 15-40 ms rising into a "
                "long decay reads as a struck object — a bell, a glass, a "
                "marimba bar. You notice it just as reliably and nothing "
                "flinches.\n\n"
                "If a cue irritates you, raise this before touching anything "
                "else."
            ),
        ),
        Param(
            "release_ms", "Release", "float", minimum=0.0, maximum=300.0,
            step=1.0, decimals=1, suffix=" ms",
            tooltip=(
                "A raised-cosine fade applied to the very end of the file, "
                "bringing any residual ring-out to true zero.\n\n"
                "It should not normally need changing. Raise it if you hear a "
                "click at the end of a file; lower it only for a deliberately "
                "abrupt ending, and check the result with earconcheck.py."
            ),
        ),
        Param(
            "decay_ms", "Voice decay", "float", minimum=40.0, maximum=2000.0,
            step=10.0, decimals=1, suffix=" ms", optional=True,
            optional_label="use the voice's own decay",
            tooltip=(
                "Overrides the decay time built into the chosen voice, which "
                "also becomes the default note length.\n\n"
                "Distinct from Note length above: this changes the voice "
                "itself, so it also moves the reference the note length falls "
                "back to when that is left unticked."
            ),
        ),
    ],
)

CHARACTER = Group(
    "Modulation",
    "Pitch movement within and between notes. Zero on every classic voice; "
    "these are what make the droid voices sound like a machine talking.",
    [
        Param(
            "glide_ms", "Glide", "float", minimum=0.0, maximum=300.0,
            step=1.0, decimals=1, suffix=" ms", optional=True,
            optional_label="use the voice's own glide",
            tooltip=(
                "Portamento: how long each note takes to slide from the "
                "previous note's pitch to its own.\n\n"
                "Interpolated in log-frequency space and eased, so it sounds "
                "like a voice bending rather than a machine sweeping. Zero on "
                "every classic voice; around 45 ms on droid.\n\n"
                "Longer than the note spacing means a note never quite "
                "arrives at its pitch before the next begins, which is "
                "expressive and destroys contour legibility."
            ),
        ),
        Param(
            "ring_depth", "Ring modulation", "float", minimum=0.0,
            maximum=1.0, step=0.01, decimals=2, optional=True,
            optional_label="use the voice's own ring mix",
            tooltip=(
                "How much ring-modulated signal is mixed in, from 0 (none) "
                "to 1 (fully modulated).\n\n"
                "A ring modulator multiplies the note by another tone, "
                "placing sum and difference frequencies where no harmonic "
                "series would put them. That is most of what reads as "
                "'machine attempting speech' rather than 'instrument'.\n\n"
                "Above about 0.6 it turns harsh quickly. It also drives the "
                "signal through zero at the difference frequency by design, "
                "so check this output with earconcheck.py --modulated."
            ),
        ),
        Param(
            "vib_cents", "Warble depth", "float", minimum=0.0, maximum=200.0,
            step=1.0, decimals=1, suffix=" cents", optional=True,
            optional_label="use the voice's own warble",
            tooltip=(
                "How far the pitch wavers, in cents — hundredths of a "
                "semitone. The rate is fixed per voice.\n\n"
                "Around 16 cents on droid is a slight unsteadiness. The 45 "
                "cents on droid_wild is unmistakable. Above roughly 100 the "
                "sense of a definite pitch starts to break down, which is "
                "occasionally what you want."
            ),
        ),
    ],
)

LOUDNESS = Group(
    "Loudness",
    "Normalise the family here, then let the application provide a single "
    "user-facing volume control.",
    [
        Param(
            "target_rms", "Target level", "float", minimum=0.01, maximum=0.4,
            step=0.005, decimals=3,
            tooltip=(
                "The A-weighted RMS every cue is normalised to.\n\n"
                "A-weighting matters more than it sounds like it should: a "
                "1 kHz tone at the same peak amplitude as a 500 Hz tone is "
                "noticeably louder to the ear. Without weighting, a family "
                "sounds unbalanced however carefully each cue was designed."
            ),
        ),
        Param(
            "gain", "Family gain", "float", minimum=0.1, maximum=2.0,
            step=0.05, decimals=2, suffix="x",
            tooltip=(
                "A multiplier applied to the target level across the whole "
                "family, for making one theme louder or quieter than another "
                "without changing the balance within it.\n\n"
                "Per-cue loudness is a spec-file setting, not a control here, "
                "and should only be used to make a cue deliberately more or "
                "less prominent — never to fix a balance problem, which the "
                "A-weighting has already handled."
            ),
        ),
        Param(
            "peak", "Peak ceiling", "float", minimum=0.1, maximum=1.0,
            step=0.01, decimals=2,
            tooltip=(
                "A hard limit applied after normalisation.\n\n"
                "The headroom exists because these files get mixed with other "
                "audio downstream; generating at 0.99 leaves nothing for the "
                "host. A cue that hits this ceiling ends up quieter than the "
                "target level, which earconcheck.py will report as a loudness "
                "spread."
            ),
        ),
    ],
)

OUTPUT = Group(
    "Output",
    "Where the files go and what format they take.",
    [
        Param(
            "stereo", "Write dual-mono", "bool",
            tooltip=(
                "Write two identical channels instead of one.\n\n"
                "The audio is unchanged and the file is twice the size. Some "
                "hosts and embedded players refuse mono files outright, which "
                "is the only reason to turn this on."
            ),
        ),
    ],
)

GROUPS: list[Group] = [IDENTITY, TIMING, CHARACTER, LOUDNESS, OUTPUT]

#: Flat lookup, for applying presets and reading the whole form back.
ALL_PARAMS: dict[str, Param] = {
    p.key: p for group in GROUPS for p in group.params
}

#: Shown in the preset dropdown above the real presets.
CUSTOM = "Custom"

PRESET_BLURBS: dict[str, str] = {
    name: cfg.get("blurb", "") for name, cfg in earcongen.PRESETS.items()
}

VOICE_BLURBS: dict[str, str] = {
    name: voice.blurb for name, voice in earcongen.VOICES.items()
}

FAMILY_BLURBS: dict[str, str] = {}
for _name in earcongen.FAMILY_NAMES:
    _specs = earcongen.resolve_family(_name)
    _note = {
        "core": "the original eight, generic slugs",
        "all": "everything non-droid; for auditioning, not shipping",
    }.get(_name, ", ".join(s.label.split(" / ")[0] for s in _specs[:3]) + ", ...")
    FAMILY_BLURBS[_name] = f"{len(_specs)} cues -- {_note}"


def preset_values(name: str) -> dict:
    """A preset's settings, restricted to those the GUI has a control for.

    Presets also carry `out`, which the GUI deliberately ignores: the user
    chose an output directory and a preset should not move it. The preset
    name becomes the subfolder instead.
    """
    cfg = earcongen.PRESETS[name]
    return {k: v for k, v in cfg.items() if k in ALL_PARAMS}


def default_values() -> dict:
    """Every GUI-controlled setting at its command-line default."""
    return {key: CLI_DEFAULTS.get(key) for key in ALL_PARAMS}
