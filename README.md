# nathan.colestock.me

Nathan Colestock's personal site — plain HTML/CSS/JS, no build step. Hosted on
GitHub Pages at **https://nathan.colestock.me**.

- Home / bio: `/` (`index.html`)
- Essays: each gets its own real folder, e.g. `/321-votes/` (`321-votes/index.html`)
- Reading: `/reading/` (`reading/index.html`)
- Thoughts (live X feed): `/thoughts/` (`thoughts/index.html`)
- Shared styles: `style.css`
- Shared headshot: `avatar.jpg` (also used as the default social-share image)

## Why essays are real pages, not hash routes

Essays used to live behind a client-side hash route (`/#/321-votes`) inside
`index.html`. That broke link previews: when a link is texted (iMessage,
Signal, WhatsApp) or pasted into Slack/X, the receiving app fetches the URL
and reads its `<meta>` tags *without* running the page's JavaScript — and a
hash fragment is never even sent to the server. So every link, whatever essay
it pointed to, unfurled with the same generic homepage title/blurb and no
image.

Each essay now has its own real, crawlable URL and its own complete `<head>`
(`title`, `description`, `og:title`, `og:description`, `og:url`, `og:image`,
`twitter:card`, canonical link), so the specific essay's title, dek, and photo
show up correctly when the link is shared.

## Adding a new essay

1. Create `slug/index.html` (copy `321-votes/index.html` as a template).
2. Update its `<head>`: `title`, `description`, `og:title`, `og:description`,
   `og:url`/canonical (`https://nathan.colestock.me/slug/`). Reuse `avatar.jpg`
   for `og:image`/`twitter:image` unless you have a dedicated feature image.
3. Add a `<li><a class="post" href="/slug/">…</a></li>` entry to the
   `writing-list` in `index.html`.
4. Commit and push to `main` — GitHub Pages redeploys automatically.

After pushing, sanity-check the preview with a tool like
https://www.opengraph.xyz/ or Twitter's card validator before texting the
link around, since Facebook/Twitter/etc. cache scraped previews aggressively.

## The Thoughts tab (live X feed)

`/thoughts/` shows @build_n_fight's posts as native X embeds, newest first.

Why it's built this way: X removed the free profile-*timeline* widget (it
renders nothing for logged-out visitors), so a whole feed can't be embedded
with one tag. Single-*post* embeds still render reliably, so the page renders
those from a list of status IDs, and a small script keeps the list current.

- The list lives in `thoughts/index.html` between the `SYNC:START` / `SYNC:END`
  markers — just numeric status IDs (the digits after `/status/`), newest first.
- **Auto-sync:** `python3 scripts/sync_x_thoughts.py` rewrites that list from
  the timeline. It tries X's public syndication endpoint (free, but often rate
  limited); when that 429s, pass IDs harvested from the logged-in profile:
  `python3 scripts/sync_x_thoughts.py --ids 2081...,2099...`. Snowflake IDs sort
  chronologically, so re-runs never lose or reorder posts. Then commit + push.
- **Add one by hand:** drop the status ID as a new first line inside the markers.
- The account must stay **public** for embeds to render.
