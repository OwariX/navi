# ADR-001: Flappy Bird clone, "Wired" edition

- Status: Accepted. Deciders: architect, adversary, ledger. Data guard: warden.
- User input: sensitivity **public**; visual style **delegated to the council** ("u decide"), which chose Wired.

## Decision
- One `index.html`: inline CSS and JS, no dependencies, works from `file://`. 13.4 KB.
- Canvas 400x600 logical, scaled with devicePixelRatio.
- **Fixed 1/120 s physics** with an accumulator. dt clamped to 0.25 s, so it plays the same at any refresh rate.
- **Circle (r=11) vs rect** collision under a r=14 glowing sprite, so near-misses are fair.
- Input: pointerdown, Space/ArrowUp/W. P pauses, auto-pause on tab hide, M mutes.
- Pipe pool of 4, recycled. No allocations in the game loop.
- Neon look on a budget: `shadowBlur` only on the bird. Pipes get a cheap double-stroke halo.
  Scanlines and vignette are pre-rendered offscreen once per resize.
- Wired details: power lines and poles, a dark city, a perspective grid floor, data-stream ticks on pipes,
  chromatic-aberration text, and a glitch tear on death and every 10 points.
- WebAudio blips. Best score in localStorage (try/catch).

## Rejected
- rAF-dependent physics, box hitbox, `click` events.
- Blurring every pipe (too slow on integrated GPUs). Per-frame scanline drawing.

## Accepted risks
- No input remapping or reduced-motion option in v1.
