# Usage

Full reference for `earcongen.py` and `earconcheck.py`. For *why* the
defaults are what they are, see [README.md](README.md).

---

## Contents

- [Concepts](#concepts)
- [earcongen.py reference](#earcongenpy-reference)
- [Recipes](#recipes)
- [The spec file](#the-spec-file)
- [Voice modulation](#voice-modulation)
- [Extending: shortening behaviour](#extending-shortening-behaviour)
- [Extending: voices, scales, contours](#extending-voices-scales-contours)
- [earcongui.py reference](#earconguipy-reference)
- [earconcheck.py reference](#earconcheckpy-reference)
- [Integrating a theme into an application](#integrating-a-theme-into-an-application)
- [Troubleshooting](#troubleshooting)
- [Ideas for extending the tool](#ideas-for-extending-the-tool)

---

## Concepts

Five things determine what comes out. The first three are shared across a
whole family and give it its identity; the last two vary per cue and make
members distinguishable.

**Voice** — the timbre. Partial ratios, their relative amplitudes, how
fast each decays, attack and decay times, and optional FM colouring.
Shared by the family.

**Scale** — the set of pitches every note is drawn from. Shared by the
family. Pentatonic by default so overlapping cues never clash.

**Root and band** — `--root` sets the reference pitch; `--floor` and
`--ceiling` constrain where fundamentals may land. If a motif would fall
outside the band, the *whole motif* transposes by octaves until it fits,
which preserves its interval structure and therefore its recognisability.

**Contour** — the shape of one cue, expressed as scale-degree offsets.
`rise3` is `[0, 2, 4]`: three notes ascending. This is the primary way
cues differ from each other.

**Root offset** — shifts one cue's whole motif up or down within the
scale. Two cues can share a contour and still be distinguishable if they
sit in different registers.

A **family** is a list of `(slug, contour, root_offset)` triples plus
optional per-cue overrides. The default family is eight cues; edit it in
the script or supply your own with `--spec`.

---

## earcongen.py reference

### Output

| Flag | Default | Meaning |
|---|---|---|
| `--out DIR` | `audio/chime` | output directory, created if absent |
| `--stereo` | off | write dual-mono instead of mono |
| `--play` | off | audition each file after writing it |

Files are named from each spec's `slug`, so the default family writes
`earcon01.wav` … `earcon08.wav`. Other families use namespaced slugs
(`ui_open.wav`, `sys_boot.wav`), so several themes can share one output
directory without colliding.

`--play` uses whatever it can find: `afplay` on macOS, `winsound` on
Windows, then `paplay` / `aplay` / `ffplay` on Linux. If none is present
it says so and carries on writing files.

### Family identity

| Flag | Default | Meaning |
|---|---|---|
| `--voice NAME` | `chime` | timbre; see `--list-voices` |
| `--family NAME` | `core` | which set of cues to generate; see `--list-families` |
| `-n`, `--note-count N` | unset | cap every motif at N notes |
| `--cap-mode MODE` | `redesign` | how `-n` shortens: `redesign` or `truncate` |
| `--scale NAME` | `major_pent` | pitch set; see below |
| `--root HZ` | `523.25` | reference pitch (C5) |
| `--floor HZ` | `480.0` | lowest permitted fundamental |
| `--ceiling HZ` | `1150.0` | highest permitted fundamental |

Families: `core`, `ui`, `system`, `message`, `progress`, `droid`,
`droid_full`, `all`. `core` is the original eight and its output is
unchanged. `all` concatenates every non-droid cue for auditioning and is
not a set to ship.

`--cap-mode redesign` (the default) substitutes a purpose-built shape of
the requested length from the `REDUCTIONS` table, preserving what each
contour means, then separates any cues that still collide by moving them
into a different register, in the direction their character implies.

`--cap-mode truncate` cuts each contour short instead. Openings survive
exactly; cues that differ only after the cut point do not. The casualties
are named on stderr and generation continues:

```
$ ./earcongen.py -n 1 --cap-mode truncate
  warning: -n 1 makes these identical: earcon01, earcon02  (--cap-mode redesign separates them)
```

Both modes report on the pitches that actually come out rather than on
scale degrees, which matters more than it sounds: `fit_to_range` folds
every motif into the band by whole octaves, so two cues five degrees apart
on a pentatonic are the *same frequency*. Comparing degrees would call
them separated and be wrong.

That folding also sets a hard ceiling on one-note families. The default
band holds six distinguishable pitches, so an eight-cue family cannot
survive `-n 1` however it is arranged. The tool reports the shortfall and
the figure rather than quietly writing duplicates; widen the band, raise
the cap, or ship fewer cues.

Per-cue overrides live in the spec file as `note_count`, which wins over
the flag.

Scales: `major_pent`, `minor_pent`, `hirajoshi`, `kumoi`, `whole_tone`,
`chromatic`.

`chromatic` deliberately discards the guarantee that any two
simultaneously-sounding cues are consonant. It exists for `--r2-full`,
where speech-like arbitrariness is the point.

`minor_pent` reads as more serious than `major_pent` without being
mournful. `hirajoshi` is distinctly ceremonial. `whole_tone` is
ambiguous and floating — no strong tonal centre, which suits products that
want cues to feel neutral rather than cheerful.

### Timing and envelope

| Flag | Default | Meaning |
|---|---|---|
| `--note-ms MS` | voice's own decay | note decay length |
| `--gap-ms MS` | `150.0` | onset-to-onset spacing within a motif |
| `--tail-ms MS` | `250.0` | ring-out appended after the last onset |
| `--attack-ms MS` | voice's own | override attack time |
| `--decay-ms MS` | voice's own | override decay time |
| `--glide-ms MS` | voice default | portamento between notes |
| `--ring-depth 0-1` | voice default | ring modulation wet mix |
| `--vib-cents N` | voice default | warble depth |
| `--release-ms MS` | `60.0` | raised-cosine release at end of file |

`--note-ms` sets the **decay time**, not a truncation point. Notes always
render through to the end of the buffer so nothing is ever cut off
mid-oscillation. Lowering it makes notes shorter and tighter; raising it
makes them ring.

`--gap-ms` below `--note-ms` means notes overlap and blend, which is what
a real instrument does and generally sounds better. Above it, notes are
separated by silence, which reads as more deliberate and more urgent.

`--release-ms` should not normally need changing. Raise it if you hear a
click at the end of a file; lower it only if you want a deliberately
abrupt ending and have verified with `earconcheck.py` that it's clean.

### Loudness

| Flag | Default | Meaning |
|---|---|---|
| `--target-rms X` | `0.11` | A-weighted RMS normalisation target |
| `--gain X` | `1.0` | family-wide multiplier on the above |
| `--peak X` | `0.80` | hard peak ceiling applied after normalisation |

Normalise the family here, then let the *application* provide a single
user-facing volume control. Do not try to set per-cue volumes in the
generator except through each spec's `gain` field, and then only to make a
deliberately more or less prominent cue — not to fix a balance problem,
which A-weighting has already handled.

The `--peak` headroom exists because these files will be mixed with other
audio downstream. Generating at 0.99 leaves nothing for the host.

### Information

| Flag | Meaning |
|---|---|
| `--list-voices` | voices with their attack/decay and character |
| `--list-contours` | contour names, lengths, and degree offsets |
| `--list-families` | every family with its cues, contours, and labels |
| `--list-presets` | presets and the options each sets |
| `--dump-spec` | print the selected family as JSON (honours `--family`) |
| `--notes` | the design reasoning, condensed |
| `--spec FILE` | use a family definition from JSON |
| `--preset NAME` | apply a named bundle of options |
| `--r2`, `--r2-full` | shorthand for the astromech presets |

A preset only sets options you did not set yourself, so `--r2 --voice
marimba` keeps the droid phrasing and takes the marimba timbre. This is
decided by inspecting the command line, not by comparing values, so
setting a flag to what happens to be its default still counts as setting
it.

---

## Recipes

```bash
# Tight and businesslike. Short notes, close spacing, no ceremony.
./earcongen.py --voice marimba --note-ms 190 --gap-ms 130 --tail-ms 150

# Ceremonial. Long tails, wide spacing, unusual scale.
./earcongen.py --voice bell --scale hirajoshi --gap-ms 220 --tail-ms 400

# Warmer, sits lower in the mix.
./earcongen.py --voice chime --floor 380 --ceiling 800 --root 392.00

# More presence, for cues that must not be missed.
./earcongen.py --voice alert --gain 1.15 --attack-ms 10

# Deliberately gentle: slow attack is the whole trick.
./earcongen.py --voice glass --attack-ms 45 --gap-ms 260

# A UI set: dense, quiet, low ceremony. These fire many times an hour.
./earcongen.py --family ui --voice marimba --note-ms 190 --gap-ms 120

# A system set: rare events, so they can afford weight.
./earcongen.py --family system --voice bell --gap-ms 220 --tail-ms 400

# Terser without losing contour. Two notes still carry rise vs fall.
./earcongen.py -n 2 --gap-ms 110 --tail-ms 160

# Droid phrasing with a wooden timbre — presets yield to explicit flags.
./earcongen.py --r2 --voice marimba --out audio/r2-wood

# Unleashed, but pulled back out of the shrillest part of the band.
./earcongen.py --r2-full --ceiling 2000 --out audio/r2-tamer

# Generate every voice into its own theme directory for A/B comparison.
for v in chime bell marimba glass pluck alert droid; do
    ./earcongen.py --voice "$v" --out "audio/$v"
done
./earconcheck.py audio/*/*.wav

# Every family in one timbre, to hear whether the catalogue hangs together.
for f in core ui system message progress; do
    ./earcongen.py --family "$f" --voice chime --out "audio/$f"
done
```

Useful reference pitches for `--root`: G4 392.00, A4 440.00, C5 523.25,
D5 587.33, E5 659.25, G5 783.99.

---

## The spec file

```bash
./earcongen.py --dump-spec > family.json
```

```json
[
  {
    "slug": "earcon01",
    "contour": "rise3",
    "root_offset": 0,
    "note_ms": null,
    "gap_ms": null,
    "gain": 1.0,
    "label": "positive / opportunity found"
  }
]
```

| Field | Meaning |
|---|---|
| `slug` | output filename stem |
| `contour` | name from `--list-contours` |
| `root_offset` | scale degrees to shift this motif; negative goes down |
| `note_ms` | per-cue decay override; `null` uses the family default |
| `gap_ms` | per-cue spacing override; `null` uses the family default |
| `gain` | relative loudness within the family |
| `note_count` | per-cue note cap; `null` uses `--note-count` |
| `label` | documentation only; printed while generating |

Design guidance for building a family:

**Related events should share a contour opening.** Two cues in the same
category read as siblings if they start the same way and resolve
differently — `rise3` and `rise_hold` in the default family. This is
better than giving them entirely different sounds, because the listener
learns one category and one distinction rather than two unrelated sounds.

**Opposed events should have opposed contours.** If one cue rises, its
counterpart should fall. Do not distinguish them by pitch alone; contour
survives noise, distraction, and cheap speakers in a way absolute pitch
does not.

**Keep a family under about eight.** Beyond that, people stop reliably
telling members apart and start ignoring the whole set. If you need more
than eight distinct events, the right move is usually to group them into
categories and give each category one cue, not to design a ninth sound.

**Reserve `alarm` and high registers.** Whatever you assign as your most
urgent cue stops being urgent as soon as a second cue sounds equally
urgent.

---

## Voice modulation

Five fields drive the droid character and are available to any voice. All
default to zero, so every voice that predates them is bit-for-bit
unchanged — a constant-pitch note still takes the closed-form phase path,
and only modulating voices pay for phase integration.

| Field | Effect |
|---|---|
| `glide_ms` | portamento into each note from the previous pitch |
| `sweep_cents` | per-note bend across the note's own decay time |
| `vib_hz`, `vib_cents` | warble rate and depth |
| `ring_ratio`, `ring_depth` | ring modulator frequency ratio and wet mix |
| `noise_amt` | servo/breath noise under the partials |

A non-integer `ring_ratio` is what makes it read as a machine attempting
speech: it places sum and difference tones where no harmonic series would
put them. Above about `0.6` for `ring_depth` it turns harsh. Noise is
deterministically seeded from the note frequency, so repeat runs are
identical.

Glides interpolate in log-frequency space, eased with a raised cosine.
Linear interpolation in Hz sounds like a machine sweeping; this sounds
like a voice bending, which is the difference worth having.

## Extending: shortening behaviour

Two tables in `earcongen.py` govern what a note cap does. They are
separate because they do different jobs.

`REDUCTIONS` is authored. It maps a contour name to the shape it becomes
at each shorter length, and it preserves meaning — it cannot preserve
distinctness, because distinctness is a property of a family rather than
of a contour. Adding an entry is one line:

```python
REDUCTIONS["my_contour"] = {3: [0, 2, 5], 2: [0, 5]}
```

A missing length falls back to truncation, which is right where the
opening genuinely is the whole idea. Length 1 is never authored: it is
always a single note, and register does the work.

`CONTOUR_CHARACTER` says what a contour is *for* — `rise`, `fall`,
`level`, `updown`, `downup` or `chatter`. It changes nothing about the
sound and exactly one thing about behaviour: which way a cue moves when
register separation has to shift it. Every contour must appear in it, and
a test enforces that, because a missing entry silently means `level`.

## Extending: voices, scales, contours

### Adding a voice

Add an entry to `VOICES` in `earcongen.py`:

```python
"woodblock": Voice(
    "woodblock",
    ratios=[1.00, 2.41, 4.10],   # frequency multipliers of the fundamental
    amps=[1.00, 0.30, 0.09],     # relative amplitude of each partial
    decays=[1.0, 2.4, 3.8],      # >1 decays faster than the fundamental
    attack_ms=4.0,
    decay_ms=180.0,
    blurb="dry, percussive, very short",
),
```

Guidance from the physics:

- **Harmonic** ratios (1, 2, 3, 4…) sound pitched and musical. **Inharmonic**
  ratios sound metallic and bell-like. Real marimba bars are 1 : 3.9 : 9.2;
  real tubular bells are close to 0.56 : 0.92 : 1.19 : 1.71 : 2.0.
- Amplitudes should fall off with partial number. A partial louder than the
  fundamental makes the perceived pitch ambiguous.
- Higher partials should decay faster (`decays` increasing). This is what
  physical objects do, and skipping it makes the tone seem to brighten as
  it fades.
- `fm_index` above 0 enables FM colouring: a brighter onset that mellows
  as `fm_decay` runs. Values above about 3 get buzzy fast.

### Adding a contour

```python
CONTOURS["rise4"] = [0, 1, 2, 4]
```

Offsets are scale degrees, not semitones, so a contour keeps its character
across every scale. Three notes is usually the practical maximum — four
starts sounding like a melody and takes long enough that it feels slow.

### Adding a scale

```python
SCALES["insen"] = [0, 1, 5, 7, 10]
```

Semitone offsets within an octave. If you add a scale containing semitone
intervals, be aware you have given up the guarantee that any two
simultaneously-sounding cues are consonant.

---

## earcongui.py reference

The window exposes every generation option in the reference above and adds
nothing of its own to the audio. Anything it can produce, the command line
can produce; the difference is how quickly you can hear the result.

```bash
pip install -r requirements-gui.txt
./earcongui.py
./earcongui.py --cli version    # print the datestamp and exit; no Qt loaded
```

### Preset, Custom, and Start from

| Mode | Controls | Start from |
|---|---|---|
| a named preset | filled in and locked | hidden |
| `Custom` | yours | shown |

Choosing a preset writes its values into every control and disables them.
It does not hide them, and it resets settings the preset does not mention
back to their defaults first — otherwise a preset inherits whatever the
previous experiment left behind and no two runs of it match.

`Custom` re-enables everything and reveals **Start from**, which loads a
preset's values as a baseline. That overwrites every control, so it is a
starting point rather than a modifier: pick it first, then adjust.

### Controls

Each numeric setting has a slider and a spin box over the same value. The
slider moves in units of that setting's step, so every notch is a value
the box can represent exactly. Related settings share a range on purpose:
the frequency controls all run 100-4000 Hz, the two note-length controls
both run 40-2000 ms, spacing and ring-out share 0-1200 ms, attack and
release share 0-300 ms. The spin box reaches values the slider cannot hit
precisely; both are clamped to the same bounds.

Settings whose command-line default is "whatever the voice does" —
`--note-ms`, `--attack-ms`, `--decay-ms`, `--glide-ms`, `--ring-depth`,
`--vib-cents` — carry a checkbox. Unticked, the voice decides.

Every control and every part of it carries a tooltip explaining what the
setting does and why the default is what it is.

### Destination

Files are written to a subfolder inside a base directory. The subfolder
follows the preset or voice name until you type your own, after which it
is left alone. Only the final component of what you type is used, so a
path with separators in it cannot escape the base directory.

Defaults, per platform:

| | Base output | Settings |
|---|---|---|
| Linux | `$XDG_DOCUMENTS_DIR`, else `~/Documents` or `~/Music` | `$XDG_CONFIG_HOME/earcongen` |
| macOS | `~/Documents/earcongen` | `~/Library/Application Support/earcongen` |
| Windows | `%USERPROFILE%\Documents\earcongen` | `%APPDATA%\earcongen` |

A file named `earcongen-portable.txt` beside the binary overrides both,
keeping settings and output next to the executable.

### Playback

Select a row to hear it, or double-click. QtMultimedia is used where it
reports a working backend; otherwise the window shells out to `afplay`,
`paplay`, `pw-play`, `aplay` or `ffplay`, or uses `winsound` on Windows.
The status bar names whichever is in use. A machine with a working
`paplay` and no Qt audio plugin is a real configuration, which is why the
fallback exists rather than an error message.

Rendering happens on a worker thread. Progress is per cue and a run can be
cancelled between files; anything already written is kept.

---

## earconcheck.py reference

```bash
./earconcheck.py audio/chime/*.wav
./earconcheck.py --verbose audio/chime/earcon01.wav
```

| Flag | Default | Meaning |
|---|---|---|
| `--drop-limit X` | `6.0` | flag envelope drops steeper than this ratio per ms |
| `--modulated` | off | raise `--drop-limit` to 12.0 for ring-modulated cues |
| `--floor X` | `0.002` | ignore drops starting below this amplitude |
| `--verbose` | off | print the sample neighbourhood at the worst drop |

Reports per file: duration, peak, A-weighted RMS, worst envelope drop and
where it occurs, tail amplitude, and clipped sample count. Then reports
the **loudness spread** across the whole set in dB — under about 1.5 dB
is consistent.

Exit status is non-zero if any file fails, so it drops straight into CI.

**Reading the output.** A real click shows as an envelope drop in the
thousands or millions. Values in the 2–6× range are almost always beating
between overlapping partials passing through a zero crossing, not a
defect. Confirm with `--verbose`: if the samples march smoothly through
zero, it's beating; if they step from a nonzero value straight to zero or
reverse sign abruptly, it's a click.

It works on any 16-bit WAV, mono or stereo, so it's also the right tool
for vetting user-supplied sound files before your application accepts
them.

---

## Integrating a theme into an application

Some conventions that make generated themes easy to consume.

**One directory per theme.** `audio/chime/`, `audio/bell/`,
`audio/marimba/`. Enumerate directories to build a theme list, enumerate
files within one to build a per-cue list.

**Derive display names from paths.** `audio/chime/earcon01.wav` →
"Chime 01". Title-case the directory, strip the `earcon` prefix, keep the
zero padding so lexical sort matches numeric order. This means dropping a
new file into a directory makes it appear with no code change.

**Allow an optional manifest.** A `theme.json` in a theme directory
mapping slugs to friendlier display names lets you improve labels later
without renaming files and invalidating everyone's saved configuration.
Absent, fall back to derived names.

**Scan a user directory as well as the bundled one.** Merging
`~/.local/share/<app>/audio/` (or the platform equivalent) into the same
list lets people install whole themes, not just override single cues.

**Validate custom files at selection time, not at playback time.** Decode
the file once when the user picks it and reject it with a visible error if
it fails. A custom sound that silently never plays is the worst possible
failure mode, because nothing indicates anything is wrong.

**Store the path, display the basename.** Handle the two cases that
follow: a file that has since been moved or deleted should show as broken
and fall back to a bundled default *visibly*; two files with the same
basename from different directories should show their parent directory to
disambiguate.

**WAV for bundled assets.** No decoder dependency, `wave` is in the
standard library, and it survives freezing with PyInstaller or similar
without special handling. At 44 KB per cue, the size argument for a
compressed format doesn't apply at this scale. Accept a wider set —
WAV, FLAC, OGG — for user-supplied files, and probe MP3 support at startup
rather than assuming it.

**Provide one volume control and a preview button per cue.** The preview
button is not a nicety; it is the only practical way for someone to tune
their cue selection without contriving the events that trigger them.

---

## Troubleshooting

**A click or pop at the end of a file.** Raise `--release-ms`. If it
persists, run `earconcheck.py --verbose` to locate it — a click *inside*
the file rather than at its end usually means `--gap-ms` is large enough
that notes no longer overlap and one is being cut short.

**Cues sound harsh or startling.** Raise `--attack-ms` first. This is the
fix roughly three times out of four. If that isn't enough, lower
`--ceiling` to keep fundamentals further from the 2–4 kHz band, or switch
from `alarm`/`alert` to `chime`/`glass`.

**Cues get lost under background noise.** Try `--voice marimba` before
raising `--gain`. Legibility is usually timbre, not level. Raising the
gain makes a cue more annoying without making it easier to identify.
Narrowing the band (`--floor 600 --ceiling 900`) can also help by keeping
everything in a consistent, well-separated register.

**Two cues sound too similar.** Change one's contour rather than its
`root_offset`. Contour is the dimension people actually discriminate on;
pitch differences within a family are much weaker cues, especially at a
distance or over poor speakers.

**One cue seems louder than the rest.** Check `earconcheck.py`'s loudness
spread. If it reports under 1.5 dB, the difference you're hearing is
probably duration or attack sharpness rather than level — a short bright
cue reads as louder than a long soft one at identical A-weighted RMS.
Adjust `note_ms` or `gain` on that one spec.

**Everything sounds too long.** Lower `--note-ms` and `--tail-ms`
together. `--tail-ms` is ring-out, so trimming it alone will start cutting
into the decay and eventually reintroduce a click.

---

## Ideas for extending the tool

Things that would make this more useful, roughly in order of value for
effort.

**Polyphony testing.** Generate every pair of cues in a family playing
simultaneously with a small random offset, so you can hear what an overlap
actually sounds like. The pentatonic constraint makes overlaps
*acceptable*, but some pairs will still be better than others, and there
is currently no way to check without contriving it.

**Variation generation.** A `--variants N` flag emitting N randomised
variations of a family — small perturbations to attack, gap, root offset,
partial amplitudes — so you can audition a spread rather than tweaking one
flag at a time. Pair with `--seed` for reproducibility.

**LUFS instead of A-weighted RMS.** A-weighting is a good approximation
and is dependency-free. ITU-R BS.1770 loudness (LUFS) is the modern
standard and would be more accurate for cues with very different
durations, where A-weighted RMS under-rates short bright sounds. Needs a
gating implementation or `pyloudnorm`.

**Sample rate and bit depth options.** Currently fixed at 44.1 kHz /
16-bit. Embedded targets often want 22.05 kHz or 8-bit, and some hosts
want 48 kHz to avoid resampling.

**Compressed export.** Optional OGG/FLAC output for size-sensitive
deployments, gated behind an optional `soundfile` import so the
zero-dependency path stays intact.

**Stereo positioning.** Placing cues at different points in the stereo
field is a strong additional discrimination axis, effectively free, and
currently unused. Would want a mono-compatibility check, since many
listeners are on a single speaker.

**A listening-test harness.** Generate a randomised sequence of cues from
a family with gaps, play it, and score how reliably you identify each.
This turns "these feel distinguishable" into a number, and it is the only
honest way to know whether a family of eight is actually a family of six
plus two nobody can tell apart.

**Background-noise auditioning.** Mix cues against pink noise, engine
rumble, or a supplied ambience file at a chosen SNR before playback, so
you can evaluate legibility in the environment the cues will actually be
used in rather than in silence.

**Envelope shapes beyond exponential.** Some percussion has a double
decay — a fast initial drop into a slower tail. Supporting a two-stage
decay would widen the timbral range meaningfully for little code.

**A spectrogram/waveform dump.** `--plot` writing a PNG per cue would make
the click and envelope behaviour visible, which is a much faster debugging
loop than reading numbers from `earconcheck.py`.
