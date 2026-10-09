# Make your own NAVI skin

A skin changes how NAVI looks and sounds: colours, type, surfaces, the home tagline. It never changes the layout, the
names or what anything means. Your skins live on your machine, next to your settings, so you can make one for yourself
or for your company without touching NAVI's code.

```bash
navi theme new acme --name "Acme"   # writes ~/.config/navi/themes/acme.json and acme.css
navi theme check acme               # contrast check for the palette (and every colourway)
navi theme list                     # built-in skins and yours
```

Reload NAVI and your skin is in **Settings → Look**, next to the built-in ones. Every open tab follows when you pick it.

> **For agents** (Claude, or any assistant asked to "make a NAVI theme"): follow this file exactly. Write only the two
> files below, keep every rule scoped to the theme, never load anything from outside, run `navi theme check <key>`,
> and look at the result in the browser before you call it done.

## The two files

### `~/.config/navi/themes/<key>.json`

The key is 2-24 characters, `a-z`, `0-9` and `-`, starting with a letter, and not a built-in skin's key.

```json
{
  "name": "Acme",
  "blurb": "Our brand: deep navy and signal blue",
  "tagline": "Ship it like you mean it.",
  "pal": {"bg": "#0b1020", "fg": "#e8ecf6", "accent": "#4f8cff", "accent2": "#ffffff"},
  "ink": {"warn": "#ffd24a", "ok": "#5dffb5", "hi": "#ffffff", "ack": "#8dffb0", "paper": "#cfd6e6", "deny": "#ff5a5a",
          "agents": {"architect": "#7fd0ff", "adversary": "#ff6b6b", "ledger": "#ffc46b", "scribe": "#d8dde8", "warden": "#5dffb5"}},
  "variants": {
    "Navy":  {"pal": {"bg": "#0b1020", "fg": "#e8ecf6", "accent": "#4f8cff", "accent2": "#ffffff"}},
    "Midnight": {"pal": {"bg": "#05070f", "fg": "#eef1f8", "accent": "#7aa7ff", "accent2": "#ffd166"}}
  },
  "off": [],
  "sound": "wired"
}
```

| Field | What it does |
|---|---|
| `name` · `blurb` | The card in Settings, and its tooltip. |
| `tagline` | Replaces the line under the logo on home. Leave it out to keep NAVI's own. |
| `pal` | The palette: background, text, the accent (act, live, primary buttons) and the second accent (selection). |
| `ink` | The other signal colours (`warn` needs you, `ok` done, `deny` blocked) and each agent's colour on the graph. |
| `variants` | Optional colourways, shown in Settings instead of the general palettes (the first one is the default). |
| `presets: true` | Instead of `pal`/`variants`: use NAVI's palettes (Ice, Wired, Phosphor…) with your CSS. |
| `off` | Atmosphere your skin switches off: any of `"scanlines"`, `"glow"`, `"flicker"`. |
| `sound` | Which sound kit to borrow: `wired`, `crt`, `glass`, `minimal`, `eva`, `journey`, `hunter`. |
| `light: true` | Tell the graph it's drawn on a light background. |

### `~/.config/navi/themes/<key>.css` (optional)

Your touches on top of the tokens. Scope **every** rule to your skin:

```css
:root[data-theme="acme"] { --sans: "Avenir Next", -apple-system, system-ui, sans-serif; }
:root[data-theme="acme"] .composer { border-radius: 14px; }
:root[data-theme="acme"] .btn.pri { letter-spacing: .01em; }
:root[data-theme="acme"] #menu .tagline { font-style: italic; }
```

Useful tokens (all derived from `pal`): `--bg`, `--fg`, `--accent`, `--accent2`, `--warn`, `--ok`, `--ink` … `--ink-4`
(text, from strongest to quietest), `--rule`, `--rule-2` (lines), `--raise`, `--raise-2` (subtle fills), `--glass`, `--sheet`
(panels and sheets), `--sans`, `--mono`. Useful selectors: `#menu` (home), `#top` (top bar), `#hdr` (session header), `#side`
(the feed panel), `#console`, `.sheet` (Settings, launch, panels), `.btn`, `.tag`, `.composer`, `#steps`.

## The rules (NAVI enforces some, you keep the rest)

1. **Nothing from outside.** `@import` and `url(http…)` are removed when NAVI serves your CSS. Use system fonts (a
   font name the machine has), gradients, and colours. No images from the web, no scripts.
2. **Readable first.** All text keeps at least **4.5:1** against its surface, in every colourway. `navi theme check`
   tests the palette; secondary text is `fg` at about 59%, so give `fg` at least 7:1 on `bg`.
3. **Signals keep their meaning.** `warn` means "needs you", `ok` means done, `deny` means blocked: pick colours that
   still read that way in your skin.
4. **The layout stays.** Restyle, never hide or move controls; the names (NAVI, the agents, CONSENSUS) stay.
5. **Scope everything** to `:root[data-theme="<key>"]`, so your skin never leaks into the others.

## A company skin in five minutes

1. `navi theme new acme --name "Acme"`.
2. Put your brand colours in `pal` (and a few colourways in `variants` if you like; a light skin sets `"light": true`).
3. Give the agents colours that sit well next to the brand, and a tagline in your voice.
4. `navi theme check acme`, then reload NAVI and pick it in Settings → Look.
5. Share the two files with your team: they drop them into `~/.config/navi/themes/` and it's there.
