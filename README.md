# earcongen

Generate a family of notification sounds that belong together, stay
individually distinguishable, and don't make people want to turn them off.

```
./earcongen.py --voice chime --out audio/chime
```

Requires Python 3.10+ and numpy. Nothing else. Writes 16-bit mono WAV.

---

## What this is

An **earcon** is a short non-speech audio cue standing in for a message —
the sound your phone makes for a new message, the chime a car makes when
you leave the lights on, the ascending blip when a transfer finishes.

Most software ships bad ones. Not because good ones are hard to make, but
because they're almost always chosen *one at a time*: someone needs a
notification sound, grabs a sample or generates a beep, ships it. Six
months later someone else needs a different notification sound and repeats
the process. The result is a set of cues that don't sound related, aren't
balanced against each other, and are individually a bit irritating in ways
nobody can quite articulate.

Earcons work best designed as a **set**, with shared identity and
deliberate contrast. That's what this tool does. You choose a timbre, a
scale, and a frequency band; it emits a family whose members are obviously
siblings but never confusable, all normalised so they sound equally loud.

It is a design instrument, not a one-shot generator. The intended workflow
is to run it, listen, change a flag, run it again — twenty times in an
afternoon until the set feels right.

## What it is not

- Not a sampler or a synthesiser you play. There's no MIDI, no realtime.
- Not for music. Motifs are two or three notes and cap out near a second.
- Not for speech, alarms that must loop, or anything safety-critical.
  A cue that must be heard through hearing protection in a factory is a
  different engineering problem with standards attached.

---

## Install

The command-line tools need Python 3.10+ and numpy, and nothing else.

```bash
git clone https://github.com/drworman/earcongen.git
cd earcongen
pip install -r requirements.txt   # numpy, and only numpy
./earcongen.py --notes            # the design reasoning, condensed
```

For the window, add Qt:

```bash
pip install -r requirements-gui.txt
./earcongui.py
```

The two are kept separate on purpose: installing the generator should not
pull in 60 MB of Qt, and the scripts should stay copyable into a project
that has no interest in a GUI.

Prebuilt binaries for Linux, Windows and macOS are attached to each
[release](https://github.com/drworman/earcongen/releases). They contain
the window and carry the command-line scripts alongside, so the archive is
the whole project rather than just the interface.

## Quick start

```bash
# Generate the default eight-cue family with the default voice
./earcongen.py --out audio/chime

# Same family, different identity
./earcongen.py --voice bell --scale hirajoshi --out audio/bell
./earcongen.py --voice marimba --note-ms 190 --gap-ms 130 --out audio/marimba

# Audition as they're written
./earcongen.py --voice chime --out audio/chime --play

# Pick a different set of cues for a different problem domain
./earcongen.py --family ui --voice marimba --out audio/ui
./earcongen.py --family system --voice bell --out audio/system

# Shorten every motif (see "Shortening motifs" below for the catch)
./earcongen.py -n 2 --out audio/short

# Astromech presets
./earcongen.py --r2 --out audio/r2            # in-band, still well behaved
./earcongen.py --r2-full --out audio/r2-full  # chromatic, wide, unrepentant

# See what's available
./earcongen.py --list-voices
./earcongen.py --list-contours
./earcongen.py --list-families
./earcongen.py --list-presets

# Define your own set
./earcongen.py --dump-spec > family.json
$EDITOR family.json
./earcongen.py --spec family.json --out audio/custom

# Check the output for clicks, DC offset, and loudness consistency
./earconcheck.py audio/chime/*.wav
```

---

## The window

`./earcongui.py` puts every setting on one form and the generated files
next to it, because the loop this tool is built around — generate, listen,
change one thing, generate again — is only as fast as its slowest step.

- **Every setting has a slider and a numeric entry** over the same value.
  Related settings share a range deliberately, so sliders stacked above
  one another can be compared by eye rather than by reading their numbers.
- **Settings that mean "leave it to the voice"** have a checkbox, so the
  difference between an attack of 20 ms and whatever this voice does is
  visible rather than implied by a magic value.
- **Choosing a preset fills in every control and locks them.** It does not
  hide them. If you pick `r2` and wonder why it sounds like that, the
  answer is on the form: the voice changed, the scale changed, the band
  widened, the spacing tightened.
- **Custom unlocks everything** and reveals a *Start from* picker, which
  loads a preset's values as a baseline you are free to ruin.
- **Everything has a tooltip**, carrying the reasoning rather than just
  the units — the same reasoning as the sections below.
- **Select a cue to hear it**, or double-click it. Playback uses Qt where
  it works and falls back to whatever player the system has.
- **Rendering runs off the interface thread**, so a long ring-out or the
  thirty-four-cue `all` set does not freeze the window mid-experiment.

Output goes to a subfolder of a base directory you choose; the subfolder
follows the preset or voice name until you type your own. Settings and
output default to the conventional locations for the platform — Roaming
AppData, Application Support, or `$XDG_CONFIG_HOME` — unless a file named
`earcongen-portable.txt` sits beside the binary, in which case both stay
next to the executable.

The window is a front end and nothing more. It reads its defaults, its
choices and its bounds from `earcongen.py`'s own argument parser, so
adding a voice or moving a default needs no change here; a test fails if
the two ever disagree.

## The design principles

These are the reasons the defaults are what they are. They're also the
things worth understanding before you override them, because most of the
ways to make an earcon annoying are the ways to make it *feel* more
attention-getting.

### Envelope beats pitch

This is the single biggest lever, and it's the one people reach for last.

A sound with an attack under about 5 ms reads as a *click* or a *beep* —
a broadband transient. The auditory system treats sudden onsets as
potentially threatening, and you get a small startle response every time.
An attack of 15–40 ms rising into a long exponential decay reads as a
**struck object**: a bell, a glass, a marimba bar. You notice it just as
reliably, and nothing in your body flinches.

This is most of the difference between a cheap piezo beep and a
notification sound you can live with for years. If a tone irritates you,
raise `--attack-ms` before you touch anything else.

The decay matters too, but less. Exponential decay (what physical objects
do) sounds natural; linear decay sounds synthetic; no decay at all — a
tone that just stops — is a click at the far end, which is a separate
problem covered below.

### Stay out of 2–4 kHz

The ear is most sensitive between roughly 2 and 4 kHz. It's also where
sirens, smoke alarms, screams, and infant cries live, which is not a
coincidence — that band is evolutionarily privileged for distress signals.

Putting a routine notification there borrows an urgency it hasn't earned,
and it's the main reason so many notification sounds feel stressful. The
default band here is **480–1150 Hz**: comfortably audible, above most
low-frequency ambient noise (engines, HVAC, traffic, room tone), and below
the shrill zone.

If a cue genuinely needs to convey emergency, go up. But use that deliberately
and rarely, because it stops working once everything is up there.

### Timbre: harmonics, not pure tones

A pure sine sounds synthetic and gets fatiguing fast — there's nothing for
the ear to latch onto and it doesn't resemble anything physical. A
fundamental plus two or three quieter harmonics reads as an instrument and
is softer at the same measured loudness.

Higher partials should decay *faster* than the fundamental, which is what
real struck objects do. The `decays` list in each voice controls this.
Skip it and the tone sounds like it's getting brighter as it fades, which
is subtly wrong in a way people notice without identifying.

### Motifs, not single beeps

Two or three notes are dramatically more distinguishable and memorable
than one. A single tone can only vary in pitch and timbre; a motif varies
in **contour**, and contour carries meaning that people read without
being taught:

| Contour | Reads as |
|---|---|
| Rising | opportunity, success, permission granted |
| Falling | attention, warning, a state degrading |
| Level / repeated | neutral status, acknowledgement |
| Up-then-down | a milestone reached, something completed |
| Wide upward leap | a gate opening, now-clear |

Used consistently, the vocabulary is learnable in a day and you stop
needing to look at the screen. This is the actual payoff of designing a
set rather than picking sounds individually.

### Shortening motifs

`-n` / `--note-count` caps every motif at N notes. How it does that is
`--cap-mode`, and the two modes are genuinely different.

**`redesign`, the default**, asks what each contour *means* and swaps in a
purpose-built shape of the requested length that still means it. A big
rise stays a big rise rather than becoming a small one; an arch still
returns to where it started. Where two cues still land on the same shape,
one is moved to a different register — upward for a rising cue, downward
for a falling one, so the nudge reinforces the meaning instead of fighting
it.

**`truncate`** simply cuts each contour short. Every cue keeps its opening
exactly as designed, at the cost that contours differing only after the
cut point become the same sound. That is sometimes what you want, and it
is never a surprise, because the casualties are named:

```
$ ./earcongen.py -n 1 --cap-mode truncate
  warning: -n 1 makes these identical: earcon01, earcon02  (--cap-mode redesign separates them)
```

The difference is measurable rather than theoretical. Every shipping
family stays fully distinct under `redesign` at two notes or more, where
truncation loses cues:

| Family, capped to 2 notes | `truncate` | `redesign` |
|---|---|---|
| `core` | 7 of 8 distinct | **8 of 8** |
| `ui`, `system`, `droid` | 7 of 8 distinct | **8 of 8** |

### The one-note limit is physical

At a single note there is only one possible shape, so register carries
everything — and how many registers exist is fixed by the band and the
scale, not by how cleverly the tool arranges them. A pentatonic has five
notes per octave and the default 480–1150 Hz band is barely wider than one
octave, which is **six distinguishable pitches**. Ask eight cues to fit
into six and two of them cannot, so the tool says so and says what would
help:

```
$ ./earcongen.py -n 1
  note: shortening left these sharing a shape, so they were separated by
  register: earcon02 +0->+5
  warning: no register left for earcon05, earcon08. A 480-1150 Hz band on the
  major_pent scale holds 6 distinguishable pitches, and 8 cues at 1 note need
  more than that. Widen the band, raise -n, or ship fewer cues.
```

Widening to 300–2400 Hz gives fifteen pitches and all eight come out
distinct. That is the honest trade: one-note cues cost you the quiet part
of the spectrum. Reach for `-n 1` when something forces your hand — a
flash budget, a host that truncates at 200 ms, a context where a
three-note motif reads as slow — not because shorter seems tidier.

### One pitch set for the whole family

Every note is drawn from a single pentatonic scale. This is a **practical**
decision, not an aesthetic one.

Two cues will eventually fire within a second of each other. You cannot
prevent it and you shouldn't try. Any two notes drawn from a pentatonic
scale sound acceptable together, so an accidental overlap sounds like a
coincidence rather than a mistake. Draw from a chromatic set, or from
whatever frequencies happened to seem right, and you will sooner or later
produce a minor second or a tritone at exactly the wrong moment — and
there's nothing you can do about it downstream.

Pentatonics have no semitone intervals at all, which is precisely why
they're forgiving. `--scale whole_tone` is also included and is similarly
safe; it sounds more ambiguous and floating, which suits some products.

### Normalise by perceived loudness, not peak

A 1 kHz tone and a 500 Hz tone at the same peak amplitude do not sound
equally loud. The ear's sensitivity varies by well over 10 dB across the
range these cues occupy.

Normalising by peak or by plain RMS produces a family that feels
unbalanced no matter how carefully each member was designed — one cue
always seems to shout and another always seems timid. This tool normalises
by **A-weighted RMS**, which approximates the ear's frequency response, so
the whole family lands at the same perceived level. You can verify it:
`earconcheck.py` reports the loudness spread across a set in dB.

### Nothing loops, nothing runs long

Looping is what makes alarms unbearable. A cue that repeats until
acknowledged converts a notification into a demand, and people respond by
disabling the whole system rather than the one cue.

Everything here is one-shot. Most cues land under a second; the
long-tailed voices are deliberately longer (`bell` around 1.5 s, `glass`
around 2 s at their defaults) because a slow ring-out is the point of
those timbres. Trim with `--note-ms` and `--tail-ms` if that's too much
for your context.

If something is important enough that the user must not miss it, solve
that with timbre, contour, and repetition *policy* in your application —
not by making the sound file longer.

### Ending a sound is harder than starting one

Cutting a decaying tone off before it reaches silence produces a click,
even when the amplitude at the cut is only a few percent. The step from
some nonzero value to digital silence is a broadband transient, and the
ear is very good at detecting exactly that.

This is easy to get wrong and easy to miss when inspecting waveforms:
checking the last sample of a file will happily pass a click that occurs
250 ms earlier. Two things are needed —

1. Let the envelope decay naturally past the nominal note length rather
   than truncating it. Render length and note length are different things.
2. Apply a **raised-cosine** release at the end, not a linear fade. A
   linear ramp is continuous in value but not in slope, and that corner is
   audible on a quiet tail. A cosine ramp is continuous in both.

`earconcheck.py` exists specifically to catch this class of defect. Run it
on anything you generate, and on any sound file a user supplies to your
application.

---

## Families

Cues are organised into sets, chosen with `--family`. The default is
`core`, the original eight, and its output is unchanged from previous
versions.

| Family | Cues | For |
|---|---|---|
| `core` | 8 | the generic default; slugs stay `earcon01`–`earcon08` |
| `ui` | 8 | direct manipulation — open, close, select, confirm, toggle |
| `system` | 8 | machine state — boot, connect, update, battery, job done |
| `message` | 5 | interruptions from people — incoming, sent, mention, call |
| `progress` | 5 | long operations — start, tick, complete, stalled, abort |
| `droid` | 8 | astromech vocabulary — affirm, negate, query, scan, alert |
| `droid_full` | 8 | the same slugs with longer, wilder phrasing |
| `all` | 34 | every non-droid cue at once, for auditioning |

Slugs are namespaced per family, so several themes can be generated into
one directory without colliding. `all` exists so you can hear the whole
catalogue in one pass — it is not a set anyone should ship. The guidance
in USAGE.md still stands: past about eight cues people stop telling
members apart, so the answer to needing more is to pick a **different**
eight, not to ship sixteen.

Run `./earcongen.py --list-families` for the full contents with contours
and labels, and `--dump-spec --family ui` to get one as editable JSON.

## Presets

A preset is a named bundle of flag values. It only fills in options you
did not set yourself, so `--r2 --voice marimba` gives you droid phrasing
with a wooden timbre, exactly as it reads.

```bash
./earcongen.py --r2 --out audio/r2
./earcongen.py --r2-full --out audio/r2-full
./earcongen.py --list-presets
```

Both presets deliberately break rules stated above. Astromech
vocalisations are ring-modulated, glide between pitches, warble, and run
to six or seven blips; `--r2-full` additionally goes chromatic and climbs
into the 2–4 kHz band this tool otherwise avoids. That is expressive, and
it is a bad choice for a cue that fires forty times a day.

`--r2` is the version that still behaves: in-band, pentatonic, phrases
capped where a notification sound should be capped. `--r2-full` is for
when character is the point and listener fatigue is not your problem.

The synthesis is original — three new modulation parameters on the voice,
no samples involved. The sounds are astromech *in the sense that a
ring-modulated glide is*, not in the sense of reproducing anything.

Ring modulation drives the signal through zero at the difference
frequency, which looks like an envelope discontinuity to the checker.
Use `./earconcheck.py --modulated` on droid output.

## Voices

| Voice | Character | Good for |
|---|---|---|
| `chime` | soft harmonic, gentle | low-urgency default |
| `bell` | inharmonic, long tail | unmistakable, ceremonial |
| `marimba` | woody, short, legible | noisy environments |
| `glass` | airy, very long tail | ambient, low urgency |
| `pluck` | string-like, tight | frequent, unobtrusive events |
| `alert` | FM sheen, more presence | things that must not be missed |
| `alarm` | bright, fast | use sparingly; this one nags |
| `sine` | pure tone reference | A/B comparison only |

`marimba` is the one to reach for when a cue keeps getting lost under
background noise. Legibility is usually a timbre problem, not a volume
problem — raising the gain makes a cue more annoying without making it
easier to identify.

---

## Extending the character

Three voice parameters were added for the droid presets and are available
to any voice you write:

| Field | Effect |
|---|---|
| `glide_ms` | portamento into each note from the previous pitch |
| `sweep_cents` | per-note bend across the note's decay |
| `vib_hz` / `vib_cents` | warble rate and depth |
| `ring_ratio` / `ring_depth` | ring modulation frequency ratio and wet mix |
| `noise_amt` | servo/breath noise mixed under the partials |

All default to zero, so every pre-existing voice is bit-for-bit unchanged
— a constant-pitch note still takes the closed-form phase path. Only
voices that actually modulate pay for phase integration.

`--glide-ms`, `--ring-depth`, and `--vib-cents` override them from the
command line for the usual run-listen-tweak loop.

A non-integer `ring_ratio` is what produces the metallic burble: it places
sum and difference tones where no harmonic series would. Values above
about 0.6 for `ring_depth` get harsh quickly.

## Building and releasing

Versions are bare `YYYYMMDD` datestamps in the plain-text `version` file
at the repository root. A release tag must match it exactly, with no `v`
prefix, or the workflow stops before it builds anything.

```bash
pip install -r requirements-dev.txt
scripts/build_local.sh --check     # tests, build, smoke-test, package
```

`scripts/build_local.sh` runs the same steps as
`.github/workflows/release.yml`: the same preflight, the same PyInstaller
invocation, the same `--cli version` smoke test, the same archive layout,
the same checksum file. If it passes here and fails in CI, the difference
is the runner rather than the tree, which is the whole point of being able
to run it locally.

Local builds are not signed. Signing belongs to the workflow, which holds
the key; a signature made on a workstation would prove nothing about the
artefacts that workflow publishes.

To cut a release: update `version`, add a `## [YYYYMMDD]` section to
[CHANGELOG.md](CHANGELOG.md) — the workflow lifts the release notes
straight out of it — commit, then tag with the same datestamp and push.

## Repository layout

```
earcongen.py            the generator
earconcheck.py          quality checks: clicks, DC, clipping, loudness spread
earcongui.py            the graphical front end (entry point)
gui/                    the window: controls, playback, platform paths
version                 YYYYMMDD datestamp; the release tag must match
packaging/              PyInstaller spec and shared build configuration
scripts/build_local.sh  the release build, runnable on a workstation
tests/                  including SHA-256 pins on the core family's audio
licenses/               LGPL and GPL texts shipped inside every binary
README.md               this file — what and why
USAGE.md                full CLI and GUI reference, recipes, extending
CHANGELOG.md            what changed, and what it means for compatibility
THIRD-PARTY-NOTICES.md  numpy, Qt, PyInstaller, and the LGPL obligations
LICENSE
```

## Documentation

- **[USAGE.md](USAGE.md)** — every flag, the spec file format, recipes,
  how to add voices and contours, how to load a theme in an application,
  troubleshooting, and ideas for extending the tool.
- `./earcongen.py --notes` — the principles above, condensed to a screen,
  and available in the window under Help.
- **[CHANGELOG.md](CHANGELOG.md)** — what changed in each release, and
  whether it changes what users hear.

## License

MIT. See [LICENSE](LICENSE).
