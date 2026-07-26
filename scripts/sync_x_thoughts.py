#!/usr/bin/env python3
"""Sync the Thoughts feed on nathan.colestock.me with @build_n_fight's X posts.

Rewrites the ID list inside the SYNC:START / SYNC:END markers in
`thoughts/index.html` with the newest posts, newest first. Snowflake status IDs
sort chronologically as integers, so the merge is order-independent and never
loses a post already on the page.

Why this exists: X removed the free live profile-timeline widget, so a whole
feed can't be embedded client-side. Single-post embeds still render reliably,
so the page renders those and THIS script keeps the list current. Post on X ->
run this -> the post appears on the site. No per-post editing.

Getting the IDs (two ways, in order of preference):

  1. --ids "id1,id2,..."   Pass IDs you already harvested (e.g. Jeeves reads
                           them from x.com/build_n_fight in the logged-in
                           browser during the scan beat). Always works.

  2. (default) best-effort fetch of X's public syndication timeline. Free and
     needs no auth, but X rate-limits it (HTTP 429) from busy IPs. If it fails,
     the script leaves the file untouched and exits non-zero so the caller can
     fall back to the browser-harvest path (method 1).

Usage:
    python3 scripts/sync_x_thoughts.py                      # try syndication
    python3 scripts/sync_x_thoughts.py --ids 2081185942744793389,207...
    python3 scripts/sync_x_thoughts.py --handle build_n_fight --max 40

Exit codes: 0 = file updated or already current; 2 = could not obtain IDs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "thoughts" / "index.html"

START = "/* SYNC:START"          # marker lines are matched loosely (comment text may follow)
END = "/* SYNC:END"
ID_RE = re.compile(r"\b(\d{15,25})\b")


def read_current_ids() -> list[str]:
    text = PAGE.read_text(encoding="utf-8")
    block = _between_markers(text)
    return ID_RE.findall(block)


def _between_markers(text: str) -> str:
    i = text.find(START)
    j = text.find(END)
    if i == -1 or j == -1 or j < i:
        raise SystemExit(f"Could not find SYNC markers in {PAGE}")
    # from end of the START marker line to the start of the END marker line
    i = text.index("\n", i) + 1
    return text[i:j]


def fetch_syndication_ids(handle: str, timeout: int = 15) -> list[str]:
    """Best-effort: pull recent status IDs from X's public syndication timeline."""
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
    ids = set()
    # The payload embeds a JSON blob; tweet ids show up as "id_str":"..." / tweetId.
    for m in re.finditer(r'"(?:id_str|tweetId|id)"\s*:\s*"(\d{15,25})"', body):
        ids.add(m.group(1))
    for m in re.finditer(r"/status/(\d{15,25})", body):
        ids.add(m.group(1))
    return list(ids)


def render_block(ids: list[str], indent: str = "    ") -> str:
    lines = [f'{indent}"{i}"' for i in ids]
    return ",\n".join(lines) + ("\n" if lines else "")


def write_ids(ids: list[str]) -> bool:
    text = PAGE.read_text(encoding="utf-8")
    i = text.find(START)
    j = text.find(END)
    if i == -1 or j == -1:
        raise SystemExit(f"Could not find SYNC markers in {PAGE}")
    line_end = text.index("\n", i) + 1            # keep the START marker line
    end_line_start = text.rfind("\n", 0, j) + 1   # keep the END marker line
    new_block = render_block(ids)
    updated = text[:line_end] + new_block + text[end_line_start:]
    if updated == text:
        return False
    PAGE.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--handle", default="build_n_fight")
    ap.add_argument("--ids", default="", help="comma/space separated status IDs")
    ap.add_argument("--max", type=int, default=50, help="cap number of posts shown")
    args = ap.parse_args()

    current = read_current_ids()

    if args.ids.strip():
        fetched = ID_RE.findall(args.ids)
        source = "provided ids"
    else:
        try:
            fetched = fetch_syndication_ids(args.handle)
            source = "syndication"
        except Exception as exc:  # noqa: BLE001 — any failure means fall back
            print(f"syndication fetch failed ({exc}); pass --ids from a browser "
                  f"harvest instead.", file=sys.stderr)
            return 2
        if not fetched:
            print("syndication returned no ids; pass --ids from a browser harvest "
                  "instead.", file=sys.stderr)
            return 2

    merged = sorted(set(current) | set(fetched), key=int, reverse=True)[: args.max]

    if merged == current:
        print(f"already current ({len(current)} posts, via {source}).")
        return 0

    changed = write_ids(merged)
    added = [i for i in merged if i not in current]
    print(f"updated: {len(merged)} posts (+{len(added)} new) via {source}."
          if changed else "no change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
