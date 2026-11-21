# anki-addon

**Modern Anki** — a cleaner, more direct Anki desktop UI, packaged as an add-on.

- Unified top/bottom bars with Decks · New · Edit · Stats, a Log in button and a light/dark toggle.
- Deck list with per-deck edit / options / more icons and a today / streak / due stats card.
- Quizlet-style flashcard in the reviewer with a flip animation.
- **New**: create or import a deck from one place; imports run silently.
- **Edit**: a Quizlet-style card list per deck with inline editing, add, suspend and delete. "Advanced" opens the full browser, filtered to that deck.
- Every dialog (Stats, Deck Options, Preferences, Browse, …) opens as a centred modal over a dimmed window; click outside or press Esc to close.
- Deck Options gains a **Med School Preset** picker (Preclinical / Dedicated) and a Custom Study shortcut.

Requires Anki 26.09.4 or later (Qt6, FSRS available).

## Development

Symlink this folder into Anki's `addons21/` folder (e.g. as `anki_addon`) during development. Restart Anki to pick up Python changes; CSS/JS are reloaded when the page is next shown.

## Packaging

```sh
rm -rf __pycache__ meta.json && zip -r anki-addon.ankiaddon . -x '.*' 'README.md' '*.ankiaddon'
```
