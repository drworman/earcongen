# Icon candidates

Six marks, none of them a generic speaker or bell. Each is drawn on a
128x128 grid with heavy strokes, because the size that matters is 16px in
a taskbar rather than 512px on a store page.

| File | Idea | Why it might win | Why it might not |
|---|---|---|---|
| `a-chime-cluster.svg` | Three tubes of descending length on a rail | The most literal picture of *a family of related tones* — the thing the tool actually makes. Reads instantly as sound without being a speaker | Wind chimes carry a new-age association some people will not shake |
| `b-envelope.svg` | The attack-decay curve, as a solid silhouette | The most specific to this project: a soft attack into a long decay is the tool's central argument. Unusual enough to be memorable | Only means something once you know what it is. At 16px it is a leaf |
| `c-rise-contour.svg` | Three dots ascending, each under an arc | Encodes both halves of the design: a motif with a contour, repeated as a set | Busiest of the six. The arcs will mush together at 16px |
| `d-band.svg` | Two rails with a rising motif between them | The frequency band is the idea most people get wrong, and this puts it front and centre | Two horizontal rails read as a container, not a sound |
| `e-struck-bar.svg` | A bar with arcs radiating from the strike | Directly states "struck object, not a beep", which is the whole aesthetic thesis | Closest of the six to a stock wifi or broadcast glyph |
| `f-tone-family.svg` | Three discs on a rising diagonal, growing | Survives 16px better than anything else here, and still says family and rise | Abstract to the point of saying very little on its own |

Colours are `#1a1a1a` with a `#c96442` accent, hardcoded rather than
`currentColor` so the files render the same wherever they are opened.
Swap them freely — each file is a dozen lines.

## Turning the winner into build inputs

The build looks for `../earcongen.ico` and `../earcongen.icns` and
carries on without them.

```bash
# Windows
magick -background none candidates/WINNER.svg -define icon:auto-resize=256,128,64,48,32,16 earcongen.ico

# macOS, on a Mac
mkdir earcongen.iconset
for s in 16 32 64 128 256 512; do
  magick -background none candidates/WINNER.svg -resize ${s}x${s} earcongen.iconset/icon_${s}x${s}.png
  magick -background none candidates/WINNER.svg -resize $((s*2))x$((s*2)) earcongen.iconset/icon_${s}x${s}@2x.png
done
iconutil -c icns earcongen.iconset
```

Check the 16px render before committing. Anything that survives that
survives everything.
