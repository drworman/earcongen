# Changelog

All notable changes to earcongen are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).

**Versions are `YYYYMMDD` datestamps.** The version lives in the plain-text
`version` file at the repository root, and a release tag must match it
exactly or the release workflow fails. Tags are bare datestamps with no
`v` prefix.

Because a datestamp carries no compatibility signal, anything affecting
compatibility between builds is called out explicitly. For this project
that means two things: the **audio output of the `core` family**, which an
application may already have shipped to users, and the **spec file
format**. The `core` family's output is pinned by SHA-256 in
`tests/test_earcongen.py`; any release that changes those hashes changes
what users hear, and will say so here.

## [20260908]

First release. Everything below is new.

### Added — the generator

- **`earcongen.py`, a design instrument for notification sounds.** An
  earcon is a short non-speech cue standing in for a message. Most
  software ships bad ones, not because good ones are hard to make but
  because they are chosen one at a time: someone needs a notification
  sound, grabs a sample, ships it, and six months later someone else
  repeats the process. The result is a set that does not sound related,
  is not balanced, and is individually irritating in ways nobody can
  articulate. This designs them as a set. Pick a timbre, a scale and a
  frequency band; it emits a family whose members are obviously siblings
  but never confusable, normalised so they sound equally loud.
- **Ten voices.** `bell`, `chime`, `marimba`, `glass`, `pluck`, `alert`,
  `alarm` and a deliberately plain `sine` reference, plus the two
  astromech voices below. Each is a table of partial ratios, amplitudes
  and per-partial decay rates, so adding one is a five-line change.
- **A catalogue of cue sets, chosen with `--family`.** `core` is the
  generic eight. `ui`, `system`, `message` and `progress` are curated for
  those domains and use namespaced slugs so several themes can share an
  output directory. `all` concatenates every non-droid cue for
  auditioning — it is not a set to ship, because past about eight cues
  people stop telling members apart and start ignoring the whole
  vocabulary.
- **`-n` / `--note-count`, a cap on motif length, with two ways of
  applying it.** `--cap-mode redesign`, the default, substitutes a
  purpose-built shape of the requested length that preserves what the
  contour meant — a big rise stays a big rise, an arch still returns to
  where it started — and then moves any cues that still collide into a
  different register, upward for a rising cue and downward for a falling
  one. `--cap-mode truncate` cuts each contour short instead, keeping
  every opening exactly as designed at the cost of making cues that
  differ only after the cut point identical; the casualties are named
  rather than silently written to disk. Under `redesign` every shipping
  family stays fully distinct at two notes or more, where truncation
  loses one cue from `core`, `ui`, `system` and `droid` alike.
- **Collision detection compares sounding pitches, not scale degrees.**
  `fit_to_range` folds every motif into the band by whole octaves, so two
  cues five degrees apart on a pentatonic come out as the same frequency.
  Comparing degrees would call them separated and be wrong, and register
  separation that trusted it would walk a cue clean out of the band while
  reporting success.
- **The one-note ceiling is reported as the physical limit it is.** A
  pentatonic in the default 480–1150 Hz band offers six distinguishable
  pitches, so an eight-cue family cannot survive `-n 1` however cleverly
  it is arranged. Rather than quietly writing duplicates, earcongen names
  the cues it could not place, states the capacity, and suggests widening
  the band, raising the cap, or shipping fewer cues. Widening to
  300–2400 Hz gives fifteen pitches and all eight come out distinct.
- **Presets, and the two astromech ones.** `--r2` is droid phrasing that
  still behaves like a notification set: in band, pentatonic, phrases
  capped where a notification sound should be capped. `--r2-full` is the
  unleashed version — chromatic, up into the 2–4 kHz band the tool
  otherwise avoids, six and seven note phrases. Characterful, and tiring
  if it fires forty times a day. Both are ordinary entries in a `PRESETS`
  table, so adding a third is three lines.
- **Presets yield to explicit flags.** Which flags were "given" is decided
  by inspecting the command line, not by comparing values against
  defaults, so `--r2 --gap-ms 95` is honoured even though 95 is exactly
  what the preset would have set. Comparing values cannot tell
  "unspecified" from "specified as the default", and getting that wrong
  means a preset quietly overrides something the user asked for.
- **Five modulation parameters on every voice:** `glide_ms` (portamento
  between notes, interpolated in log-frequency space so it sounds like a
  voice bending rather than a machine sweeping), `sweep_cents` (per-note
  bend), `vib_hz`/`vib_cents` (warble), `ring_ratio`/`ring_depth` (ring
  modulation, which places sum and difference tones where no harmonic
  series would and is most of what reads as a machine attempting speech),
  and `noise_amt` (servo noise, deterministically seeded so repeat runs
  are identical). All default to zero.
- **A `chromatic` scale**, for the unleashed droid preset. It discards the
  guarantee that any two simultaneously-sounding cues are consonant,
  which every other scale here exists to provide.
- **Thirteen further contours**, including four-note shapes and the long,
  jumpy droid material.
- **`--list-families` and `--list-presets`**, and `--dump-spec` now
  follows `--family`.

### Added — the checker

- **`earconcheck.py`** catches the defects that are easy to introduce and
  easy to miss when looking at waveforms rather than listening:
  end-of-file clicks, envelope discontinuities, DC offset, clipping, and
  loudness that is inconsistent across a family. It works on any 16-bit
  WAV, so it is also useful for vetting user-supplied sound files, and
  its exit status drops into CI.
- **`--modulated`** loosens the envelope-drop limit for ring-modulated
  cues, whose nulls are deliberate: a ring modulator drives the signal
  through zero at the difference frequency by design. Without this the
  droid families sit within a hair of the default limit.
- The loudness verdict now lists what to check — deliberate per-cue gain,
  peak limiting on a wide-interval motif, or a genuine normalisation miss
  — rather than asserting a fault. Two of those three are not bugs.

### Added — the graphical front end

- **`earcongui.py`**, a PySide6 window over the same generator. The loop
  this tool is built around is generate, listen, change one thing,
  generate again, and that loop is only as fast as its slowest step.
- **A cap-mode control** beside the note cap, so the choice between
  preserving meaning and preserving openings is visible rather than
  buried in a flag. The status line reports what the cap did: which cues
  were separated by register, or which could not be placed at all.
- **Every setting has a control**, grouped by what it does, each with a
  slider and a numeric entry over the same value. Related settings share
  a range deliberately, so three sliders stacked above one another can be
  compared by eye: the frequency controls all run 100–4000 Hz, the two
  note-length controls both run 40–2000 ms.
- **Settings that mean "leave it to the voice" have a checkbox**, so the
  difference between "attack of 20 ms" and "whatever this voice does" is
  visible rather than implied by a magic value.
- **Choosing a preset fills in every control and locks them.** It does not
  hide them. Someone who picks `r2` and wonders why it sounds like that
  can read the answer off the form: the voice changed, the scale changed,
  the band widened, the spacing tightened. Custom unlocks everything and
  reveals a **Start from** picker, which loads a preset's values as a
  baseline without locking them.
- **Full tooltips throughout**, on every control and on each of its parts,
  because a tooltip on the label alone is one most people never find.
  They carry the reasoning, not just the units.
- **A destination chooser** with a base directory and a subfolder that
  follows the preset or voice name until you type your own. The subfolder
  is reduced to its final component, so a path typed with separators
  cannot escape the base directory.
- **Playback inside the window.** Select a cue to hear it, or
  double-click. QtMultimedia is used where it works and an external
  player is the fallback, because a machine with `paplay` and no working
  Qt audio plugin is a real configuration rather than a hypothetical one.
- **Rendering happens off the interface thread**, so a long ring-out or
  the thirty-four-cue `all` set does not freeze the window during exactly
  the experiments the tool exists to support. Progress is per cue and the
  run can be cancelled between files.
- **The GUI reads its defaults and choices from the command-line parser**
  rather than keeping a copy. Add a voice or move a default in
  `earcongen.py` and the window follows without being edited; a test
  fails if the two ever disagree.
- **Platform-aware locations.** Settings go to Roaming AppData, Application
  Support or `$XDG_CONFIG_HOME`; output defaults to the conventional
  documents folder. A `earcongen-portable.txt` file beside the binary
  keeps both next to the executable instead.

### Added — build and release

- **`version`**, a plain-text `YYYYMMDD` datestamp at the repository root.
- **`.github/workflows/release.yml`**: verify the tag matches the version
  file, run the tests and lint, generate and check every family, build a
  single-file binary for Linux, Windows and macOS, sign where credentials
  exist, smoke-test the artefact, and publish with release notes taken
  from this file.
- **`scripts/build_local.sh`** performs the same steps on a workstation.
  A local build and a CI build are the same build; if this passes and CI
  does not, the difference is the runner rather than the tree.
- **Signing secrets are declared at the job level.** A step's own `env:`
  block is not available to that step's `if:`, which GitHub evaluates
  first, so a step-level reference makes the condition always false and
  signing skips silently on a correctly configured repository — a
  failure that ships an unsigned binary from a green build.
- **The command-line tools are not frozen.** They need numpy alone, run
  anywhere Python does, and are meant to be read and edited. They travel
  inside every release archive as source, so the project is fully usable
  without the binary.
- **A test suite**, including SHA-256 pins on the `core` family's output.

### Not included

- **No icons.** Six candidate marks live in
  `packaging/icons/candidates/` with notes on what each says and where
  each is weak. The build looks for `packaging/earcongen.ico` and
  `packaging/earcongen.icns` and produces correct binaries without them,
  so a fork needs no artwork to ship.

### Notes

- The command-line tools require Python 3.10+ and numpy. The GUI
  additionally requires PySide6; `requirements.txt` and
  `requirements-gui.txt` are separate so installing the former does not
  pull in 60 MB of Qt.
- Qt is used under the LGPL v3 and is never statically linked. See
  `THIRD-PARTY-NOTICES.md`.
