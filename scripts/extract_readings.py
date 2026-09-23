#!/usr/bin/env python3
"""Regenerate speaking/<slug>/reading.html from manuscripts (heading-aware).

Source of truth: manuscripts/MAP.md
  python3 scripts/extract_readings.py
Then rebuild pages:
  python3 scripts/build_speaking.py
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import zipfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rich_docx
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEAKING = ROOT / "speaking"
MANUSCRIPTS = ROOT / "manuscripts"
MAP_PATH = MANUSCRIPTS / "MAP.md"
TALKS_PATH = SPEAKING / "talks.json"

W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

PDF_H2 = {
    "introduction",
    "review",
    "correcting",
    "restraining",
    "leading",
    "result",
    "conclusion",
    "main point",
}
PDF_H3 = {"hook"}

# Slug → manuscript filename (or "cues")
DEFAULT_MAP: dict[str, str] = {
    "all-hands-on-deck": "all-hands-on-deck.docx",
    "avoid-sabotage": "avoid-sabotage.docx",
    "build-and-fight": "build-and-fight.docx",
    "fear-to-faith-favor": "fear-to-faith-favor.docx",
    "from-confusion-to-obedience": "Confusion-Turns-to-Obedience.pdf",
    "from-fear-to-faith-again": "from-fear-to-faith-again.docx",
    "from-ignorance-to-repentance": "cues",
    "good-shepherd": "good-shepherd.docx",
    "guard-the-gates": "guard-the-gates.docx",
    "how-can-i-start-building": "how-can-i-start-building.docx",
    "learning-to-live-in-the-story": "learning-to-live-in-the-story.docx",
    "make-war-not-peace": "make-war-not-peace.docx",
    "youre-responsible-for-results": "cues",
    "pray-lots-work-hard": "pray-lots-work-hard-from-cues.txt",
    "put-your-name-on-something": "put-your-name-on-something.docx",
    "resurrection-jesus-is-king": "resurrection-jesus-is-king.docx",
    "who-can-stand-against-us": "who-can-stand-against-us.docx",
    "win-the-world-through-the-word": "win-the-world-through-the-word.docx",
}

SKIP_OUTLINE = {"put-your-name-on-something"}
PROMOTE_CAPS = {"build-and-fight"}
CUE_SLUGS = {"pray-lots-work-hard", "from-ignorance-to-repentance", "youre-responsible-for-results"}

GAP = 2.5
MIN_PARA = 220


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def write_reading(path: Path, blocks: list[tuple[str, str]]) -> None:
    parts = ['<div class="reading-body">']
    for tag, text in blocks:
        text = (text or "").strip()
        if not text:
            continue
        parts.append(f"<{tag}>{esc(text)}</{tag}>")
    parts.append("</div>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def norm_style(name: str | None) -> str:
    if not name:
        return "Normal"
    return name.replace(" ", "").strip()


def style_to_tag(style: str, text: str, page_title: str | None) -> str | None:
    """Return 'h2', 'h3', 'skip', or None (body)."""
    s = norm_style(style)
    if s == "Heading1":
        if page_title:
            a = text.strip().rstrip("!.").lower()
            b = page_title.strip().rstrip("!.").lower()
            if a == b or a.rstrip("!") == b.rstrip("!"):
                return "skip"
        return "h2"
    if s == "Heading2":
        return "h2"
    if s == "Heading3":
        return "h3"
    return None


def extract_docx_xml(path: Path) -> list[tuple[str, str]]:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find("w:body", W_NS)
    out: list[tuple[str, str]] = []
    if body is None:
        return out
    for p in body.findall("w:p", W_NS):
        texts = [t.text or "" for t in p.findall(".//w:t", W_NS)]
        text = "".join(texts).strip()
        if not text:
            continue
        pPr = p.find("w:pPr", W_NS)
        style = "Normal"
        if pPr is not None:
            ps = pPr.find("w:pStyle", W_NS)
            if ps is not None:
                style = ps.get(f"{{{W_NS['w']}}}val") or "Normal"
        out.append((style, text))
    return out


def extract_docx(path: Path) -> list[tuple[str, str]]:
    try:
        from docx import Document  # type: ignore

        doc = Document(str(path))
        out: list[tuple[str, str]] = []
        for p in doc.paragraphs:
            text = (p.text or "").strip()
            if not text:
                continue
            style = p.style.name if p.style else "Normal"
            out.append((style, text))
        return out
    except Exception:
        return extract_docx_xml(path)


def has_heading_styles(paras: list[tuple[str, str]]) -> bool:
    for style, _ in paras:
        if norm_style(style) in {"Heading1", "Heading2", "Heading3"}:
            return True
    return False


def is_all_caps_heading(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 80:
        return False
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 3:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.9


def blocks_from_docx(
    paras: list[tuple[str, str]],
    *,
    page_title: str | None,
    skip_outline: bool,
    promote_caps: bool,
) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []

    if skip_outline:
        # Keep short meta before First Draft / Explanatory Outline
        meta: list[tuple[str, str]] = []
        start_idx = None
        for i, (style, text) in enumerate(paras):
            low = text.strip().lower()
            if low in {"first draft", "explanatory outline"} or low.startswith(
                "explanatory outline"
            ):
                break
            if len(text) < 120:
                meta.append(("p", text))
            else:
                break
        # Prefer Heading1 Introduction (structured manuscript body)
        for i, (style, text) in enumerate(paras):
            if norm_style(style) == "Heading1" and text.strip().lower() == "introduction":
                start_idx = i
                break
        if start_idx is None:
            for i, (style, text) in enumerate(paras):
                if text.strip().lower() == "introduction":
                    start_idx = i
                    break
        if start_idx is None:
            start_idx = 0
        paras = meta + paras[start_idx:]

    for style, text in paras:
        tag = style_to_tag(style, text, page_title)
        if tag == "skip":
            continue
        if tag:
            blocks.append((tag, text))
            continue
        if promote_caps and is_all_caps_heading(text):
            blocks.append(("h2", text.title() if text.isupper() else text))
            continue
        # Plain "Introduction" / "Conclusion" etc. as body titles when no Heading styles
        if not has_heading_styles([(style, text)]) and text.strip().lower() in PDF_H2:
            # only when whole doc lacks headings — handled via promote path below
            pass
        blocks.append(("p", text))

    # If no heading styles at all and not promote_caps, promote known section words
    if not has_heading_styles(paras) and not promote_caps:
        fixed: list[tuple[str, str]] = []
        for tag, text in blocks:
            low = text.strip().lower().rstrip(":")
            if tag == "p" and low in PDF_H2 and len(text) <= 40:
                fixed.append(("h2", text.strip().rstrip(":")))
            elif tag == "p" and low in PDF_H3 and len(text) <= 40:
                fixed.append(("h3", text.strip().rstrip(":")))
            else:
                fixed.append((tag, text))
        blocks = fixed

    if skip_outline:
        blocks = truncate_duplicate_sermon(blocks)
    return blocks


def truncate_duplicate_sermon(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Keep first sermon body; drop repeated Introductions / Lord's Supper notes."""
    intro_seen = 0
    out: list[tuple[str, str]] = []
    for tag, text in blocks:
        low = text.strip().lower()
        if tag == "h2" and low == "introduction":
            intro_seen += 1
            if intro_seen > 1:
                break
        if tag in {"h2", "h3"} and (
            "presiding" in low
            or "lord" in low and "supper" in low
            or low.startswith("what to say when")
        ):
            break
        out.append((tag, text))
    return out


def extract_pdf(path: Path, page_title: str | None) -> list[tuple[str, str]]:
    try:
        raw = subprocess.check_output(
            ["pdftotext", "-layout", str(path), "-"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="replace")
    except Exception as e:
        raise SystemExit(f"pdftotext failed for {path}: {e}") from e

    lines = []
    for ln in raw.splitlines():
        ln = ln.replace("\x0c", "").strip()
        ln = re.sub(r"[ \t]+", " ", ln)
        lines.append(ln)

    blocks: list[tuple[str, str]] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if buf:
            para = " ".join(buf).strip()
            if para:
                blocks.append(("p", para))
        buf = []

    for ln in lines:
        if not ln:
            flush()
            continue
        low = ln.lower().rstrip(":")
        if page_title:
            a = ln.rstrip("!.").lower()
            b = page_title.rstrip("!.").lower()
            if a == b or a.replace(" turns to ", " to ") == b.replace(" from ", "").replace(
                " to ", " to "
            ):
                # skip redundant title
                if len(ln) < 80:
                    flush()
                    continue
        if low in PDF_H2 and len(ln) <= 40:
            flush()
            label = ln if ln[0].isupper() else ln.title()
            blocks.append(("h2", label.rstrip(":")))
            continue
        if low in PDF_H3 and len(ln) <= 40:
            flush()
            label = ln if ln[0].isupper() else ln.title()
            blocks.append(("h3", label.rstrip(":")))
            continue
        if low.startswith("transition"):
            flush()
            blocks.append(("p", ln))
            continue
        buf.append(ln)
    flush()
    return blocks


def clean_cue(t: str) -> str:
    t = t.strip()
    t = re.sub(r"\b([A-Za-z][A-Za-z']*)\s+\1\b", r"\1", t, flags=re.I)
    t = t.replace('""', '"')
    return re.sub(r"\s+", " ", t).strip()


def cues_to_blocks(cues: list) -> list[tuple[str, str]]:
    paras: list[str] = []
    buf: list[str] = []
    prev_end = None

    def buf_text() -> str:
        return clean_cue(" ".join(buf))

    def flush() -> None:
        nonlocal buf
        text = buf_text()
        if text:
            paras.append(text)
        buf = []

    for cue in cues:
        text = clean_cue(str(cue.get("text") or ""))
        if not text:
            continue
        start = float(cue.get("start") or 0)
        end = float(cue.get("end") or start)
        if buf and prev_end is not None:
            gap = start - prev_end
            prev = buf[-1]
            cur = buf_text()
            if gap > GAP:
                flush()
            elif (
                re.search(r'[.!?]"?\s*$', prev)
                and text[:1].isupper()
                and len(cur) >= MIN_PARA
            ):
                flush()
        buf.append(text)
        prev_end = end
    flush()
    return [("p", p) for p in paras]


def load_titles() -> dict[str, str]:
    if not TALKS_PATH.exists():
        return {}
    data = json.loads(TALKS_PATH.read_text(encoding="utf-8"))
    return {t["slug"]: t["title"] for t in data if isinstance(t, dict)}


def parse_existing_map() -> dict[str, str]:
    if not MAP_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for line in MAP_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 2:
            continue
        slug, source = cols[0], cols[1].strip("`")
        if slug.lower() in {"slug", "------"} or set(slug) <= {"-"}:
            continue
        out[slug] = source
    return out


def write_map(statuses: dict[str, str], sources: dict[str, str]) -> None:
    notes = {
        "pray-lots-work-hard": "Cue-derived prose (docx was scripture-only). Flat paragraphs.",
        "from-ignorance-to-repentance": "No full manuscript; cue-based reading. Flat paragraphs.",
        "youre-responsible-for-results": "No manuscript on hand; cue/prior reading.",
        "put-your-name-on-something": "Skip First Draft / Explanatory Outline; start at Heading Introduction; keep sermon section headings.",
        "from-confusion-to-obedience": "PDF; section titles (Introduction, Review, Correcting, …) → h2.",
        "build-and-fight": "Use second manuscript copy after Titus 2 note (closer to video cues); never both tabs. ALL-CAPS → h2; lists/strong preserved.",
    }
    lines = [
        "# Speaking transcript sources",
        "",
        "How each talk's cleaned reading transcript (`speaking/<slug>/reading.html`) is produced.",
        "",
        "Regenerate: `python3 scripts/extract_readings.py`",
        "Then build: `python3 scripts/build_speaking.py`",
        "",
        "| Slug | Source | Notes |",
        "|------|--------|-------|",
    ]
    for slug in sorted(sources):
        src = sources[slug]
        note = notes.get(slug, statuses.get(slug, ""))
        if slug not in notes and statuses.get(slug):
            note = statuses[slug]
        lines.append(f"| {slug} | `{src}` | {note} |")
    lines += [
        "",
        "Heading mapping: Word `Heading1` / `Heading2` → `<h2>`; `Heading3` → `<h3>`; body → `<p>`.",
        "Skip redundant Heading1 when it matches the page H1 title.",
        "",
        "Page layout: YouTube `#yt-player` → **Transcript** (`reading-transcript`) → **Follow along** (`#transcript`).",
        "",
        "Preview only: sync `speaking/` to `ncolestock/ncolestock.github.io`.",
        "Never push `nathan.colestock.me` / production CNAME from this lane.",
        "",
    ]
    MAP_PATH.write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "MAP.md").write_text(
        "# Speaking transcript sources\n\nSee [`manuscripts/MAP.md`](manuscripts/MAP.md).\n",
        encoding="utf-8",
    )


def process_slug(slug: str, source: str, title: str | None) -> str:
    out = SPEAKING / slug / "reading.html"
    src = source.strip().strip("`")

    if slug in CUE_SLUGS or src in {"cues", "cue", "spoken cues"}:
        if slug == "pray-lots-work-hard":
            txt = MANUSCRIPTS / "pray-lots-work-hard-from-cues.txt"
            cues_path = SPEAKING / slug / "transcript.json"
            if cues_path.exists():
                cues = json.loads(cues_path.read_text(encoding="utf-8"))
                blocks = cues_to_blocks(cues)
                write_reading(out, blocks)
                MANUSCRIPTS.mkdir(exist_ok=True)
                txt.write_text("\n\n".join(t for _, t in blocks) + "\n", encoding="utf-8")
                return f"cue-prose paras={len(blocks)}"
            if txt.exists():
                paras = [p.strip() for p in txt.read_text(encoding="utf-8").split("\n\n") if p.strip()]
                write_reading(out, [("p", p) for p in paras])
                return f"cue-txt paras={len(paras)}"
        cues_path = SPEAKING / slug / "transcript.json"
        if cues_path.exists():
            cues = json.loads(cues_path.read_text(encoding="utf-8"))
            blocks = cues_to_blocks(cues)
            write_reading(out, blocks)
            return f"cue-only paras={len(blocks)}"
        if out.exists():
            return "cue-only kept-existing"
        return "cue-only MISSING"

    path = MANUSCRIPTS / src
    if not path.exists():
        return f"MISSING {src}"

    if path.suffix.lower() == ".pdf":
        blocks = extract_pdf(path, title)
        write_reading(out, blocks)
        nh = sum(1 for t, _ in blocks if t in {"h2", "h3"})
        return f"pdf headings={nh} blocks={len(blocks)}"

    if path.suffix.lower() == ".txt":
        paras = [p.strip() for p in path.read_text(encoding="utf-8").split("\n\n") if p.strip()]
        write_reading(out, [("p", p) for p in paras])
        return f"txt paras={len(paras)}"

    if path.suffix.lower() == ".docx":
        promote = slug in PROMOTE_CAPS or slug == "build-and-fight"
        skip = slug in SKIP_OUTLINE
        blocks, footnotes = rich_docx.extract_rich_docx(
            path,
            page_title=title,
            slug=slug,
            skip_outline=skip,
            promote_caps=promote,
        )
        # Promote known section words if still flat
        if not any(t in {"h2", "h3"} for t, _ in blocks):
            fixed = []
            for tag, content in blocks:
                plain = re.sub(r"<[^>]+>", "", content).strip()
                low = plain.lower().rstrip(":")
                if tag == "p" and low in PDF_H2 and len(plain) <= 40:
                    fixed.append(("h2", plain.rstrip(":")))
                elif tag == "p" and low in PDF_H3 and len(plain) <= 40:
                    fixed.append(("h3", plain.rstrip(":")))
                else:
                    fixed.append((tag, content))
            blocks = fixed
        rich_docx.write_rich_reading(out, blocks, footnotes)
        nh = sum(1 for t, _ in blocks if t in {"h2", "h3"})
        nl = sum(1 for t, _ in blocks if t in {"ul", "ol"})
        ns = sum(content.count("<strong>") for _, content in blocks)
        return f"docx headings={nh} lists={nl} strong={ns} fn={len(footnotes)} blocks={len(blocks)}"
    return f"unknown {src}"


def main() -> None:
    titles = load_titles()
    sources = dict(DEFAULT_MAP)
    sources.update(parse_existing_map())

    # Ensure every talk directory is covered
    for child in SPEAKING.iterdir():
        if child.is_dir() and child.name not in sources:
            if (child / "transcript.json").exists() or (child / "reading.html").exists():
                sources[child.name] = "cues"

    statuses: dict[str, str] = {}
    headed = 0
    flat = 0
    for slug, source in sorted(sources.items()):
        if not (SPEAKING / slug).is_dir():
            continue
        st = process_slug(slug, source, titles.get(slug))
        statuses[slug] = st
        print(f"{slug}: {st}")
        if "headings=" in st:
            try:
                n = int(st.split("headings=")[1].split()[0])
            except Exception:
                n = 0
            if n > 0:
                headed += 1
            else:
                flat += 1
        elif "cue" in st:
            flat += 1

    write_map(statuses, {k: sources[k] for k in sources if (SPEAKING / k).is_dir()})
    print(f"heading-aware≈{headed} flat/cue≈{flat} MAP→{MAP_PATH}")


if __name__ == "__main__":
    main()
