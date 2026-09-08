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

```bash
git clone <your-remote>/earcongen.git
cd earcongen
pip install numpy          # the only dependency
./earcongen.py --notes     # the design reasoning, condensed
```

## Quick start

```bash
# Generate the default eight-cue family with the default voice
./earcongen.py --out audio/chime

# Same family, different identity
./earcongen.py --voice bell --scale hirajoshi --out audio/bell
./earcongen.py --voice marimba --note-ms 190 --gap-ms 130 --out audio/marimba

# Audition as they're written
./earcongen.py --voice chime --out audio/chime --play

# See what's available
./earcongen.py --list-voices
./earcongen.py --list-contours

# Define your own set
./earcongen.py --dump-spec > family.json
$EDITOR family.json
./earcongen.py --spec family.json --out audio/custom

# Check the output for clicks, DC offset, and loudness consistency
./earconcheck.py audio/chime/*.wav
```

---

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

## Repository layout

```
earcongen.py      the generator
earconcheck.py    quality checks: clicks, DC, clipping, loudness spread
README.md         this file — what and why
USAGE.md          full CLI reference, recipes, extending, integration
LICENSE
```

## Documentation

- **[USAGE.md](USAGE.md)** — every flag, the spec file format, recipes,
  how to add voices and contours, how to load a theme in an application,
  troubleshooting, and ideas for extending the tool.
- `./earcongen.py --notes` — the principles above, condensed to a screen.

## License

MIT. See [LICENSE](LICENSE).
