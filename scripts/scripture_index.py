"""Build the site Index: every scripture cited in Writing or Speaking."""
from __future__ import annotations

import html as html_lib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]

BOOK_ORDER = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles", "Ezra–Nehemiah", "Ezra", "Nehemiah", "Esther",
    "Job", "Psalm", "Proverbs", "Ecclesiastes", "Song of Solomon",
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

# Abbreviation / alias → canonical book name
BOOK_ALIASES = {
    "gen": "Genesis", "genesis": "Genesis",
    "ex": "Exodus", "exod": "Exodus", "exodus": "Exodus",
    "lev": "Leviticus", "leviticus": "Leviticus",
    "num": "Numbers", "numbers": "Numbers",
    "deut": "Deuteronomy", "deuteronomy": "Deuteronomy",
    "josh": "Joshua", "joshua": "Joshua",
    "judg": "Judges", "judges": "Judges",
    "ruth": "Ruth",
    "1 sam": "1 Samuel", "2 sam": "2 Samuel", "1 samuel": "1 Samuel", "2 samuel": "2 Samuel",
    "1 kgs": "1 Kings", "2 kgs": "2 Kings", "1 kings": "1 Kings", "2 kings": "2 Kings",
    "1 chr": "1 Chronicles", "2 chr": "2 Chronicles",
    "1 chronicles": "1 Chronicles", "2 chronicles": "2 Chronicles",
    "ezra": "Ezra",
    "neh": "Nehemiah", "nehemiah": "Nehemiah",
    "esth": "Esther", "esther": "Esther",
    "job": "Job",
    "ps": "Psalm", "psa": "Psalm", "psalm": "Psalm", "psalms": "Psalm",
    "prov": "Proverbs", "proverbs": "Proverbs",
    "eccl": "Ecclesiastes", "ecc": "Ecclesiastes", "ecclesiastes": "Ecclesiastes",
    "song": "Song of Solomon", "songs": "Song of Solomon", "sos": "Song of Solomon",
    "isa": "Isaiah", "isaiah": "Isaiah",
    "jer": "Jeremiah", "jeremiah": "Jeremiah",
    "lam": "Lamentations", "lamentations": "Lamentations",
    "ezek": "Ezekiel", "eze": "Ezekiel", "ezekiel": "Ezekiel",
    "dan": "Daniel", "daniel": "Daniel",
    "hos": "Hosea", "hosea": "Hosea",
    "joel": "Joel",
    "amos": "Amos",
    "obad": "Obadiah", "obadiah": "Obadiah",
    "jonah": "Jonah",
    "mic": "Micah", "micah": "Micah",
    "nah": "Nahum", "nahum": "Nahum",
    "hab": "Habakkuk", "habakkuk": "Habakkuk",
    "zeph": "Zephaniah", "zephaniah": "Zephaniah",
    "hag": "Haggai", "haggai": "Haggai",
    "zech": "Zechariah", "zechariah": "Zechariah",
    "mal": "Malachi", "malachi": "Malachi",
    "matt": "Matthew", "mt": "Matthew", "matthew": "Matthew",
    "mark": "Mark", "mk": "Mark",
    "luke": "Luke", "lk": "Luke",
    "john": "John", "jn": "John",
    "acts": "Acts",
    "rom": "Romans", "romans": "Romans",
    "1 cor": "1 Corinthians", "2 cor": "2 Corinthians",
    "1 corinthians": "1 Corinthians", "2 corinthians": "2 Corinthians",
    "gal": "Galatians", "galatians": "Galatians",
    "eph": "Ephesians", "ephesians": "Ephesians",
    "phil": "Philippians", "philippians": "Philippians",
    "col": "Colossians", "colossians": "Colossians",
    "1 thess": "1 Thessalonians", "2 thess": "2 Thessalonians",
    "1 thessalonians": "1 Thessalonians", "2 thessalonians": "2 Thessalonians",
    "1 tim": "1 Timothy", "2 tim": "2 Timothy",
    "1 timothy": "1 Timothy", "2 timothy": "2 Timothy",
    "titus": "Titus",
    "phlm": "Philemon", "philemon": "Philemon",
    "heb": "Hebrews", "hebrews": "Hebrews",
    "jas": "James", "james": "James",
    "1 pet": "1 Peter", "2 pet": "2 Peter", "1 peter": "1 Peter", "2 peter": "2 Peter",
    "1 jn": "1 John", "2 jn": "2 John", "3 jn": "3 John",
    "1 john": "1 John", "2 john": "2 John", "3 john": "3 John",
    "jude": "Jude",
    "rev": "Revelation", "revelation": "Revelation",
    "ezra–nehemiah": "Ezra–Nehemiah", "ezra-nehemiah": "Ezra–Nehemiah",
}

BOOK_PATTERN = (
    r"(?:(?:1|2|3)\s+)?"
    r"(?:Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|"
    r"Samuel|Kings|Chronicles|Ezra|Nehemiah|Esther|Job|Psalms?|Proverbs|"
    r"Ecclesiastes|Song of Solomon|Song of Songs|Isaiah|Jeremiah|Lamentations|"
    r"Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|"
    r"Zephaniah|Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|"
    r"Corinthians|Galatians|Ephesians|Philippians|Colossians|Thessalonians|"
    r"Timothy|Titus|Philemon|Hebrews|James|Peter|Jude|Revelation|"
    r"Gen|Exod|Ex|Lev|Num|Deut|Josh|Judg|Sam|Kgs|Chr|Neh|Esth|Ps|Prov|Eccl|Ecc|"
    r"Song|Isa|Jer|Lam|Ezek|Eze|Dan|Hos|Obad|Mic|Nah|Hab|Zeph|Hag|Zech|Mal|"
    r"Matt|Mt|Mk|Lk|Jn|Rom|Cor|Gal|Eph|Phil|Col|Thess|Tim|Phlm|Heb|Jas|Pet|Rev)"
)

REF_RE = re.compile(
    rf"(?<![A-Za-z])({BOOK_PATTERN})\.?\s+"
    rf"(\d+)(?::(\d+))?(?:[\u2013\-](\d+)(?::(\d+))?)?",
    re.IGNORECASE,
)

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def _canon_book(raw: str) -> str | None:
    key = re.sub(r"\s+", " ", raw.strip().lower().rstrip("."))
    key = key.replace("song of songs", "song of solomon")
    return BOOK_ALIASES.get(key)


def normalize_ref(match: re.Match) -> tuple[str, int, int, str] | None:
    book = _canon_book(match.group(1))
    if not book:
        return None
    ch = int(match.group(2))
    vs = int(match.group(3) or 0)
    end_ch = match.group(4)
    end_vs = match.group(5)
    # Display form
    if vs and end_ch and end_vs:
        if int(end_ch) == ch:
            display = f"{book} {ch}:{vs}–{end_vs}"
        else:
            display = f"{book} {ch}:{vs}–{end_ch}:{end_vs}"
    elif vs and end_ch and not end_vs:
        # Nehemiah 1:1–2 style ambiguous; treat end as chapter if no start verse end
        display = f"{book} {ch}:{vs}–{end_ch}"
    elif not vs and end_ch:
        display = f"{book} {ch}–{end_ch}"
    elif vs:
        display = f"{book} {ch}:{vs}"
    else:
        display = f"{book} {ch}"
    # Special overview
    if re.fullmatch(r"Ezra[\u2013\-]Nehemiah", match.group(0).strip(), re.I):
        return ("Ezra–Nehemiah", 0, 0, "Ezra–Nehemiah")
    return (book, ch, vs, display)


def extract_refs_from_text(text: str) -> list[tuple[str, int, int, str]]:
    plain = TAG_RE.sub(" ", text)
    plain = html_lib.unescape(plain)
    plain = WS_RE.sub(" ", plain)
    found = []
    seen = set()
    # Overview form without chapter
    for m in re.finditer(r"\bEzra[\u2013\-]Nehemiah\b", plain, re.I):
        key = ("Ezra–Nehemiah", 0, 0, "Ezra–Nehemiah")
        if key not in seen:
            seen.add(key)
            found.append(key)
    for m in REF_RE.finditer(plain):
        parsed = normalize_ref(m)
        if not parsed:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        found.append(parsed)
    return found


def strip_to_body(html: str) -> str:
    # Prefer article/body content
    for pat in (
        r'<div class="reading-body">(.*)</div>\s*</section>',
        r'<div class="body">(.*?)</div>\s*(?:<h3|</article>)',
        r"<article[^>]*>(.*?)</article>",
    ):
        m = re.search(pat, html, re.S | re.I)
        if m:
            return m.group(1)
    return html


def collect_citations() -> dict[tuple, list[dict]]:
    """Map normalized ref key -> list of work dicts."""
    citations: dict[tuple, list[dict]] = defaultdict(list)

    def add(ref: tuple[str, int, int, str], work: dict) -> None:
        key = (ref[0], ref[1], ref[2], ref[3])
        # dedupe same work+ref
        for existing in citations[key]:
            if existing["url"] == work["url"]:
                return
        citations[key].append(work)

    # Speaking: primary scripture + reading bodies
    talks_path = ROOT / "speaking" / "talks.json"
    talks = json.loads(talks_path.read_text(encoding="utf-8"))
    for talk in talks:
        work = {
            "title": talk["title"],
            "url": f"/speaking/{talk['slug']}/",
            "kind": "Speaking",
            "date": talk.get("date") or "",
        }
        primary = talk.get("scripture")
        if primary:
            # parse primary with same extractor (may be Ezra–Nehemiah)
            for ref in extract_refs_from_text(str(primary)):
                add(ref, work)
            if re.fullmatch(r"Ezra[\u2013\-]Nehemiah", str(primary).strip()):
                add(("Ezra–Nehemiah", 0, 0, "Ezra–Nehemiah"), work)
        reading = ROOT / "speaking" / talk["slug"] / "reading.html"
        if reading.exists():
            body = strip_to_body(reading.read_text(encoding="utf-8"))
            for ref in extract_refs_from_text(body):
                add(ref, work)

    # Writing: essay HTML pages (anything with an article that isn't section hubs)
    skip_dirs = {
        "speaking", "reading", "thoughts", "index", "scripts", "manuscripts",
        "speaking-seed", ".git", "node_modules",
    }
    for path in ROOT.rglob("index.html"):
        rel = path.relative_to(ROOT)
        if len(rel.parts) < 2:
            continue  # site home
        top = rel.parts[0]
        if top in skip_dirs:
            continue
        if any(p.startswith(".") for p in rel.parts):
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        if 'class="art-title"' not in html and "art-title" not in html:
            # still allow if has body scripture
            if "scripture" not in html and not REF_RE.search(TAG_RE.sub(" ", html)):
                continue
        title_m = re.search(r'class="art-title"[^>]*>(.*?)</', html, re.S)
        title = TAG_RE.sub("", title_m.group(1)).strip() if title_m else top.replace("-", " ").title()
        title = html_lib.unescape(title)
        url = "/" + "/".join(rel.parts[:-1]) + "/"
        work = {"title": title, "url": url, "kind": "Writing", "date": ""}
        date_m = re.search(r'<div class="art-meta">.*?<span>([^<]+)</span>', html, re.S)
        if date_m and not date_m.group(1).lower().startswith("essay"):
            # often Essay then date
            pass
        meta = re.findall(r'<div class="art-meta">(.*?)</div>', html, re.S)
        if meta:
            spans = re.findall(r"<span>([^<]+)</span>", meta[0])
            for s in spans:
                if re.search(r"\d{4}|January|February|March|April|May|June|July|August|September|October|November|December", s):
                    work["date"] = s.strip()
                    break
        body = strip_to_body(html)
        for ref in extract_refs_from_text(body):
            add(ref, work)

    return citations


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
    # talks arg kept for builder compatibility; citations scan the tree
    _ = talks
    description = "Scripture index of passages cited in Nathan Colestock’s writing and speaking."
    citations = collect_citations()

    # group by book
    by_book: dict[str, list[tuple]] = defaultdict(list)
    for key in citations:
        book = key[0]
        by_book[book].append(key)

    ordered_books = sorted(by_book.keys(), key=lambda b: BOOK_RANK.get(b, 5_000))
    blocks: list[str] = []

    for book in ordered_books:
        heading = "Psalms" if book == "Psalm" else book
        keys = sorted(by_book[book], key=lambda k: (k[1], k[2], k[3]))
        rows = []
        for key in keys:
            ref_display = esc(key[3])
            works = citations[key]
            # sort works: speaking by date desc, writing after or by title
            def work_sort(w):
                return (0 if w["kind"] == "Speaking" else 1, w.get("date") or "", w["title"])

            work_bits = []
            for w in sorted(works, key=work_sort, reverse=False):
                # speaking dates look like YYYY-MM-DD — pretty them if possible
                when = w.get("date") or ""
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
                    when = full_date(when)
                meta = f'{esc(w["kind"])}'
                if when:
                    meta += f' · {esc(when)}'
                work_bits.append(
                    f"""            <a class="scripture-work" href="{esc(w["url"])}">
              <span class="scripture-title">{esc(w["title"])}</span>
              <span class="scripture-work-meta">{meta}</span>
            </a>"""
                )
            rows.append(
                f"""        <li class="scripture-entry">
          <div class="scripture-ref">{ref_display}</div>
          <div class="scripture-works">
{chr(10).join(work_bits)}
          </div>
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

    body = "\n".join(blocks) if blocks else "      <p class=\"scripture-empty\">No scripture citations found yet.</p>"
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
