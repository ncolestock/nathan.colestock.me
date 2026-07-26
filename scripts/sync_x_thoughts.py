#!/usr/bin/env python3
"""Sync the Thoughts feed on nathan.colestock.me with @build_n_fight's X posts.

The Thoughts page renders its OWN cards (cream, in the site's design) — it no
longer loads X's widgets.js. This script fetches each post's content from X's
public per-tweet syndication endpoint and rewrites the JSON data block inside the
SYNC:START / SYNC:END markers in `thoughts/index.html`, newest first. Snowflake
status IDs sort chronologically as integers, so the merge is order-independent
and never loses a post already on the page.

Why per-tweet (not the profile timeline): X removed the free live
profile-timeline widget AND rate-limits the profile syndication endpoint (429)
from busy IPs. The per-tweet CDN endpoint
(cdn.syndication.twimg.com/tweet-result) is reliable and returns full text,
the link-preview card, and media — everything the page needs to render a card.

Getting the IDs (three ways; content is then fetched per-ID):

  1. --ids "id1,id2,..."  IDs you already harvested (e.g. Jeeves reads them from
                          x.com/build_n_fight in the logged-in browser during the
                          scan beat). Always works.
  2. (default) whatever IDs are already on the page, refreshed in place. Use
     --refresh to re-pull content for posts already present (e.g. after an edit).
  3. best-effort profile syndication fetch to DISCOVER new IDs (may 429). Enable
     with --discover; on failure the script just keeps the current set.

Usage:
    python3 scripts/sync_x_thoughts.py --ids 2081185942744793389,207...
    python3 scripts/sync_x_thoughts.py --refresh          # re-pull existing
    python3 scripts/sync_x_thoughts.py --discover          # try to find new IDs

Exit codes: 0 = file updated or already current; 2 = could not fetch any content.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "thoughts" / "index.html"
HANDLE = "build_n_fight"

# The JSON data block lives inside this script tag; we rewrite its contents.
DATA_RE = re.compile(
    r'(<script type="application/json" id="thoughts-data">)(.*?)(</script>)',
    re.S,
)
ID_RE = re.compile(r"\b(\d{15,25})\b")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# --------------------------------------------------------------------------- #
# Read / write the page's data block
# --------------------------------------------------------------------------- #
def read_current() -> list[dict]:
    text = PAGE.read_text(encoding="utf-8")
    m = DATA_RE.search(text)
    if not m:
        raise SystemExit(f"Could not find thoughts-data block in {PAGE}")
    body = m.group(2).strip()
    if not body:
        return []
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        # Legacy or hand-edited: recover any bare IDs so we can re-fetch them.
        return [{"id": i} for i in dict.fromkeys(ID_RE.findall(body))]


def write_posts(posts: list[dict]) -> bool:
    text = PAGE.read_text(encoding="utf-8")
    payload = json.dumps(posts, ensure_ascii=False, indent=2)
    new_text = DATA_RE.sub(
        lambda m: m.group(1) + "\n" + payload + "\n" + m.group(3), text, count=1
    )
    if new_text == text:
        return False
    PAGE.write_text(new_text, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# Fetch content for one tweet
# --------------------------------------------------------------------------- #
def _token(tweet_id: str) -> str:
    """X's syndication token: ((id / 1e15) * pi) in base-36, stripped of 0s/dots."""
    n = (int(tweet_id) / 1e15) * math.pi
    s = ""
    whole = int(n)
    frac = n - whole
    # base-36 of the whole part
    if whole == 0:
        s = "0"
    while whole:
        whole, r = divmod(whole, 36)
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + s
    # base-36 of the fractional part (enough digits to match X)
    s += "."
    for _ in range(12):
        frac *= 36
        d = int(frac)
        s += "0123456789abcdefghijklmnopqrstuvwxyz"[d]
        frac -= d
    return re.sub(r"(0+|\.)", "", s) or "a"


def _get_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _linkify(text: str, urls: list[dict]) -> str:
    """Escape, then turn t.co links, @mentions and #hashtags into anchors."""
    out = html.escape(text)
    for u in urls:
        tco = html.escape(u.get("url", ""))
        disp = html.escape(u.get("display_url", u.get("expanded_url", "")))
        href = html.escape(u.get("expanded_url", u.get("url", "")))
        if tco:
            out = out.replace(
                tco,
                f'<a href="{href}" target="_blank" rel="noopener nofollow">{disp}</a>',
            )
    out = re.sub(
        r"(^|[\s(])@(\w{1,15})",
        r'\1<a href="https://x.com/\2" target="_blank" rel="noopener nofollow">@\2</a>',
        out,
    )
    out = re.sub(
        r"(^|[\s(])#(\w+)",
        r'\1<a href="https://x.com/hashtag/\2" target="_blank" rel="noopener nofollow">#\2</a>',
        out,
    )
    return out.replace("\n", "<br>")


def _card(raw: dict) -> dict | None:
    card = raw.get("card")
    if not card:
        return None
    bv = card.get("binding_values", {})

    def s(key):
        v = bv.get(key, {})
        return (v.get("string_value") or "").strip()

    def img(*keys):
        for k in keys:
            v = bv.get(k, {}).get("image_value")
            if v and v.get("url"):
                return v["url"]
        return ""

    # Resolve the card's destination from the tweet's URL entities.
    dest = ""
    card_tco = card.get("url", "")
    for u in raw.get("entities", {}).get("urls", []):
        if u.get("url") == card_tco:
            dest = u.get("expanded_url", "")
            break
    if not dest:
        dest = s("card_url") or card_tco

    name = card.get("name", "")
    return {
        "title": s("title"),
        "description": s("description"),
        "domain": s("vanity_url") or s("domain"),
        "image": img("thumbnail_image_large", "thumbnail_image_original",
                     "thumbnail_image"),
        "url": dest,
        "large": name == "summary_large_image",
    }


def fetch_post(tweet_id: str) -> dict | None:
    """Return a render-ready post dict, or None if it can't be fetched."""
    last_err = None
    for tok in (_token(tweet_id), "a"):
        url = (f"https://cdn.syndication.twimg.com/tweet-result"
               f"?id={tweet_id}&lang=en&token={tok}")
        try:
            raw = _get_json(url)
            break
        except Exception as exc:  # noqa: BLE001 — try the fallback token
            last_err = exc
    else:
        print(f"  ! {tweet_id}: {last_err}", file=sys.stderr)
        return None

    urls = raw.get("entities", {}).get("urls", [])
    card = _card(raw)

    # Display text: drop a trailing bare t.co that's just the card/media link.
    text = raw.get("text", "")
    lo, hi = (raw.get("display_text_range") or [0, len(text)])
    text = text[lo:hi]
    for u in urls:
        if card and u.get("expanded_url") == card["url"]:
            text = text.replace(u.get("url", ""), "").rstrip()

    photos = [p["url"] for p in (raw.get("photos") or []) if p.get("url")]

    return {
        "id": raw.get("id_str", tweet_id),
        "html": _linkify(text, urls),
        "created_at": raw.get("created_at", ""),
        "url": f"https://x.com/{HANDLE}/status/{raw.get('id_str', tweet_id)}",
        "card": card,
        "photos": photos,
    }


def discover_ids(handle: str) -> list[str]:
    url = (f"https://syndication.twitter.com/srv/timeline-profile/"
           f"screen-name/{handle}")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "text/html,application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        print(f"discover failed ({exc}); keeping current set.", file=sys.stderr)
        return []
    ids = set(re.findall(r"/status/(\d{15,25})", body))
    ids |= set(re.findall(r'"(?:id_str|tweetId)"\s*:\s*"(\d{15,25})"', body))
    return list(ids)


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--handle", default=HANDLE)
    ap.add_argument("--ids", default="", help="comma/space separated status IDs")
    ap.add_argument("--refresh", action="store_true",
                    help="re-pull content for posts already on the page")
    ap.add_argument("--discover", action="store_true",
                    help="try the profile timeline to find new IDs (may 429)")
    ap.add_argument("--max", type=int, default=50, help="cap posts shown")
    args = ap.parse_args()

    current = read_current()
    by_id = {p["id"]: p for p in current if p.get("id")}

    want = set(by_id)
    if args.ids.strip():
        want |= set(ID_RE.findall(args.ids))
    if args.discover:
        want |= set(discover_ids(args.handle))

    # Which IDs need a content fetch?
    def needs_fetch(i: str) -> bool:
        return args.refresh or "html" not in by_id.get(i, {})

    to_fetch = [i for i in want if needs_fetch(i)]
    fetched = 0
    for i in sorted(to_fetch, key=int, reverse=True):
        post = fetch_post(i)
        if post:
            by_id[i] = post
            fetched += 1
            print(f"  + {i}")

    if not by_id:
        print("no content available; pass --ids from a browser harvest.",
              file=sys.stderr)
        return 2

    posts = sorted(by_id.values(), key=lambda p: int(p["id"]), reverse=True)
    posts = posts[: args.max]

    changed = write_posts(posts)
    print(f"{'updated' if changed else 'already current'}: "
          f"{len(posts)} posts ({fetched} fetched this run).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
