# Speaking transcript sources

How each talk's cleaned reading transcript (`speaking/<slug>/reading.html`) is produced.

Regenerate: `python3 scripts/extract_readings.py`
Then build: `python3 scripts/build_speaking.py`

| Slug | Source | Notes |
|------|--------|-------|
| all-hands-on-deck | `all-hands-on-deck.docx` |  |
| avoid-sabotage | `avoid-sabotage.docx` |  |
| build-and-fight | `build-and-fight.docx` | Use second manuscript copy after Titus 2 note (closer to video cues); never both tabs. ALL-CAPS → h2; lists/strong preserved. |
| fear-to-faith-favor | `fear-to-faith-favor.docx` |  |
| from-confusion-to-obedience | `Confusion-Turns-to-Obedience.pdf` | PDF; section titles (Introduction, Review, Correcting, …) → h2. |
| from-fear-to-faith-again | `from-fear-to-faith-again.docx` |  |
| from-ignorance-to-repentance | `cues` | No full manuscript; cue-based reading. Flat paragraphs. |
| good-shepherd | `good-shepherd.docx` |  |
| guard-the-gates | `guard-the-gates.docx` |  |
| how-can-i-start-building | `how-can-i-start-building.docx` |  |
| learning-to-live-in-the-story | `learning-to-live-in-the-story.docx` |  |
| make-war-not-peace | `make-war-not-peace.docx` |  |
| youre-responsible-for-results | `cues` | No manuscript on hand; cue/prior reading. |
| pray-lots-work-hard | `pray-lots-work-hard-from-cues.txt` | Cue-derived prose (docx was scripture-only). Flat paragraphs. |
| put-your-name-on-something | `put-your-name-on-something.docx` | First Draft only; skip outline/duplicates/Lord's Supper; short Title Case h2s; strip chrome. |
| resurrection-jesus-is-king | `resurrection-jesus-is-king.docx` | Second Draft only; strip draft chrome + meta outline list; consistent Title Case h2s. |
| who-can-stand-against-us | `who-can-stand-against-us.docx` |  |
| win-the-world-through-the-word | `win-the-world-through-the-word.docx` |  |

Heading mapping: Word `Heading1` / `Heading2` → `<h2>`; `Heading3` → `<h3>`; body → `<p>`.
Skip redundant Heading1 when it matches the page H1 title.

Page layout: YouTube `#yt-player` → **Transcript** (`reading-transcript`) → **Follow along** (`#transcript`).

Preview only: sync `speaking/` to `ncolestock/ncolestock.github.io`.
Never push `nathan.colestock.me` / production CNAME from this lane.
