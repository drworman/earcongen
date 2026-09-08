#!/usr/bin/env python3
"""
earcongen -- generate a related-but-distinguishable family of earcons.

An "earcon" is a short, non-speech audio cue that stands in for a message:
the sound a phone makes for a new message, the chime a car makes when you
leave the lights on. Good ones are learnable, unobtrusive, and mutually
distinguishable. Most software ships bad ones, because they are usually
chosen one at a time rather than designed as a set.

This tool designs them as a set. You pick a timbre, a scale and a
frequency band; it emits a family of cues that share an identity but stay
individually recognisable, normalised so they sound equally loud.

Design constraints baked in (see --notes, or README.md, for the reasoning):
  * soft attack, exponential decay -- struck objects, not beeps
  * fundamentals kept out of the 2-4 kHz irritation band by default
  * every note drawn from one pentatonic scale, so cues that overlap in
    time never clash
  * motifs of 2-3 notes rather than single tones, so cues are
    distinguishable by contour rather than by pitch alone
  * A-weighted loudness normalisation, so cues at different pitches
    actually sound equally loud
  * nothing loops, and most cues land under a second

Requires numpy only. Writes 16-bit mono WAV.

Quick start:
    ./earcongen.py --voice chime --out audio/chime
    ./earcongen.py --voice bell --scale minor_pent --out audio/bell
    ./earcongen.py --voice marimba --floor 400 --ceiling 900 --out audio/marimba
    ./earcongen.py --list-voices
    ./earcongen.py --notes
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

SR = 44100

# ---------------------------------------------------------------------------
# Voices: partial structure + default envelope character.
#
# ratios : frequency multipliers of the fundamental
# amps   : relative amplitude of each partial
# decays : per-partial decay multiplier (>1 = decays faster than fundamental)
# ---------------------------------------------------------------------------


@dataclass
class Voice:
    name: str
    ratios: list[float]
    amps: list[float]
    decays: list[float]
    attack_ms: float = 20.0
    decay_ms: float = 520.0
    fm_index: float = 0.0          # >0 enables FM colouring
    fm_ratio: float = 2.0
    fm_decay: float = 0.35         # index falls off this fast (fraction of decay)
    blurb: str = ""


VOICES: dict[str, Voice] = {
    # Inharmonic partials, long tail. The classic "notification" sound.
    "bell": Voice(
        "bell",
        ratios=[0.56, 1.00, 1.19, 1.71, 2.00, 2.74, 3.00],
        amps=[0.35, 1.00, 0.55, 0.30, 0.22, 0.12, 0.08],
        decays=[0.7, 1.0, 1.3, 1.8, 2.0, 2.8, 3.4],
        attack_ms=8.0,
        decay_ms=900.0,
        blurb="inharmonic, long tail, unmistakably a bell",
    ),
    # Harmonic and soft. Least intrusive of the set.
    "chime": Voice(
        "chime",
        ratios=[1.00, 2.00, 3.00, 4.20],
        amps=[1.00, 0.38, 0.16, 0.06],
        decays=[1.0, 1.5, 2.2, 3.0],
        attack_ms=22.0,
        decay_ms=620.0,
        blurb="soft harmonic, gentle -- good default for low-urgency alerts",
    ),
    # Real marimba bar partials (1 : 3.9 : 9.2). Woody, fast, very legible.
    "marimba": Voice(
        "marimba",
        ratios=[1.00, 3.90, 9.20],
        amps=[1.00, 0.28, 0.08],
        decays=[1.0, 2.6, 4.5],
        attack_ms=5.0,
        decay_ms=300.0,
        blurb="woody, short, cuts through engine noise without being sharp",
    ),
    # Very long decay, sparse high partials. Ambient.
    "glass": Voice(
        "glass",
        ratios=[1.00, 2.76, 5.40, 8.93],
        amps=[1.00, 0.30, 0.10, 0.04],
        decays=[0.8, 1.4, 2.0, 2.6],
        attack_ms=35.0,
        decay_ms=1300.0,
        blurb="airy, very long tail -- atmospheric, easy to miss under noise",
    ),
    # 1/n harmonic series, quick decay.
    "pluck": Voice(
        "pluck",
        ratios=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        amps=[1.0, 0.50, 0.33, 0.25, 0.20, 0.16],
        decays=[1.0, 1.4, 1.8, 2.2, 2.6, 3.0],
        attack_ms=3.0,
        decay_ms=260.0,
        blurb="string-like, tight, unobtrusive",
    ),
    # FM colouring, brighter onset that mellows. More presence than chime.
    "alert": Voice(
        "alert",
        ratios=[1.00, 2.00],
        amps=[1.00, 0.25],
        decays=[1.0, 1.8],
        attack_ms=12.0,
        decay_ms=420.0,
        fm_index=2.2,
        fm_ratio=2.0,
        fm_decay=0.30,
        blurb="FM sheen, more presence -- for things you must not miss",
    ),
    # Brightest / fastest. Still enveloped, so not a piezo beep.
    "alarm": Voice(
        "alarm",
        ratios=[1.00, 2.00, 3.00, 4.00],
        amps=[1.00, 0.65, 0.40, 0.22],
        decays=[1.0, 1.2, 1.5, 1.9],
        attack_ms=4.0,
        decay_ms=340.0,
        fm_index=1.2,
        fm_ratio=3.0,
        fm_decay=0.25,
        blurb="urgent, bright -- use sparingly, this is the one that nags",
    ),
    # Reference tone. Deliberately plain.
    "sine": Voice(
        "sine",
        ratios=[1.00],
        amps=[1.00],
        decays=[1.0],
        attack_ms=25.0,
        decay_ms=500.0,
        blurb="pure sine reference -- synthetic, fatiguing, here for A/B only",
    ),
}

# ---------------------------------------------------------------------------
# Scales, expressed as semitone offsets within an octave.
# Pentatonics are used because any two notes drawn from one sound fine
# together -- which matters when two alerts fire within a second.
# ---------------------------------------------------------------------------

SCALES: dict[str, list[int]] = {
    "major_pent": [0, 2, 4, 7, 9],
    "minor_pent": [0, 3, 5, 7, 10],
    "hirajoshi": [0, 2, 3, 7, 8],
    "kumoi": [0, 2, 3, 7, 9],
    "whole_tone": [0, 2, 4, 6, 8, 10],
}

# ---------------------------------------------------------------------------
# Contours. Degree offsets within the chosen scale.
# Semantics that hold up in practice:
#   rising  -> opportunity / permission granted
#   falling -> attention / state degrading
#   level   -> neutral status
# ---------------------------------------------------------------------------

CONTOURS: dict[str, list[int]] = {
    "rise2": [0, 2],
    "rise3": [0, 2, 4],
    "fall2": [0, -2],
    "fall3": [0, -2, -4],
    "level2": [0, 0],
    "level3": [0, 0, 0],
    "updown": [0, 2, 0],
    "downup": [0, -2, 0],
    "leap_up": [0, 4],
    "leap_down": [0, -4],
    "rise_hold": [0, 1, 1],
    "single": [0],
}


@dataclass
class EarconSpec:
    """One earcon in the family."""
    slug: str
    contour: str
    root_offset: int = 0       # scale degrees; shifts this motif's register
    note_ms: float | None = None
    gap_ms: float | None = None
    gain: float = 1.0          # relative loudness within the family
    label: str = ""


# The starting set. Edit freely, or supply your own via --spec -- this is
# the point of the tool. Slugs are deliberately generic so the output drops
# into any project; the labels describe the *shape* each cue implies, not
# any particular application's events.
#
# Two cues that share an opening and differ only in resolution (01 and 02
# below) read as related without being confusable. That is the usual way
# to handle two events in the same category.
DEFAULT_FAMILY: list[EarconSpec] = [
    EarconSpec("earcon01", "rise3", 0, label="positive / opportunity found"),
    EarconSpec("earcon02", "rise_hold", 0, label="positive, related to 01"),
    EarconSpec("earcon03", "updown", 2, label="milestone / threshold reached"),
    EarconSpec("earcon04", "fall2", -2, label="attention / state degrading"),
    EarconSpec("earcon05", "fall3", -2, label="attention, more urgent than 04"),
    EarconSpec("earcon06", "leap_up", 1, label="permission granted / now clear"),
    EarconSpec("earcon07", "downup", -1, label="resource running low"),
    EarconSpec("earcon08", "level2", 3, label="neutral status / acknowledgement"),
]


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def a_weight_gain(freqs: np.ndarray) -> np.ndarray:
    """ISO A-weighting, linear gain per frequency."""
    f = np.maximum(freqs, 1e-6)
    f2 = f ** 2
    num = (12194.0 ** 2) * (f2 ** 2)
    den = (
        (f2 + 20.6 ** 2)
        * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
        * (f2 + 12194.0 ** 2)
    )
    ra = num / den
    return ra * (10 ** (2.00 / 20.0))


def a_weighted_rms(sig: np.ndarray) -> float:
    """RMS after A-weighting, computed in the frequency domain."""
    if sig.size == 0:
        return 0.0
    spec = np.fft.rfft(sig)
    freqs = np.fft.rfftfreq(sig.size, 1.0 / SR)
    w = a_weight_gain(freqs)
    weighted = spec * w
    # Parseval, accounting for the one-sided spectrum.
    energy = np.sum(np.abs(weighted) ** 2) * 2.0 / (sig.size ** 2)
    return float(np.sqrt(max(energy, 0.0)))


def envelope(n: int, attack_ms: float, decay_ms: float, decay_mult: float) -> np.ndarray:
    """Raised-cosine attack into exponential decay.

    The attack shape is what separates a bell from a click. Below ~5 ms
    the onset reads as a transient and the ear flinches.

    `n` is the render length, which is deliberately NOT the note length --
    the envelope must be allowed to decay naturally past the nominal note
    duration. Truncating it mid-oscillation is a click, however quiet the
    signal is at the truncation point.
    """
    t = np.arange(n) / SR
    atk_n = max(1, int(SR * attack_ms / 1000.0))
    atk_n = min(atk_n, n)

    env = np.ones(n)
    # Raised cosine rise -- no discontinuity in the first derivative.
    rise = 0.5 * (1.0 - np.cos(np.pi * np.arange(atk_n) / atk_n))
    env[:atk_n] = rise

    tau = (decay_ms / 1000.0) / (3.0 * decay_mult)
    decay_t = np.zeros(n)
    decay_t[atk_n:] = t[atk_n:] - t[atk_n]
    env *= np.exp(-decay_t / max(tau, 1e-5))
    return env


def render_note(freq: float, voice: Voice, decay_ms: float, render_n: int) -> np.ndarray:
    """Render one note for `render_n` samples, decaying with time constant
    derived from `decay_ms`. Render length and decay length are separate:
    the caller renders to the end of the buffer so nothing is cut off."""
    if render_n <= 0:
        return np.zeros(0)
    t = np.arange(render_n) / SR
    out = np.zeros(render_n)

    for ratio, amp, dec in zip(voice.ratios, voice.amps, voice.decays):
        pf = freq * ratio
        if pf >= SR / 2.0:      # skip anything that would alias
            continue
        phase = 2.0 * np.pi * pf * t

        if voice.fm_index > 0.0:
            mod_env = np.exp(-t / max(voice.fm_decay * decay_ms / 1000.0, 1e-5))
            phase = phase + voice.fm_index * mod_env * np.sin(
                2.0 * np.pi * pf * voice.fm_ratio * t
            )

        env = envelope(render_n, voice.attack_ms, decay_ms, dec)
        out += amp * env * np.sin(phase)

    return out


def scale_freq(root_hz: float, scale: list[int], degree: int) -> float:
    """Map a (possibly negative, possibly out-of-octave) scale degree to Hz."""
    span = len(scale)
    octave = degree // span
    idx = degree % span
    semis = scale[idx] + 12 * octave
    return root_hz * (2.0 ** (semis / 12.0))


def fit_to_range(freqs: list[float], floor: float, ceiling: float) -> list[float]:
    """Transpose the whole motif by octaves until it fits the band.

    Transposing as a unit preserves the interval structure, which is what
    makes the motif recognisable.
    """
    if not freqs:
        return freqs
    f = list(freqs)
    for _ in range(6):
        if max(f) > ceiling:
            f = [x / 2.0 for x in f]
        elif min(f) < floor:
            f = [x * 2.0 for x in f]
        else:
            break
    return f


def render_earcon(
    spec: EarconSpec,
    voice: Voice,
    scale: list[int],
    root_hz: float,
    floor: float,
    ceiling: float,
    note_ms: float,
    gap_ms: float,
    target_rms: float,
    peak_ceiling: float,
    tail_ms: float,
    release_ms: float,
) -> np.ndarray:
    contour = CONTOURS[spec.contour]
    nm = spec.note_ms if spec.note_ms is not None else note_ms
    gm = spec.gap_ms if spec.gap_ms is not None else gap_ms

    degrees = [spec.root_offset + d for d in contour]
    freqs = [scale_freq(root_hz, scale, d) for d in degrees]
    freqs = fit_to_range(freqs, floor, ceiling)

    step_n = int(SR * gm / 1000.0)
    note_n = int(SR * nm / 1000.0)
    tail_n = int(SR * tail_ms / 1000.0)
    total = step_n * (len(freqs) - 1) + note_n + tail_n

    buf = np.zeros(total)
    for i, f in enumerate(freqs):
        start = i * step_n
        # Render each note all the way to the end of the buffer. The tail
        # is genuine ring-out, not appended silence, so no note is ever
        # cut off mid-oscillation.
        buf[start:] += render_note(f, voice, nm, total - start)

    # A-weighted normalisation: this is why a 500 Hz and a 1 kHz earcon
    # in the same family actually sound equally loud.
    rms = a_weighted_rms(buf)
    if rms > 1e-9:
        buf *= (target_rms / rms)
    buf *= spec.gain

    peak = float(np.max(np.abs(buf))) if buf.size else 0.0
    if peak > peak_ceiling:
        buf *= (peak_ceiling / peak)

    # Raised-cosine release on the summed buffer. Continuous in value AND
    # first derivative, unlike a linear fade -- the residual ring-out is
    # brought to true zero without a step. This is the fix for the
    # end-of-file pop; a linear ramp here is audible, a cosine one is not.
    rel_n = min(int(SR * release_ms / 1000.0), buf.size)
    if rel_n > 1:
        buf[-rel_n:] *= 0.5 * (1.0 + np.cos(np.pi * np.arange(rel_n) / (rel_n - 1)))

    return buf


def write_wav(path: Path, sig: np.ndarray, stereo: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(sig, -1.0, 1.0)
    data = (pcm * 32767.0).astype("<i2")
    if stereo:
        data = np.repeat(data[:, None], 2, axis=1).reshape(-1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2 if stereo else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def play(path: Path) -> None:
    """Best-effort local audition. Falls through quietly if nothing is present."""
    if sys.platform == "darwin" and shutil.which("afplay"):
        subprocess.run(["afplay", str(path)], check=False)
        return
    if sys.platform.startswith("win"):
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return
        except Exception:
            pass
    for cmd in (["paplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd + [str(path)], check=False)
            return
    print(f"  (no player found -- listen to {path} yourself)", file=sys.stderr)


NOTES = """\
Why the defaults are what they are
----------------------------------

Attack time is the biggest single lever. Under ~5 ms the onset reads as a
click and the listener flinches; 15-40 ms with a long exponential decay
reads as a struck object. That difference is most of what separates a
pleasant earcon from a piezo beep, more than pitch or timbre.

Fundamentals default to 480-1150 Hz. The 2-4 kHz band is where the ear is
most sensitive and where alarms and sirens live -- staying below it means
the tone can be clearly audible without being shrill. It is also above
most low-frequency ambient noise -- engines, HVAC, traffic, room tone --
so it stays legible without being loud.

Every note comes from one pentatonic scale. This is a practical decision,
not an aesthetic one: two alerts will eventually fire within a second of
each other, and any two notes drawn from a pentatonic sound fine together.
Anything else risks an accidental dissonance you cannot design around.

Motifs of 2-3 notes are far more distinguishable than single tones, and
carry meaning through contour: rising for opportunity or permission,
falling for attention or a degrading state, level for neutral status.
Learn the vocabulary once and you stop needing to look.

A-weighted normalisation matters more than it sounds like it should. A
1 kHz tone at the same peak amplitude as a 500 Hz tone is noticeably
louder to the ear. Without weighting, a family sounds unbalanced no matter
how carefully each tone was designed individually.

Nothing loops. Most cues land under a second; the long-tailed voices
(bell, glass) run longer by design, and glass at its defaults is around
two seconds. Looping is what makes alarms unbearable -- a cue that repeats
until acknowledged turns a notification into a demand, and people respond
by disabling the whole system rather than the one cue.

Things worth trying
-------------------

  --voice marimba --note-ms 190 --gap-ms 130     tight and businesslike
  --voice bell --scale hirajoshi --gap-ms 220    more ceremonial
  --voice chime --floor 380 --ceiling 800        warmer, sits lower
  --voice alert --gain 1.15                      more presence for danger
  --root 587.33                                  shift the whole family up

If a tone is annoying, raise --attack-ms before touching anything else.
If it is hard to hear over background noise, try --voice marimba before
raising the gain -- legibility is usually a timbre problem, not a volume
problem.
"""


def main() -> int:
    p = argparse.ArgumentParser(
        description="Generate a family of related earcons.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", default="audio/chime", help="output directory")
    p.add_argument("--voice", default="chime", choices=sorted(VOICES), help="timbre")
    p.add_argument("--scale", default="major_pent", choices=sorted(SCALES))
    p.add_argument("--root", type=float, default=523.25,
                   help="root frequency in Hz (default C5 523.25)")
    p.add_argument("--floor", type=float, default=480.0,
                   help="lowest allowed fundamental (Hz)")
    p.add_argument("--ceiling", type=float, default=1150.0,
                   help="highest allowed fundamental (Hz)")
    p.add_argument("--note-ms", type=float, default=None,
                   help="note decay length in ms; defaults to the voice's own "
                        "decay time. This sets the decay, not a truncation point")
    p.add_argument("--gap-ms", type=float, default=150.0,
                   help="onset-to-onset spacing between notes in a motif")
    p.add_argument("--tail-ms", type=float, default=250.0,
                   help="ring-out appended after the last note onset")
    p.add_argument("--release-ms", type=float, default=60.0,
                   help="raised-cosine release at end of file; raise if you "
                        "still hear a click, lower for a more abrupt ending")
    p.add_argument("--attack-ms", type=float, default=None,
                   help="override the voice's attack time")
    p.add_argument("--decay-ms", type=float, default=None,
                   help="override the voice's decay time")
    p.add_argument("--gain", type=float, default=1.0,
                   help="family-wide loudness multiplier")
    p.add_argument("--target-rms", type=float, default=0.11,
                   help="A-weighted RMS normalisation target")
    p.add_argument("--peak", type=float, default=0.80, help="peak ceiling")
    p.add_argument("--stereo", action="store_true", help="write dual-mono")
    p.add_argument("--play", action="store_true", help="audition each after writing")
    p.add_argument("--spec", help="JSON file describing the family (see --dump-spec)")
    p.add_argument("--dump-spec", action="store_true",
                   help="print the default family as JSON and exit")
    p.add_argument("--list-voices", action="store_true")
    p.add_argument("--list-contours", action="store_true")
    p.add_argument("--notes", action="store_true",
                   help="print the design reasoning behind the defaults")
    args = p.parse_args()

    if args.notes:
        print(NOTES)
        return 0

    if args.list_voices:
        for name in sorted(VOICES):
            v = VOICES[name]
            print(f"  {name:<9} atk {v.attack_ms:>5.1f}ms  dec {v.decay_ms:>6.1f}ms   {v.blurb}")
        return 0

    if args.list_contours:
        for name, c in CONTOURS.items():
            print(f"  {name:<11} {c}")
        return 0

    if args.dump_spec:
        print(json.dumps([asdict(s) for s in DEFAULT_FAMILY], indent=2))
        return 0

    if args.spec:
        raw = json.loads(Path(args.spec).read_text())
        family = [EarconSpec(**d) for d in raw]
    else:
        family = DEFAULT_FAMILY

    voice = VOICES[args.voice]
    if args.attack_ms is not None or args.decay_ms is not None:
        voice = Voice(**{**asdict(voice),
                         "attack_ms": args.attack_ms if args.attack_ms is not None else voice.attack_ms,
                         "decay_ms": args.decay_ms if args.decay_ms is not None else voice.decay_ms})

    note_ms = args.note_ms if args.note_ms is not None else voice.decay_ms
    scale = SCALES[args.scale]
    outdir = Path(args.out)

    print(f"voice={args.voice}  scale={args.scale}  root={args.root:.2f}Hz  "
          f"band={args.floor:.0f}-{args.ceiling:.0f}Hz -> {outdir}/")

    for spec in family:
        sig = render_earcon(
            spec, voice, scale, args.root, args.floor, args.ceiling,
            note_ms, args.gap_ms, args.target_rms * args.gain,
            args.peak, args.tail_ms, args.release_ms,
        )
        path = outdir / f"{spec.slug}.wav"
        write_wav(path, sig, stereo=args.stereo)
        dur = sig.size / SR
        print(f"  {path}  {dur:5.2f}s  {spec.contour:<11} {spec.label}")
        if args.play:
            play(path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
