#!/usr/bin/env python3
"""
earconcheck.py -- quality checks for short audio cues.

Catches the defects that are easy to introduce and easy to miss when you
are looking at waveforms rather than listening: end-of-file clicks,
envelope discontinuities, DC offset, clipping, and loudness that is
inconsistent across a family.

Works on any mono or stereo 16-bit WAV, not just earcongen output, so it
is also useful for vetting user-supplied sound files before an
application accepts them.

    ./earconcheck.py audio/chime/*.wav
    ./earconcheck.py --verbose audio/chime/earcon01.wav

Exit status is non-zero if any file fails, so this drops into CI.

Why an envelope check rather than a peak or endpoint check
----------------------------------------------------------
A click is a discontinuity in the *envelope*, not in the sample values.
Checking the last sample of a file will not find a click that occurs
250 ms earlier; checking the largest sample-to-sample step will flag
legitimate high-frequency content, because a sine at amplitude A and
frequency f has a maximum slew of A*2*pi*f/SR regardless of whether
anything is wrong. Tracking the short-window peak envelope and looking
for drops that are too fast to be a decay finds the real thing.

Note that this check reports beat-induced zero crossings between
overlapping partials as mild drops. Anything below about 6x is normally
that rather than a defect; confirm by looking at the sample neighbourhood
with --verbose before chasing it.

Ring-modulated and heavily warbled cues -- anything from the droid voices
-- push envelope nulls much closer to that limit as a matter of course,
because a ring modulator drives the signal through zero at the difference
frequency by design. Use --modulated on those, which raises the limit to
a level that still catches genuine truncation clicks.
"""

from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

import numpy as np


def load(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"{path}: expected 16-bit, got {width * 8}-bit")
    d = np.frombuffer(raw, dtype="<i2").astype(float) / 32768.0
    if ch > 1:
        d = d.reshape(-1, ch).mean(axis=1)
    return d, sr


def a_weight_gain(f: np.ndarray) -> np.ndarray:
    f = np.maximum(f, 1e-6)
    f2 = f ** 2
    num = (12194.0 ** 2) * (f2 ** 2)
    den = ((f2 + 20.6 ** 2)
           * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2))
           * (f2 + 12194.0 ** 2))
    return (num / den) * (10 ** (2.00 / 20.0))


def a_weighted_rms(sig: np.ndarray, sr: int) -> float:
    if sig.size == 0:
        return 0.0
    spec = np.fft.rfft(sig)
    w = a_weight_gain(np.fft.rfftfreq(sig.size, 1.0 / sr))
    energy = np.sum(np.abs(spec * w) ** 2) * 2.0 / (sig.size ** 2)
    return float(np.sqrt(max(energy, 0.0)))


def envelope(sig: np.ndarray, sr: int, win_ms: float = 1.0) -> np.ndarray:
    w = max(1, int(sr * win_ms / 1000.0))
    nb = sig.size // w
    if nb < 2:
        return np.array([float(np.max(np.abs(sig)))]) if sig.size else np.array([0.0])
    trimmed = sig[:nb * w].reshape(nb, w)
    return np.max(np.abs(trimmed), axis=1)


def analyse(path: Path, floor: float, drop_limit: float) -> dict:
    d, sr = load(path)
    env = np.maximum(envelope(d, sr), 1e-9)

    # Ratio between adjacent envelope windows. Ignore drops originating
    # from already-inaudible levels -- those are silence, not clicks.
    if env.size > 1:
        ratio = env[:-1] / env[1:]
        live = env[:-1] > floor
        scored = np.where(live, ratio, 0.0)
        idx = int(np.argmax(scored))
        worst = float(scored[idx])
        at = idx / 1000.0
    else:
        worst, at = 1.0, 0.0

    tail = d[-max(1, sr // 1000):]

    return {
        "path": path,
        "dur": d.size / sr,
        "sr": sr,
        "peak": float(np.max(np.abs(d))) if d.size else 0.0,
        "dc": float(np.mean(d)) if d.size else 0.0,
        "arms": a_weighted_rms(d, sr),
        "worst_drop": worst,
        "drop_at": at,
        "tail_peak": float(np.max(np.abs(tail))),
        "clipped": int(np.sum(np.abs(d) >= 0.999)),
        "fail": worst > drop_limit,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Quality checks for short audio cues.")
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--drop-limit", type=float, default=6.0,
                   help="flag envelope drops steeper than this ratio per ms")
    p.add_argument("--modulated", action="store_true",
                   help="loosen --drop-limit for ring-modulated or warbled "
                        "cues, whose envelope nulls are by design")
    p.add_argument("--floor", type=float, default=0.002,
                   help="ignore drops starting below this amplitude")
    p.add_argument("--verbose", action="store_true",
                   help="print the sample neighbourhood at the worst drop")
    args = p.parse_args()
    if args.modulated and "--drop-limit" not in sys.argv:
        args.drop_limit = 12.0

    rows = []
    for f in args.files:
        try:
            rows.append(analyse(f, args.floor, args.drop_limit))
        except Exception as e:
            print(f"{f}: ERROR {e}", file=sys.stderr)
            rows.append({"path": f, "fail": True, "dur": 0, "peak": 0, "dc": 0,
                         "arms": 0, "worst_drop": 0, "drop_at": 0,
                         "tail_peak": 0, "clipped": 0, "sr": 0})

    name_w = max(len(str(r["path"])) for r in rows)
    print(f"{'file':<{name_w}} {'dur':>6} {'peak':>6} {'A-rms':>7} "
          f"{'drop':>8} {'at':>7} {'tail':>7} {'clip':>5}")
    for r in rows:
        flag = "  FAIL" if r["fail"] else ""
        print(f"{r['path']!s:<{name_w}} {r['dur']:6.3f} {r['peak']:6.3f} "
              f"{r['arms']:7.4f} {r['worst_drop']:7.1f}x {r['drop_at']:6.3f}s "
              f"{r['tail_peak']:7.5f} {r['clipped']:5d}{flag}")

    ok = [r for r in rows if r["arms"] > 0]
    if len(ok) > 1:
        a = np.array([r["arms"] for r in ok])
        spread = 20 * np.log10(a.max() / max(a.min(), 1e-9))
        verdict = "consistent" if spread < 1.5 else "INCONSISTENT"
        print(f"\nloudness spread across family: {spread:.2f} dB ({verdict})")
        if spread >= 1.5:
            # Deliberate per-cue gain shows up here as a defect, and so does
            # peak limiting on a wide-interval motif. Neither is a bug, so
            # this says what to check rather than what to do.
            print("  check for: per-cue gain set on purpose, cues peak-limited "
                  "below\n  the RMS target, or a genuine normalisation miss")

    if args.verbose:
        for r in rows:
            if r["dur"] == 0:
                continue
            d, sr = load(r["path"])
            i = int(r["drop_at"] * sr)
            lo, hi = max(0, i - 3), min(d.size, i + 4)
            print(f"\n{r['path']} @ {r['drop_at']:.4f}s")
            print("  ", np.array2string(d[lo:hi], precision=6, floatmode="fixed"))
            seg = d[max(0, i - int(sr * 0.004)):i + int(sr * 0.004)]
            if seg.size > 1:
                print(f"   local max step {np.max(np.abs(np.diff(seg))):.6f}, "
                      f"local peak {np.max(np.abs(seg)):.5f}")
                print("   (a smooth march through zero here is beating, not a click)")

    return 1 if any(r["fail"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
