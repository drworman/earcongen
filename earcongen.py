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
    distinguishable by contour rather than by pitch alone (--note-count
    shortens them when you need it, at a cost the tool will tell you about)
  * A-weighted loudness normalisation, so cues at different pitches
    actually sound equally loud
  * nothing loops, and most cues land under a second

Requires numpy only. Writes 16-bit mono WAV.

Quick start:
    ./earcongen.py --voice chime --out audio/chime
    ./earcongen.py --voice bell --scale minor_pent --out audio/bell
    ./earcongen.py --voice marimba --floor 400 --ceiling 900 --out audio/marimba
    ./earcongen.py --family ui --voice marimba --out audio/ui
    ./earcongen.py -n 2 --out audio/short
    ./earcongen.py --r2 --out audio/r2
    ./earcongen.py --list-voices
    ./earcongen.py --list-families
    ./earcongen.py --notes
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass, asdict
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
    # --- modulation: off by default, so every pre-existing voice is
    # --- bit-for-bit unchanged. These are what make a droid a droid.
    glide_ms: float = 0.0          # portamento into each note from the previous pitch
    sweep_cents: float = 0.0       # per-note bend over the note's decay; -/+
    vib_hz: float = 0.0            # warble rate
    vib_cents: float = 0.0         # warble depth
    ring_ratio: float = 0.0        # ring modulator freq as a ratio of the fundamental
    ring_depth: float = 0.0        # 0..1 wet mix; inharmonic, metallic
    noise_amt: float = 0.0         # servo/breath noise mixed under the partials
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
    # Astromech, house-trained. Ring modulation at a non-integer ratio gives
    # the metallic burble; a short glide between notes gives the speech-like
    # portamento. Kept mild enough to still pass as a notification sound.
    "droid": Voice(
        "droid",
        ratios=[1.00, 2.00, 3.02],
        amps=[1.00, 0.30, 0.10],
        decays=[1.0, 1.6, 2.4],
        attack_ms=9.0,
        decay_ms=230.0,
        glide_ms=45.0,
        vib_hz=6.0,
        vib_cents=16.0,
        ring_ratio=1.41,
        ring_depth=0.30,
        blurb="astromech burble -- ring-modded, glides between notes",
    ),
    # The unleashed version. Faster, wider warble, deeper ring mod, a touch
    # of servo noise, and a per-note upward bend. Not a well-behaved earcon.
    "droid_wild": Voice(
        "droid_wild",
        ratios=[1.00, 2.00],
        amps=[1.00, 0.42],
        decays=[1.0, 1.5],
        attack_ms=4.0,
        decay_ms=150.0,
        glide_ms=26.0,
        sweep_cents=140.0,
        vib_hz=11.0,
        vib_cents=45.0,
        ring_ratio=2.73,
        ring_depth=0.55,
        noise_amt=0.05,
        blurb="astromech unleashed -- wide bends, deep ring mod, servo noise",
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
    # Deliberately breaks the tool's own consonance guarantee. Present for
    # the droid presets, where speech-like arbitrariness is the point and
    # two cues overlapping is not a scenario anyone is designing for.
    "chromatic": list(range(12)),
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
    # Four-note shapes. Past three notes a cue starts reading as a melody
    # rather than a token; these exist for cues that can afford the time.
    "rise4": [0, 1, 2, 4],
    "fall4": [0, -1, -2, -4],
    "arch": [0, 2, 4, 2],
    "vee": [0, -2, -4, -2],
    "double_rise": [0, 2, 0, 2],
    "query": [0, 1, 3, 6],
    # Droid material. Long, jumpy, and speech-like -- these are what the
    # --r2 presets reach for, and they are a poor fit for anything else.
    "whistle_up": [0, 7],
    "whistle_down": [0, -7],
    "scan": [0, 1, 2, 3, 4, 5],
    "chatter5": [0, 3, 1, 4, 2],
    "chatter7": [0, 4, 1, 5, 2, 6, 3],
    "burble": [0, 2, -1, 3, 0, 4],
    "alarm_trill": [0, 4, 0, 4, 0, 4],
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
    note_count: int | None = None   # per-cue cap; None uses --note-count
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
# The catalogue.
#
# `core` is the original eight and is still the default; its output is
# unchanged. The rest are curated sets for specific problem domains, on the
# principle from USAGE.md that the answer to needing more than eight cues is
# to pick a different eight, not to ship sixteen.
#
# Within a set, related cues share a contour opening and opposed cues have
# opposed contours. Across sets, slugs are namespaced so two themes can be
# generated into one directory without collision.
# ---------------------------------------------------------------------------

FAMILIES: dict[str, list[EarconSpec]] = {
    "core": DEFAULT_FAMILY,

    # Direct manipulation. Short, quiet, high-frequency-of-use cues -- these
    # fire many times an hour, so they are the ones that must not wear out.
    "ui": [
        EarconSpec("ui_open", "rise2", 0, gain=0.85, label="panel or view opening"),
        EarconSpec("ui_close", "fall2", 0, gain=0.85, label="panel or view closing"),
        EarconSpec("ui_select", "single", 2, gain=0.75, label="item selected"),
        EarconSpec("ui_confirm", "rise3", 1, label="action confirmed"),
        EarconSpec("ui_cancel", "fall3", -1, label="action cancelled"),
        EarconSpec("ui_toggle_on", "leap_up", 0, gain=0.85, label="switch on"),
        EarconSpec("ui_toggle_off", "leap_down", 0, gain=0.85, label="switch off"),
        EarconSpec("ui_deny", "downup", -3, label="not permitted"),
    ],

    # Machine state. Longer, more ceremonial -- these fire rarely and want
    # to be noticed when they do.
    "system": [
        EarconSpec("sys_boot", "rise4", -2, label="service starting"),
        EarconSpec("sys_ready", "rise_hold", 0, label="service ready"),
        EarconSpec("sys_connect", "rise2", 2, label="link established"),
        EarconSpec("sys_disconnect", "fall2", 2, label="link lost"),
        EarconSpec("sys_update", "updown", 1, label="update available"),
        EarconSpec("sys_battery_low", "fall4", -1, label="power reserve low"),
        EarconSpec("sys_job_done", "arch", 0, label="background task finished"),
        EarconSpec("sys_job_failed", "vee", -2, label="background task failed"),
    ],

    # Interruptions from other people. These compete with whatever the
    # listener is doing, so contour separation matters more than usual.
    "message": [
        EarconSpec("msg_in", "rise2", 1, label="incoming message"),
        EarconSpec("msg_sent", "fall2", 3, gain=0.8, label="message sent"),
        EarconSpec("msg_mention", "updown", 3, label="you were mentioned"),
        EarconSpec("msg_call_in", "double_rise", 0, gap_ms=190.0, label="incoming call"),
        EarconSpec("msg_call_end", "fall3", 0, label="call ended"),
    ],

    # Long-running operations. `prog_tick` is deliberately the quietest cue
    # in the catalogue: anything that can fire every few seconds must be
    # closer to a texture than to an alert.
    "progress": [
        EarconSpec("prog_start", "rise2", -1, label="operation started"),
        EarconSpec("prog_tick", "single", 0, gain=0.55, label="progress step"),
        EarconSpec("prog_complete", "rise3", 2, label="operation complete"),
        EarconSpec("prog_stalled", "level3", -2, label="stalled, awaiting input"),
        EarconSpec("prog_abort", "fall4", -3, label="operation aborted"),
    ],

    # Astromech, house-trained. Same slugs as `droid_full` so the two are
    # drop-in swappable once you have decided how much character you want.
    "droid": [
        EarconSpec("r2_affirm", "rise3", 1, label="yes / acknowledged"),
        EarconSpec("r2_negate", "fall3", -1, label="no / refused"),
        EarconSpec("r2_query", "query", 0, label="asking a question"),
        EarconSpec("r2_excited", "chatter5", 2, label="pleased / excited"),
        EarconSpec("r2_worried", "downup", -2, label="uncertain / worried"),
        EarconSpec("r2_scan", "scan", 0, gain=0.8, label="scanning / working"),
        EarconSpec("r2_alert", "alarm_trill", 3, label="urgent warning"),
        EarconSpec("r2_powerdown", "fall4", -2, note_ms=420.0, label="powering down"),
    ],

    # Astromech, unleashed. Longer phrases, wider leaps. Reached for by
    # --r2-full, which also swaps in the chromatic scale and a wider band.
    "droid_full": [
        EarconSpec("r2_affirm", "whistle_up", 1, label="yes / acknowledged"),
        EarconSpec("r2_negate", "whistle_down", -1, label="no / refused"),
        EarconSpec("r2_query", "query", 0, label="asking a question"),
        EarconSpec("r2_excited", "chatter7", 2, label="pleased / excited"),
        EarconSpec("r2_worried", "burble", -2, label="uncertain / worried"),
        EarconSpec("r2_scan", "scan", 0, gain=0.8, label="scanning / working"),
        EarconSpec("r2_alert", "alarm_trill", 4, label="urgent warning"),
        EarconSpec("r2_powerdown", "fall4", -3, note_ms=520.0, gap_ms=210.0,
                   label="powering down"),
    ],
}


def resolve_family(name: str) -> list[EarconSpec]:
    """`all` is every non-droid cue, for auditioning the catalogue in one
    pass. It is not a family anyone should ship -- see --list-families."""
    if name != "all":
        return FAMILIES[name]
    out: list[EarconSpec] = []
    seen: set[str] = set()
    for key, specs in FAMILIES.items():
        if key.startswith("droid"):
            continue
        for spec in specs:
            if spec.slug not in seen:
                seen.add(spec.slug)
                out.append(spec)
    return out


FAMILY_NAMES = sorted(FAMILIES) + ["all"]


# ---------------------------------------------------------------------------
# Presets: named bundles of flag values. A preset only fills in options you
# did not set yourself, so `--r2 --voice bell` does exactly what it looks
# like it does.
# ---------------------------------------------------------------------------

PRESETS: dict[str, dict] = {
    "r2": {
        "blurb": "astromech chatter that still behaves like an earcon set",
        "voice": "droid",
        "scale": "kumoi",
        "family": "droid",
        "root": 587.33,
        "floor": 420.0,
        "ceiling": 1400.0,
        "note_ms": 200.0,
        "gap_ms": 95.0,
        "tail_ms": 220.0,
        "out": "audio/r2",
    },
    "r2-full": {
        "blurb": "astromech unleashed -- chromatic, wide band, long phrases",
        "voice": "droid_wild",
        "scale": "chromatic",
        "family": "droid_full",
        "root": 659.25,
        "floor": 300.0,
        "ceiling": 3200.0,
        "note_ms": 140.0,
        "gap_ms": 70.0,
        "tail_ms": 260.0,
        "gain": 0.9,
        "out": "audio/r2-full",
    },
}


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


def freq_track(freq: float, prev_freq: float | None, voice: Voice,
               decay_ms: float, n: int, t: np.ndarray) -> np.ndarray | None:
    """Instantaneous fundamental over the note, or None if it is constant.

    Returning None matters: a constant-pitch note takes the closed-form
    phase path below, which is both faster and bit-identical to what this
    tool emitted before glides existed. Only voices that actually modulate
    pay for the integrated path.
    """
    glides = (voice.glide_ms > 0.0 and prev_freq is not None
              and prev_freq > 0.0 and abs(prev_freq - freq) > 1e-9)
    warbles = voice.vib_hz > 0.0 and voice.vib_cents != 0.0
    if not (glides or warbles or voice.sweep_cents):
        return None

    f = np.full(n, float(freq))

    if glides:
        # Glide in log-frequency space, eased with a raised cosine. Linear
        # interpolation in Hz sounds like a machine; this sounds like a
        # voice, which is the whole point.
        g = min(max(1, int(SR * voice.glide_ms / 1000.0)), n)
        x = 0.5 * (1.0 - np.cos(np.pi * np.arange(g) / g))
        f[:g] = prev_freq * (freq / prev_freq) ** x

    if voice.sweep_cents:
        # Bend across the note's own decay time, not the render length.
        prog = np.clip(t / max(decay_ms / 1000.0, 1e-4), 0.0, 1.0)
        f = f * 2.0 ** ((voice.sweep_cents / 1200.0) * prog)

    if warbles:
        f = f * 2.0 ** ((voice.vib_cents / 1200.0)
                        * np.sin(2.0 * np.pi * voice.vib_hz * t))

    return f


def render_note(freq: float, voice: Voice, decay_ms: float, render_n: int,
                prev_freq: float | None = None) -> np.ndarray:
    """Render one note for `render_n` samples, decaying with time constant
    derived from `decay_ms`. Render length and decay length are separate:
    the caller renders to the end of the buffer so nothing is cut off.

    `prev_freq` is the previous note's fundamental, used only by voices
    with a non-zero glide.
    """
    if render_n <= 0:
        return np.zeros(0)
    t = np.arange(render_n) / SR
    out = np.zeros(render_n)

    f_t = freq_track(freq, prev_freq, voice, decay_ms, render_n, t)

    for ratio, amp, dec in zip(voice.ratios, voice.amps,
                               voice.decays, strict=True):
        if f_t is None:
            pf = freq * ratio
            if pf >= SR / 2.0:      # skip anything that would alias
                continue
            phase = 2.0 * np.pi * pf * t
            mod_phase = 2.0 * np.pi * pf * voice.fm_ratio * t
        else:
            pf_t = f_t * ratio
            if float(np.max(pf_t)) >= SR / 2.0:
                continue
            # Phase is the integral of instantaneous frequency. Multiplying
            # a varying frequency by t instead is the classic way to get a
            # note that is in tune at both ends and wrong in the middle.
            phase = (2.0 * np.pi / SR) * np.cumsum(pf_t)
            mod_phase = phase * voice.fm_ratio

        if voice.fm_index > 0.0:
            mod_env = np.exp(-t / max(voice.fm_decay * decay_ms / 1000.0, 1e-5))
            phase = phase + voice.fm_index * mod_env * np.sin(mod_phase)

        env = envelope(render_n, voice.attack_ms, decay_ms, dec)
        out += amp * env * np.sin(phase)

    # Ring modulation. A non-integer ratio puts sum and difference tones
    # where no harmonic series would, which is most of what reads as
    # "machine trying to talk" rather than "instrument".
    if voice.ring_depth > 0.0 and voice.ring_ratio > 0.0:
        carrier = f_t if f_t is not None else np.full(render_n, float(freq))
        ring_phase = (2.0 * np.pi / SR) * np.cumsum(carrier * voice.ring_ratio)
        out = out * (1.0 - voice.ring_depth) + out * np.sin(ring_phase) * voice.ring_depth

    # Servo noise, band-limited by a crude moving average tied to the
    # fundamental. Deterministically seeded so repeat runs are identical.
    if voice.noise_amt > 0.0:
        rng = np.random.default_rng(int(abs(freq) * 1000.0) & 0xFFFFFFFF)
        nz = rng.standard_normal(render_n)
        k = max(1, int(SR / max(freq, 1.0) / 4.0))
        if k > 1:
            nz = np.convolve(nz, np.ones(k) / k, mode="same")
        peak = float(np.max(np.abs(nz)))
        if peak > 1e-9:
            nz /= peak
        out += voice.noise_amt * envelope(render_n, voice.attack_ms, decay_ms, 1.8) * nz

    return out


# ---------------------------------------------------------------------------
# Shortening a family properly.
#
# Truncation is blunt: `rise3` cut to two notes is `rise2`, and any two
# contours sharing an opening become the same sound. The alternative is to
# ask what each contour *means* and hand it a purpose-built shape of the
# requested length that still means it -- a big rise stays a big rise, an
# arch still returns to where it started.
#
# Two mechanisms do that, and they are separate on purpose:
#
#   1. REDUCTIONS, below, is authored. It says what each contour becomes at
#      each shorter length. It preserves meaning but cannot guarantee
#      distinctness, because distinctness is a property of a family rather
#      than of a contour.
#   2. Register separation, in plan_family(), guarantees distinctness. Where
#      two cues still land on the same shape it moves one of them to a
#      different register -- upward for a rising cue, downward for a falling
#      one, so the nudge reinforces the meaning instead of fighting it.
#
# At one note there is only one possible shape, so mechanism 1 has nothing
# to offer and mechanism 2 does all the work. That is exactly the argument
# in --notes for why single-note families are weaker: register is all that
# is left to carry meaning.
# ---------------------------------------------------------------------------

#: What each contour is *for*. Drives which way a nudged cue moves, and
#: nothing else. Every contour in CONTOURS must appear here; a test checks.
CONTOUR_CHARACTER: dict[str, str] = {
    "rise2": "rise", "rise3": "rise", "rise_hold": "rise", "rise4": "rise",
    "leap_up": "rise", "whistle_up": "rise", "scan": "rise",
    "double_rise": "rise", "query": "rise",
    "fall2": "fall", "fall3": "fall", "fall4": "fall",
    "leap_down": "fall", "whistle_down": "fall",
    "updown": "updown", "arch": "updown",
    "downup": "downup", "vee": "downup",
    "level2": "level", "level3": "level", "single": "level",
    "chatter5": "chatter", "chatter7": "chatter", "burble": "chatter",
    "alarm_trill": "chatter",
}

#: Which way to look for a free register when two cues collide. A rising
#: cue that has to move goes up.
NUDGE_DIRECTION: dict[str, int] = {
    "rise": +1, "updown": +1, "chatter": +1,
    "fall": -1, "downup": -1,
    "level": +1,
}

#: Purpose-built shapes for contours asked to be shorter than they are.
#: A missing length falls back to truncation, which is right for the cases
#: where the opening genuinely is the whole idea (`leap_up` at two notes is
#: already `leap_up`). Length 1 is never authored: it is always a single
#: note, and register does the work.
REDUCTIONS: dict[str, dict[int, list[int]]] = {
    # Three rising cues that must stay distinguishable, so they reduce to
    # three different sizes of rise rather than all to [0, 2].
    "rise3": {2: [0, 4]},
    "rise_hold": {2: [0, 1]},
    "rise4": {3: [0, 2, 4], 2: [0, 5]},
    "fall3": {2: [0, -4]},
    "fall4": {3: [0, -2, -4], 2: [0, -5]},
    # The turning shapes keep their turn for as long as they have notes to
    # spend on it, then keep their first move.
    "updown": {2: [0, 3]},
    "downup": {2: [0, -3]},
    "arch": {3: [0, 4, 0], 2: [0, 2]},
    "vee": {3: [0, -4, 0], 2: [0, -2]},
    # Ends high, because that is the half of "up, back, up again" that
    # carries the meaning. [0, 2, 0] would end where it started, which is
    # a different cue wearing the same name.
    "double_rise": {3: [0, 0, 2], 2: [0, 2]},
    "query": {3: [0, 3, 6], 2: [0, 6]},
    "level3": {2: [0, 0]},
    # The long droid material thins out rather than being cut off, so a
    # shortened chatter still reads as chatter instead of as a two-note
    # motif that happens to start the same way.
    "scan": {5: [0, 1, 2, 3, 5], 4: [0, 2, 3, 5], 3: [0, 2, 5], 2: [0, 5]},
    "chatter5": {4: [0, 3, 1, 4], 3: [0, 3, 1], 2: [0, 3]},
    "chatter7": {6: [0, 4, 1, 5, 2, 6], 5: [0, 4, 1, 5, 3], 4: [0, 4, 1, 5],
                 3: [0, 4, 1], 2: [0, 4]},
    "burble": {5: [0, 2, -1, 3, 4], 4: [0, 2, -1, 3], 3: [0, 2, -1], 2: [0, 2]},
    "alarm_trill": {5: [0, 4, 0, 4, 0], 4: [0, 4, 0, 4], 3: [0, 4, 0], 2: [0, 4]},
}

#: How --cap-mode shortens a family.
CAP_MODES = ("redesign", "truncate")


@dataclass
class PitchContext:
    """Everything needed to turn a placement into actual frequencies.

    Register separation is meaningless without this. Two cues four scale
    degrees apart look separated on paper and can still come out as the
    same sound, because fit_to_range folds every motif into the band by
    whole octaves: with a five-note scale and a band a little over an
    octave wide, degrees 0 and 5 land on exactly the same frequency.
    Separation therefore has to be judged on the pitches that actually
    come out, not on the degrees that went in.
    """
    root_hz: float
    scale: list[int]
    floor: float
    ceiling: float


@dataclass
class Placement:
    """One cue's final shape and register, after any shortening."""
    spec: EarconSpec
    degrees: list[int]
    root_offset: int
    #: True when no free register could be found -- the band is full. The
    #: cue still renders; it just is not unique.
    unresolved: bool = False

    @property
    def moved(self) -> bool:
        """Whether register separation had to move this cue."""
        return self.root_offset != self.spec.root_offset

    @property
    def notes(self) -> int:
        return len(self.degrees)

    def frequencies(self, pitch: PitchContext) -> tuple[float, ...]:
        """The pitches this cue will actually sound, after band fitting."""
        degrees = [self.root_offset + d for d in self.degrees]
        freqs = fit_to_range(
            [scale_freq(pitch.root_hz, pitch.scale, d) for d in degrees],
            pitch.floor, pitch.ceiling,
        )
        # Rounded so that two motifs differing by floating-point noise are
        # correctly treated as the same sound.
        return tuple(round(f, 4) for f in freqs)

    def in_band(self, pitch: PitchContext) -> bool:
        """Whether every note actually landed inside the band.

        fit_to_range gives up after six octave shifts, so a sufficiently
        extreme register comes back out of band rather than folded. Those
        results look distinct and are useless: they are exactly the
        shrillness the band exists to prevent. Register separation has to
        rule them out, or a search for a free slot will happily walk off
        the top of the band and report success.
        """
        freqs = self.frequencies(pitch)
        tolerance = 1e-6
        return all(pitch.floor - tolerance <= f <= pitch.ceiling + tolerance
                   for f in freqs)


def effective_cap(spec: EarconSpec, note_count: int | None) -> int | None:
    """The note cap for one cue: its own if set, otherwise the flag's."""
    cap = spec.note_count if spec.note_count is not None else note_count
    return cap if cap is not None and cap > 0 else None


def capped_contour(spec: EarconSpec, note_count: int | None) -> list[int]:
    """Truncate a contour to at most N notes.

    The blunt instrument, reached for by `--cap-mode truncate`. `rise3` at
    N=2 is the first two notes of `rise3`, so a family shortened this way
    keeps its openings intact and loses the cues that differ only after the
    cut point.
    """
    contour = CONTOURS[spec.contour]
    cap = effective_cap(spec, note_count)
    return contour[:cap] if cap else contour


def reduced_contour(spec: EarconSpec, note_count: int | None) -> list[int]:
    """Shorten a contour to N notes, preserving what it means.

    Uses the authored shape for that contour at that length where one
    exists, a single note at length 1, and truncation otherwise.
    """
    contour = CONTOURS[spec.contour]
    cap = effective_cap(spec, note_count)
    if not cap or cap >= len(contour):
        return contour
    if cap == 1:
        return [0]
    authored = REDUCTIONS.get(spec.contour, {}).get(cap)
    return list(authored) if authored is not None else contour[:cap]


def distinct_pitch_capacity(pitch: PitchContext) -> int:
    """How many distinguishable single notes this band and scale provide.

    The hard ceiling on a one-note family. A 480-1150 Hz band is a little
    over an octave, and a pentatonic has five notes per octave, so the
    answer is usually five or six -- which is why an eight-cue family
    cannot survive `-n 1` intact no matter how cleverly it is arranged.
    """
    seen = set()
    for degree in range(-60, 61):
        freq = fit_to_range(
            [scale_freq(pitch.root_hz, pitch.scale, degree)],
            pitch.floor, pitch.ceiling,
        )[0]
        if pitch.floor - 1e-6 <= freq <= pitch.ceiling + 1e-6:
            seen.add(round(freq, 4))
    return len(seen)


def plan_family(specs: list[EarconSpec], note_count: int | None = None,
                cap_mode: str = "redesign",
                pitch: PitchContext | None = None) -> list[Placement]:
    """Work out the final shape and register of every cue in a family.

    With no cap this is the identity: each cue keeps its declared contour
    and register, which is what makes an uncapped family bit-for-bit what
    it has always been.

    With a cap in redesign mode, contours are reduced and then any two cues
    that still collide are separated by register. The cue that moves is the
    later one in declaration order, and it moves in the direction its
    character implies, so a rising cue that has to give way ends up higher
    rather than in an arbitrary spot.
    """
    if cap_mode not in CAP_MODES:
        raise ValueError(f"Unknown cap mode {cap_mode!r}; expected one of {CAP_MODES}.")

    shorten = capped_contour if cap_mode == "truncate" else reduced_contour
    plans = [Placement(spec, list(shorten(spec, note_count)), spec.root_offset)
             for spec in specs]

    # An uncapped family is left exactly as declared. Anything else would
    # let this function change output that has never asked to be changed.
    if not any(effective_cap(spec, note_count) for spec in specs):
        return plans

    if cap_mode == "truncate":
        # Truncation is chosen deliberately for its bluntness; silently
        # repairing it would take away the thing being asked for. main()
        # reports the collisions instead.
        return plans

    # What counts as "the same cue". With pitch context this is the actual
    # sounding frequencies, which is the only test that means anything;
    # without it, the shape and register are the best available proxy.
    def signature(plan: Placement):
        if pitch is not None:
            return plan.frequencies(pitch)
        return (tuple(plan.degrees), plan.root_offset)

    def probe(plan: Placement, offset: int):
        """The signature a cue would have at `offset`, or None if that
        register puts it outside the band."""
        trial = Placement(plan.spec, plan.degrees, offset)
        if pitch is not None and not trial.in_band(pitch):
            return None
        return signature(trial)

    # Every declared placement is reserved before anything moves, so a cue
    # is never nudged onto a register that a later cue is about to claim.
    reserved = {signature(p) for p in plans}
    taken: set = set()

    for plan in plans:
        if signature(plan) not in taken:
            taken.add(signature(plan))
            continue

        direction = NUDGE_DIRECTION.get(
            CONTOUR_CHARACTER.get(plan.spec.contour, "level"), +1
        )
        # The cue's own direction is searched to exhaustion before the
        # other one is tried at all. Sweeping outward by distance instead
        # would let a rising cue settle one step below its neighbour
        # rather than four steps above it, which reads as the wrong cue.
        #
        # The range is generous because a fold-limited band repeats every
        # few degrees: the search is looking for a genuinely new sound,
        # not merely a new number.
        found = False
        for sign in (direction, -direction):
            for distance in range(1, 64):
                offset = plan.root_offset + sign * distance
                candidate = probe(plan, offset)
                if candidate is None:
                    continue
                if candidate not in reserved and candidate not in taken:
                    plan.root_offset = offset
                    found = True
                    break
            if found:
                break

        # Nothing free anywhere. The band is full; the cue renders as a
        # duplicate and says so rather than pretending otherwise.
        plan.unresolved = not found
        taken.add(signature(plan))

    return plans


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
    plan: Placement,
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
    """Render one cue. Shape and register are already settled by
    plan_family(); everything left is timbre, timing and level."""
    spec = plan.spec
    nm = spec.note_ms if spec.note_ms is not None else note_ms
    gm = spec.gap_ms if spec.gap_ms is not None else gap_ms

    degrees = [plan.root_offset + d for d in plan.degrees]
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
        buf[start:] += render_note(f, voice, nm, total - start,
                                   prev_freq=freqs[i - 1] if i else None)

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
    for cmd in (["paplay"], ["aplay", "-q"],
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
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

On shortening motifs
--------------------

--note-count caps every motif at N notes. --cap-mode decides how.

`redesign`, the default, asks what each contour means and substitutes a
purpose-built shape of that length which still means it: a big rise stays
a big rise instead of becoming a small one, and an arch still returns to
where it started. Cues that still collide are moved into a different
register -- upward for a rising cue, downward for a falling one, so the
nudge agrees with the meaning rather than fighting it.

`truncate` just cuts each contour short. Openings survive exactly, and
contours that differ only after the cut point become the same sound. That
is a legitimate thing to want and it is never silent: the casualties are
named.

Either way, the collision test is on the pitches that actually come out,
not on scale degrees. fit_to_range folds every motif into the band by
whole octaves, so two cues five degrees apart on a pentatonic are the same
frequency; comparing degrees would call them separated and be wrong.

That folding is also a hard ceiling on one-note families. Register is all
a single note has, and the number of registers is fixed by the band and
the scale: a pentatonic in the default 480-1150 Hz band gives six
distinguishable pitches, so an eight-cue family cannot survive -n 1 no
matter how it is arranged. Widening to 300-2400 Hz gives fifteen. That is
the real cost of one-note cues -- they buy brevity with the quiet part of
the spectrum -- and it is why they are worth reaching for only when
something forces your hand: a tight flash budget, a host that cuts cues
off at 200 ms, a context where anything longer reads as slow.

On the droid presets
--------------------

--r2 and --r2-full break several of the rules above on purpose. Real
astromech vocalisations are ring-modulated, glide between pitches, warble,
and run to six or seven blips; --r2-full also goes chromatic and up into
the 2-4 kHz band this tool otherwise avoids. That combination is
expressive and characterful and is a poor choice for a cue that fires
forty times a day.

--r2 is the version that still behaves: in-band, pentatonic, phrases
capped where a notification sound should be capped. --r2-full is for when
character is the point and fatigue is not your problem. Both are ordinary
presets, so any flag you set yourself still wins over them.

Things worth trying
-------------------

  --voice marimba --note-ms 190 --gap-ms 130     tight and businesslike
  --voice bell --scale hirajoshi --gap-ms 220    more ceremonial
  --voice chime --floor 380 --ceiling 800        warmer, sits lower
  --voice alert --gain 1.15                      more presence for danger
  --root 587.33                                  shift the whole family up
  --family ui --voice marimba                    dense, low-ceremony UI set
  --family system --voice bell --gap-ms 220      rare events, more weight
  -n 2 --gap-ms 110                              terser without losing contour
  -n 1 --floor 300 --ceiling 2400                one note each, band widened to fit
  -n 2 --cap-mode truncate                       keep openings, accept collisions
  --r2 --voice marimba                           droid phrasing, wooden timbre
  --r2-full --ceiling 2000                       unleashed but less shrill

If a tone is annoying, raise --attack-ms before touching anything else.
If it is hard to hear over background noise, try --voice marimba before
raising the gain -- legibility is usually a timbre problem, not a volume
problem.
"""


@dataclass
class Rendered:
    """One written file, as reported back to whoever asked for the render."""
    path: Path
    duration: float
    spec: EarconSpec
    notes: int


def explicit_dests(parser: argparse.ArgumentParser, argv: list[str]) -> set[str]:
    """Which options the user actually typed, regardless of their values.

    Presets need this. Checking `args.x == default` cannot distinguish
    "left alone" from "set to the default on purpose", and getting that
    wrong means a preset silently overrides an explicit flag.
    """
    given: set[str] = set()
    for action in parser._actions:
        for opt in action.option_strings:
            if any(tok == opt or tok.startswith(opt + "=") for tok in argv):
                given.add(action.dest)
    return given


def degenerate_groups(family: list[EarconSpec],
                      note_count: int | None,
                      pitch: PitchContext | None = None,
                      cap_mode: str = "truncate") -> list[list[str]]:
    """Cues a note cap has rendered indistinguishable from each other.

    Given a PitchContext this compares the pitches that actually come out,
    which is the only comparison that means anything: two motifs four
    scale degrees apart can still be the same sound once fit_to_range has
    folded them into the band. Without one it falls back to comparing
    shapes and registers, which is a reasonable proxy and no more.

    Writing two identical WAVs under different names is the kind of thing
    you discover months later, so it gets said out loud at generation
    time rather than left to be noticed.
    """
    if not note_count:
        return []
    plans = plan_family(family, note_count, cap_mode, pitch)
    buckets: dict[tuple, list[str]] = {}
    for plan in plans:
        if pitch is not None:
            key = (plan.frequencies(pitch), plan.spec.note_ms,
                   plan.spec.gap_ms, plan.spec.gain)
        else:
            key = (tuple(plan.degrees), plan.root_offset, plan.spec.note_ms,
                   plan.spec.gap_ms, plan.spec.gain)
        buckets.setdefault(key, []).append(plan.spec.slug)
    return [slugs for slugs in buckets.values() if len(slugs) > 1]


def build_parser() -> argparse.ArgumentParser:
    """The command line, as a separate object.

    The GUI reads defaults and choices from this rather than keeping its
    own copy, so a bound or a default cannot be changed in one place and
    quietly disagree with the other.
    """
    p = argparse.ArgumentParser(
        description="Generate a family of related earcons.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--out", default="audio/chime", help="output directory")
    p.add_argument("--voice", default="chime", choices=sorted(VOICES), help="timbre")
    p.add_argument("--family", default="core", choices=FAMILY_NAMES,
                   help="which set of cues to generate (default core, the "
                        "original eight); see --list-families")
    p.add_argument("-n", "--note-count", type=int, default=None, metavar="N",
                   help="cap every motif at N notes; see --cap-mode")
    p.add_argument("--cap-mode", default="redesign", choices=list(CAP_MODES),
                   help="how -n shortens a family. redesign swaps in a "
                        "purpose-built shape of that length and separates "
                        "any cues that still collide by register; truncate "
                        "just cuts each contour short, which is blunter and "
                        "can leave two cues identical")
    p.add_argument("--preset", choices=sorted(PRESETS),
                   help="named bundle of options; explicit flags still win")
    p.add_argument("--r2", action="store_true",
                   help="shorthand for --preset r2")
    p.add_argument("--r2-full", action="store_true",
                   help="shorthand for --preset r2-full")
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
    p.add_argument("--glide-ms", type=float, default=None,
                   help="override the voice's portamento between notes")
    p.add_argument("--ring-depth", type=float, default=None,
                   help="override the voice's ring modulation mix (0-1)")
    p.add_argument("--vib-cents", type=float, default=None,
                   help="override the voice's warble depth in cents")
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
    p.add_argument("--list-families", action="store_true")
    p.add_argument("--list-presets", action="store_true")
    p.add_argument("--notes", action="store_true",
                   help="print the design reasoning behind the defaults")
    return p


def apply_preset(args: argparse.Namespace, parser: argparse.ArgumentParser,
                 argv: list[str]) -> None:
    """Fill in preset values for options the user did not type."""
    if getattr(args, "r2_full", False):
        args.preset = args.preset or "r2-full"
    elif getattr(args, "r2", False):
        args.preset = args.preset or "r2"
    if not args.preset:
        return
    # Only fill in what the user left alone. Comparing against argv
    # rather than against the defaults means `--r2 --gap-ms 150` is
    # honoured even when 150 happens to be the default value.
    given = explicit_dests(parser, argv)
    for key, value in PRESETS[args.preset].items():
        if key != "blurb" and key not in given:
            setattr(args, key, value)


def resolve_voice(args: argparse.Namespace) -> Voice:
    """The voice named by --voice, with any per-flag overrides applied."""
    overrides = {
        "attack_ms": getattr(args, "attack_ms", None),
        "decay_ms": getattr(args, "decay_ms", None),
        "glide_ms": getattr(args, "glide_ms", None),
        "ring_depth": getattr(args, "ring_depth", None),
        "vib_cents": getattr(args, "vib_cents", None),
    }
    voice = VOICES[args.voice]
    if any(v is not None for v in overrides.values()):
        voice = Voice(**{**asdict(voice),
                         **{k: v for k, v in overrides.items() if v is not None}})
    return voice


def pitch_context(args: argparse.Namespace,
                  scale: list[int] | None = None) -> PitchContext:
    """The band and pitch set a family will be fitted into."""
    return PitchContext(args.root, scale if scale is not None else SCALES[args.scale],
                        args.floor, args.ceiling)


def resolve_specs(args: argparse.Namespace) -> list[EarconSpec]:
    """The cues to render: a spec file if given, otherwise a family."""
    spec_file = getattr(args, "spec", None)
    if spec_file:
        raw = json.loads(Path(spec_file).read_text())
        return [EarconSpec(**d) for d in raw]
    return resolve_family(args.family)


def generate_family(args: argparse.Namespace,
                    on_file=None) -> list[Rendered]:
    """Render and write every cue, reporting each file as it lands.

    This is the one rendering path. The CLI prints from `on_file`, the
    GUI updates a progress bar and a list from it; neither reimplements
    the resolution rules, which is what stops them diverging.
    """
    voice = resolve_voice(args)
    specs = resolve_specs(args)
    scale = SCALES[args.scale]
    note_ms = args.note_ms if args.note_ms is not None else voice.decay_ms
    outdir = Path(args.out)
    note_count = getattr(args, "note_count", None)

    pitch = pitch_context(args, scale)
    written: list[Rendered] = []
    for plan in plan_family(specs, note_count,
                            getattr(args, "cap_mode", "redesign"), pitch):
        sig = render_earcon(
            plan, voice, scale, args.root, args.floor, args.ceiling,
            note_ms, args.gap_ms, args.target_rms * args.gain,
            args.peak, args.tail_ms, args.release_ms,
        )
        path = outdir / f"{plan.spec.slug}.wav"
        write_wav(path, sig, stereo=args.stereo)
        item = Rendered(path, sig.size / SR, plan.spec, plan.notes)
        written.append(item)
        if on_file is not None:
            on_file(item)
    return written


def main() -> int:
    p = build_parser()
    args = p.parse_args()

    apply_preset(args, p, sys.argv[1:])

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
            print(f"  {name:<11} {len(c)} note{'s' if len(c) != 1 else ''}  {c}")
        return 0

    if args.list_families:
        for name in FAMILY_NAMES:
            specs = resolve_family(name)
            note = ""
            if name == "core":
                note = "   (default -- the original eight)"
            elif name == "all":
                note = "   (every non-droid cue; for auditioning, not shipping)"
            print(f"  {name:<11} {len(specs):>2} cues{note}")
            for spec in specs:
                print(f"      {spec.slug:<17} {spec.contour:<12} {spec.label}")
            print()
        return 0

    if args.list_presets:
        for name in sorted(PRESETS):
            cfg = PRESETS[name]
            print(f"  {name:<9} {cfg['blurb']}")
            body = ", ".join(f"{k}={v}" for k, v in cfg.items() if k != "blurb")
            print(f"            {body}")
        return 0

    if args.dump_spec:
        print(json.dumps([asdict(s) for s in resolve_family(args.family)], indent=2))
        return 0

    family = resolve_specs(args)

    if args.note_count:
        if args.cap_mode == "truncate":
            for slugs in degenerate_groups(family, args.note_count,
                                           pitch_context(args), "truncate"):
                print(f"  warning: -n {args.note_count} makes these identical: "
                      f"{', '.join(slugs)}  (--cap-mode redesign separates them)",
                      file=sys.stderr)
        else:
            pitch = pitch_context(args)
            plans = plan_family(family, args.note_count, args.cap_mode, pitch)
            moved = [p for p in plans if p.moved and not p.unresolved]
            stuck = [p for p in plans if p.unresolved]
            if moved:
                detail = ", ".join(
                    f"{p.spec.slug} {p.spec.root_offset:+d}->{p.root_offset:+d}"
                    for p in moved
                )
                print(f"  note: shortening left these sharing a shape, so they "
                      f"were separated by register: {detail}")
            if stuck:
                capacity = distinct_pitch_capacity(pitch)
                print(
                    f"  warning: no register left for "
                    f"{', '.join(p.spec.slug for p in stuck)}. A "
                    f"{args.floor:.0f}-{args.ceiling:.0f} Hz band on the "
                    f"{args.scale} scale holds {capacity} distinguishable "
                    f"pitches, and {len(family)} cues at {args.note_count} "
                    f"note{'s' if args.note_count != 1 else ''} need more than "
                    f"that. Widen the band, raise -n, or ship fewer cues.",
                    file=sys.stderr,
                )

    outdir = Path(args.out)

    head = f"voice={args.voice}  scale={args.scale}  root={args.root:.2f}Hz  "
    head += f"band={args.floor:.0f}-{args.ceiling:.0f}Hz"
    if not args.spec:
        head += f"  family={args.family}"
    if args.note_count:
        head += f"  n<={args.note_count} ({args.cap_mode})"
    if args.preset:
        head += f"  preset={args.preset}"
    print(f"{head} -> {outdir}/")

    def report(item: Rendered) -> None:
        print(f"  {item.path}  {item.duration:5.2f}s  {item.spec.contour:<11} "
              f"{item.notes}n  {item.spec.label}")
        if args.play:
            play(item.path)

    generate_family(args, on_file=report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
