"""Scripture index helpers for Speaking."""
from __future__ import annotations

import re
from typing import Callable

BOOK_ORDER = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra–Nehemiah", "Ezra", "Nehemiah", "Esther",
    "Job", "Psalm", "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon",
    "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel",
    "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum",
    "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude", "Revelation",
]
BOOK_RANK = {name: i for i, name in enumerate(BOOK_ORDER)}


def parse_scripture(ref: str | None) -> tuple[str, int, int, str] | None:
    if not ref or not str(ref).strip():
        return None
    display = str(ref).strip()
    if re.fullmatch(r"Ezra[\u2013\-]Nehemiah", display):
        return ("Ezra–Nehemiah", 0, 0, display)
    m = re.match(
        r"^(?P<book>\d?\s?[A-Za-z]+(?:\s+[A-Za-z]+)?)\s+"
        r"(?P<start_ch>\d+)"
        r"(?::(?P<start_vs>\d+))?"
        r"(?:[\u2013\-](?P<end_ch>\d+)(?::(?P<end_vs>\d+))?)?"
        r"$",
        display,
    )
    if not m:
        return ("Other", 999, 0, display)
    book = m.group("book").strip()
    if book == "Psalms":
        book = "Psalm"
    return (book, int(m.group("start_ch")), int(m.group("start_vs") or 0), display)


def scripture_sort_key(talk: dict) -> tuple:
    parsed = parse_scripture(talk.get("scripture"))
    if not parsed:
        return (10_000, 0, 0, talk["date"], talk["title"])
    book, ch, vs, _ = parsed
    return (BOOK_RANK.get(book, 5_000), ch, vs, talk["date"], talk["title"])


def speaking_subnav(active: str) -> str:
    items = [
        ("By date", "/speaking/", "date"),
        ("Scripture", "/index/", "scripture"),
    ]
    links = []
    for label, href, key in items:
        cur = ' aria-current="page"' if key == active else ""
        cls = "speaking-subtab is-active" if key == active else "speaking-subtab"
        links.append(f'<a class="{cls}" href="{href}"{cur}>{label}</a>')
    return (
        '    <nav class="speaking-subnav" aria-label="Speaking views">\n      '
        + "\n      ".join(links)
        + "\n    </nav>\n"
    )


def render_scripture_index(
    talks: list[dict],
    *,
    esc: Callable[[str], str],
    full_date: Callable[[str], str],
    head: Callable[..., str],
    tabs: Callable[[str], str],
    masthead: str,
    theme_button: str,
    chrome_close: Callable[[], str],
) -> str:
    description = "Scripture index of sermons and talks by Nathan Colestock."
    groups: dict[str, list[dict]] = {}
    other: list[dict] = []
    for talk in sorted(talks, key=scripture_sort_key):
        parsed = parse_scripture(talk.get("scripture"))
        if not parsed:
            other.append(talk)
            continue
        groups.setdefault(parsed[0], []).append(talk)

    ordered_books = sorted(groups.keys(), key=lambda b: BOOK_RANK.get(b, 5_000))
    blocks: list[str] = []
    for book in ordered_books:
        heading = "Psalms" if book == "Psalm" else book
        rows = []
        for talk in groups[book]:
            ref = esc(talk.get("scripture") or "")
            when = esc(full_date(talk["date"]))
            title = esc(talk["title"])
            slug = esc(talk["slug"])
            rows.append(
                f"""        <li>
          <a class="scripture-row" href="/speaking/{slug}/">
            <span class="scripture-ref">{ref}</span>
            <span class="scripture-meta">
              <span class="scripture-title">{title}</span>
              <time datetime="{esc(talk["date"])}">{when}</time>
            </span>
          </a>
        </li>"""
            )
        book_id = re.sub(r"[^a-z0-9]+", "-", book.lower()).strip("-")
        blocks.append(
            f"""      <section class="scripture-book" aria-labelledby="book-{book_id}">
        <h2 class="scripture-book-label" id="book-{book_id}">{esc(heading)}</h2>
        <ul class="scripture-list">
{chr(10).join(rows)}
        </ul>
      </section>"""
        )

    if other:
        rows = []
        for talk in sorted(other, key=lambda t: t["date"], reverse=True):
            when = esc(full_date(talk["date"]))
            title = esc(talk["title"])
            slug = esc(talk["slug"])
            kind = "Conference" if talk.get("kind") == "conference" else "Talk"
            rows.append(
                f"""        <li>
          <a class="scripture-row" href="/speaking/{slug}/">
            <span class="scripture-ref">{kind}</span>
            <span class="scripture-meta">
              <span class="scripture-title">{title}</span>
              <time datetime="{esc(talk["date"])}">{when}</time>
            </span>
          </a>
        </li>"""
            )
        blocks.append(
            f"""      <section class="scripture-book" aria-labelledby="book-other">
        <h2 class="scripture-book-label" id="book-other">Other</h2>
        <ul class="scripture-list">
{chr(10).join(rows)}
        </ul>
      </section>"""
        )

    body = "\n".join(blocks)
    return f"""{head("Index", description, "/index/")}
<body>
<div id="mapbg" aria-hidden="true"></div>
{theme_button}
<main class="view active" id="view-index">
  <div class="shell">
{masthead}
{tabs("Index")}
    <section class="scripture-index" aria-label="Scripture index">
{body}
    </section>
    <footer class="home-foot">© 2026 Nathan Colestock</footer>
  </div>
</main>
{chrome_close()}"""
