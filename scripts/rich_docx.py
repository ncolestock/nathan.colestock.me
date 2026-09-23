"""Rich DOCX → reading HTML blocks (strong, lists, footnotes, multi-tab pick)."""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
WN = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _val(el, attr="val"):
    if el is None:
        return None
    return el.get(f"{WN}{attr}") or el.get(attr)


def _para_style(p) -> str:
    pPr = p.find("w:pPr", W)
    if pPr is None:
        return "Normal"
    ps = pPr.find("w:pStyle", W)
    return _val(ps) or "Normal"


def _num_info(p) -> tuple[str | None, int | None]:
    pPr = p.find("w:pPr", W)
    if pPr is None:
        return None, None
    numPr = pPr.find("w:numPr", W)
    if numPr is None:
        return None, None
    numId = _val(numPr.find("w:numId", W))
    ilvl = _val(numPr.find("w:ilvl", W))
    try:
        return numId, int(ilvl or 0)
    except Exception:
        return numId, 0


def _run_html(r) -> str:
    texts = []
    for t in r.findall("w:t", W):
        texts.append(t.text or "")
    # footnote references inside run
    for fr in r.findall("w:footnoteReference", W):
        fid = _val(fr, "id")
        if fid:
            texts.append(f'[[FN:{fid}]]')
    raw = "".join(texts)
    if not raw:
        # standalone footnote ref as its own "run" handled elsewhere
        return ""
    esc = html.escape(raw, quote=False)
    rPr = r.find("w:rPr", W)
    bold = rPr is not None and rPr.find("w:b", W) is not None
    italic = rPr is not None and rPr.find("w:i", W) is not None
    if bold:
        esc = f"<strong>{esc}</strong>"
    if italic:
        esc = f"<em>{esc}</em>"
    return esc


def _para_inner_html(p) -> str:
    parts = []
    # footnote refs can be direct children too
    for child in list(p):
        tag = child.tag
        if tag == f"{WN}r":
            parts.append(_run_html(child))
            # also check for footnoteReference inside
        elif tag == f"{WN}hyperlink":
            for r in child.findall("w:r", W):
                parts.append(_run_html(r))
    # catch footnote refs not inside runs
    for fr in p.findall("w:footnoteReference", W):
        fid = _val(fr, "id")
        if fid and f"[[FN:{fid}]]" not in "".join(parts):
            parts.append(f"[[FN:{fid}]]")
    return "".join(parts).strip()


def _plain(inner: str) -> str:
    t = re.sub(r"<[^>]+>", "", inner)
    t = re.sub(r"\[\[FN:\d+\]\]", "", t)
    return html.unescape(t).strip()


def load_footnotes(zf: zipfile.ZipFile) -> dict[str, str]:
    if "word/footnotes.xml" not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read("word/footnotes.xml"))
    out: dict[str, str] = {}
    for fn in root.findall("w:footnote", W):
        typ = _val(fn, "type")
        if typ in {"separator", "continuationSeparator"}:
            continue
        fid = _val(fn, "id")
        if not fid:
            continue
        texts = []
        for t in fn.findall(".//w:t", W):
            texts.append(t.text or "")
        text = "".join(texts).strip()
        if text:
            out[fid] = text
    return out


def load_numbering_kinds(zf: zipfile.ZipFile) -> dict[str, str]:
    """numId → 'ul' or 'ol' (best-effort)."""
    if "word/numbering.xml" not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read("word/numbering.xml"))
    abstract: dict[str, str] = {}
    for absn in root.findall("w:abstractNum", W):
        aid = _val(absn, "abstractNumId")
        # look at lvl 0 numFmt
        kind = "ul"
        for lvl in absn.findall("w:lvl", W):
            if _val(lvl, "ilvl") not in {None, "0"}:
                continue
            fmt = lvl.find("w:numFmt", W)
            v = (_val(fmt) or "").lower()
            if v in {"decimal", "lowerletter", "upperletter", "lowerroman", "upperroman"}:
                kind = "ol"
            break
        if aid is not None:
            abstract[aid] = kind
    out: dict[str, str] = {}
    for num in root.findall("w:num", W):
        nid = _val(num, "numId")
        ref = num.find("w:abstractNumId", W)
        aid = _val(ref)
        if nid is not None:
            out[nid] = abstract.get(aid or "", "ul")
    return out


def select_build_and_fight_tab(paras: list[ET.Element]) -> list[ET.Element]:
    """Prefer second copy after Titus 2 note (closer to video cues); never both."""
    texts = []
    for p in paras:
        texts.append(_plain(_para_inner_html(p)))
    i_tab = next((i for i, t in enumerate(texts) if t.lower() == "tab 1"), None)
    i_pull = next(
        (
            i
            for i, t in enumerate(texts)
            if t.lower().startswith("pull out titus")
            or t.lower().startswith("pull out the titus")
        ),
        None,
    )
    if i_pull is not None:
        # second copy
        return [p for i, p in enumerate(paras) if i > i_pull and texts[i]]
    if i_tab is not None:
        end = i_pull if i_pull is not None else len(paras)
        return [p for i, p in enumerate(paras) if i_tab < i < end and texts[i]]
    return paras


def style_tag(style: str, text: str, page_title: str | None) -> str | None:
    s = (style or "Normal").replace(" ", "")
    plain = text.strip()
    if s == "Heading1":
        if page_title:
            a = plain.rstrip("!.").lower()
            b = page_title.strip().rstrip("!.").lower()
            if a == b:
                return "skip"
        return "h2"
    if s == "Heading2":
        return "h2"
    if s == "Heading3":
        return "h3"
    return None


def is_all_caps_heading(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 80:
        return False
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 3:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.9


def apply_fn_markers(inner: str, used: list[str]) -> str:
    def repl(m):
        fid = m.group(1)
        if fid not in used:
            used.append(fid)
        n = used.index(fid) + 1
        return (
            f'<sup class="fn" id="fnref-{n}">'
            f'<a href="#fn-{n}" aria-label="Footnote {n}">{n}</a></sup>'
        )

    return re.sub(r"\[\[FN:(\d+)\]\]", repl, inner)



CHROME_RE = re.compile(
    r"^(first draft|second draft|third draft|explanatory outline|outline|cutting floor|"
    r"\d{1,2}-\d{1,2} (editing|restructure)|tab \d+)\s*$",
    re.I,
)
DATE_CHROME_RE = re.compile(
    r"(preached by|christ the king|stillwater|november \d|january \d|february \d|"
    r"march \d|april \d|may \d|june \d|july \d|august \d|september \d|october \d|"
    r"december \d|nehemiah \d|psalm \d|^\s*sermon\s*$)",
    re.I,
)


def title_case_heading(text: str) -> str:
    """Title Case for sermon spine headings; keep short all-caps → Title Case."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return t
    # Already mixed and short enough — light normalize
    small = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "vs", "v", "vv"}
    parts = []
    for i, w in enumerate(t.split(" ")):
        raw = w
        # keep parenthetical verse refs as-is-ish
        core = w.strip("()[],.:;")
        low = core.lower()
        if i and low in small and not any(ch.isdigit() for ch in core):
            # preserve surrounding punctuation
            parts.append(w.replace(core, low))
        elif core.isupper() and len(core) <= 3 and core.isalpha():
            parts.append(w)  # LORD, God acronyms already short
        elif core.isupper() or (core and core[0].islower()):
            parts.append(w.replace(core, core[:1].upper() + core[1:].lower() if len(core) > 1 else core.upper()))
        else:
            parts.append(w)
    # Fix common theological caps
    out = " ".join(parts)
    out = re.sub(r"\bLord\b", "LORD", out) if "LORD" in t or "Lord" in t else out
    # Prefer LORD when original had LORD
    if "LORD" in t:
        out = re.sub(r"\bLord\b", "LORD", out)
    return out


def is_chrome_para(plain: str, page_title: str | None = None) -> bool:
    p = (plain or "").strip()
    if not p:
        return True
    if CHROME_RE.match(p):
        return True
    # Strict chrome only — never treat sermon section titles as chrome
    low = p.lower()
    if len(p) < 120 and (
        low.startswith("preached by")
        or low.startswith("christ the king church")
        or re.fullmatch(r"christ the king church( · |, )?stillwater(, mn)?", low)
        or re.fullmatch(r"stillwater,? mn", low)
        or re.fullmatch(
            r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},\s*\d{4}",
            low,
        )
        or re.fullmatch(r"nehemiah\s+\d+[a-z–-]*", low)
        or re.fullmatch(r"psalm\s+\d+[a-z–-]*", low)
        or low in {"sermon", "conference"}
    ):
        return True
    if page_title and p.rstrip("!.").lower() == page_title.strip().rstrip("!.").lower():
        return True
    if len(p) < 60 and re.fullmatch(
        r"(put your name on something|resurrection!?|jesus is king!?|resurrection!? jesus is king!?)",
        low,
    ):
        return True
    return False


def is_stop_marker(plain: str) -> bool:
    low = (plain or "").strip().lower()
    if not low:
        return False
    if low in {"cutting floor", "outline", "explanatory outline", "first draft", "second draft"}:
        return True
    if low.startswith("explanatory outline"):
        return True
    if re.match(r"^\d{1,2}-\d{1,2} (editing|restructure)", low):
        return True
    if "presiding" in low and "supper" in low:
        return True
    if "lord" in low and "supper" in low and len(low) < 80:
        return True
    if low.startswith("what to say when"):
        return True
    return False


def shorten_heading(plain: str) -> str:
    """Map long outline-question h2s to short Title Case labels when needed."""
    p = re.sub(r"\s+", " ", plain.strip())
    mapping = [
        (r"literary purpose|function of this list", "Literary Purpose Of This List"),
        (r"why does nehemiah think|why.*rebuilding is such a big deal", "Why This Rebuilding Matters"),
        (r"ezekiel 47 presents it as the first step", "First Step In Healing The World"),
        (r"how does ezekiel 47.*new covenant", "Ezekiel 47 And The New Covenant"),
        (r"christ.?s church is the city", "The Church As The City Of Grace"),
        (r"so what exactly are we building", "What Are We Building?"),
        (r"what is .civilization", "What Is Civilization?"),
        (r"first let me define what i mean by christian civilization", "Define Christian Civilization"),
        (r"how is .christian civilization. different", "Christian Civilization And Related Terms"),
        (r"result of taking dominion", "Result Of Taking Dominion"),
        (r"teaching them all i have commanded", "Teaching Them All I Commanded"),
        (r"learn from these mighty men", "Learn From These Mighty Men"),
        (r"^1\.?\s*build to win", "1. Build To Win"),
        (r"^2\.?\s*build as an offering", "2. Build As An Offering"),
        (r"^3\.?\s*do your assigned", "3. Do Your Assigned Building"),
        (r"^4\.?\s*be scrappy", "4. Be Scrappy"),
        (r"^5\.?\s*build humbly", "5. Build Humbly"),
        (r"^6\.?\s*receive forgiveness", "6. Receive Forgiveness"),
        (r"main idea and outline", "Main Idea"),
        (r"why preach psalm 2", "Why Preach Psalm 2 On Easter?"),
        (r"is psalm 2 about david", "Is Psalm 2 About David Or Jesus?"),
        (r"rulers of the earth attack", "The Rulers Attack God And His Son (Vv. 1–3)"),
        (r"do not try to cast the rule|are you trying to cast the rule", "Application: Do Not Cast Off God’s Rule"),
        (r"father planned for his son", "The Father Planned His Son As King (Vv. 4–6)"),
        (r"planned every evil to work", "Application: God Plans Evil For Our Good"),
        (r"at the resurrection.*king of everything", "At The Resurrection Jesus Became King (Vv. 7–9)"),
        (r"wicked rulers are fragile", "Application: Wicked Rulers Are Fragile"),
        (r"therefore, serve the lord|therefore serve the lord", "Serve The LORD And Take Refuge In Jesus (Vv. 10–12)"),
        (r"^serve the lord with fear", "Serve The LORD With Fear"),
        (r"^take refuge in jesus", "Take Refuge In Jesus"),
    ]
    low = p.lower()
    for pat, label in mapping:
        if re.search(pat, low):
            return label.rstrip(".")
    if len(p) > 70:
        # First clause before ? or period if still long
        cut = re.split(r"[?]", p, maxsplit=1)[0].strip()
        if 10 < len(cut) <= 70:
            return title_case_heading(cut + ("?" if "?" in p else ""))
        return title_case_heading(p[:67].rstrip(" ,;:") + "…")
    return title_case_heading(p).rstrip(".")


def looks_like_section_heading(plain: str) -> bool:
    p = plain.strip()
    if not p or len(p) > 90:
        return False
    low = p.lower()
    if is_stop_marker(p) or is_chrome_para(p):
        return False
    # Never promote ordinary sentences
    if low.startswith(("there", "here", "so ", "but ", "and ", "now ", "this ", "that ")):
        return False
    if re.match(r"^\d+\.\s+\S", p) and len(p) < 80:
        return True
    if p.endswith(".") and len(p) > 55:
        return False
    keys = (
        "introduction", "conclusion", "christian civilization is good",
        "literary function", "define christian", "overlap with",
        "two reasons christian", "our christian civilization is in ruins",
        "we are morally compromised", "we have low capacities",
        "learn from these mighty", "build and fight to win", "build as an offering",
        "do your assigned building", "be scrappy", "build humbly",
        "let forgiveness", "receive forgiveness", "why is their accomplishment",
        "their work is so grand", "main idea",
    )
    return any(k in low for k in keys)


def slice_put_your_name(paras: list[ET.Element]) -> list[ET.Element]:
    """One First-Draft sermon only: Introduction → before Cutting Floor / Outline / liturgy."""
    texts = [_plain(_para_inner_html(p)) for p in paras]
    # Prefer first non-Heading1 Introduction after First Draft / after outline
    start = None
    for i, t in enumerate(texts):
        low = t.strip().lower()
        if low == "introduction":
            # skip if this is a Heading1 outline copy later — take earliest
            start = i
            break
    if start is None:
        return paras
    # If Explanatory Outline exists before this Intro, ensure we start at Intro after outline
    out = []
    for i in range(start, len(paras)):
        plain = texts[i]
        if i > start and is_stop_marker(plain):
            break
        # Stop before Heading1 long-outline second sermon (Introduction as Heading1 after body Conclusion)
        style = _para_style(paras[i]).replace(" ", "")
        if i > start + 5 and style == "Heading1" and plain.strip().lower() == "introduction":
            break
        if is_chrome_para(plain):
            continue
        out.append(paras[i])
    return out


def slice_resurrection(paras: list[ET.Element]) -> list[ET.Element]:
    """Second Draft only: Heading1 Introduction → Conclusion; drop First Draft + chrome."""
    texts = [_plain(_para_inner_html(p)) for p in paras]
    start = None
    for i, t in enumerate(texts):
        style = _para_style(paras[i]).replace(" ", "")
        if style == "Heading1" and t.strip().lower() == "introduction":
            start = i
            break
    if start is None:
        for i, t in enumerate(texts):
            if t.strip().lower() == "introduction":
                start = i
                break
    if start is None:
        return paras
    out = []
    for i in range(start, len(paras)):
        plain = texts[i]
        low = plain.strip().lower()
        if i > start and low == "first draft":
            break
        if i > start and is_stop_marker(plain) and low not in {"conclusion"}:
            # don't stop on conclusion
            if low != "conclusion":
                break
        if is_chrome_para(plain):
            continue
        out.append(paras[i])
    return out


def postprocess_blocks(
    blocks: list[tuple[str, str]],
    *,
    slug: str | None,
    page_title: str | None,
) -> list[tuple[str, str]]:
    """Strip chrome/drafts/duplicates; Title Case spine; promote short section titles."""
    # Drop leading chrome paragraphs
    i0 = 0
    while i0 < len(blocks):
        tag, content = blocks[i0]
        plain = _plain(content)
        if tag == "p" and is_chrome_para(plain, page_title):
            i0 += 1
            continue
        break
    blocks = blocks[i0:]

    # Truncate at stop markers / duplicate Introduction
    intro_seen = 0
    trimmed = []
    skip_main_idea_list = False
    for tag, content in blocks:
        plain = _plain(content)
        low = plain.lower().strip()
        if tag in {"h2", "h3", "p"} and is_stop_marker(plain) and low not in {"introduction", "conclusion", "main idea"}:
            if low == "main idea and outline" or low == "main idea":
                # keep a short Main Idea heading, skip following outline dump until next real h2
                trimmed.append(("h2", "Main Idea"))
                skip_main_idea_list = True
                continue
            break
        if tag == "h2" and low == "introduction":
            intro_seen += 1
            if intro_seen > 1:
                break
        if skip_main_idea_list:
            if tag in {"h2", "h3"} and low not in {"main idea", "main idea and outline"}:
                skip_main_idea_list = False
            else:
                # keep first prose paragraph after Main Idea as the idea sentence
                if tag == "p" and len(plain) > 80:
                    trimmed.append((tag, content))
                    skip_main_idea_list = False
                continue
        if tag in {"h2", "h3"}:
            label = shorten_heading(plain)
            trimmed.append((tag, html.escape(label, quote=False)))
            continue
        # Promote short section-title paragraphs for put-your-name first draft
        if slug == "put-your-name-on-something" and tag == "p" and looks_like_section_heading(plain):
            # Prefer strong-only paras
            if re.fullmatch(r"\s*(<strong>[^<]+</strong>)\s*", content) or looks_like_section_heading(plain):
                label = shorten_heading(plain)
                if label.lower() == "introduction":
                    intro_seen += 1
                    if intro_seen > 1:
                        break
                trimmed.append(("h2", html.escape(label, quote=False)))
                continue
        trimmed.append((tag, content))

    # Drop empty / chrome leftovers
    final = []
    for tag, content in trimmed:
        plain = _plain(content)
        if tag == "p" and is_chrome_para(plain, page_title):
            continue
        final.append((tag, content))
    return final



def extract_rich_docx(
    path: Path,
    *,
    page_title: str | None = None,
    slug: str | None = None,
    skip_outline: bool = False,
    promote_caps: bool = False,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (blocks, footnotes) where blocks are (tag, html_inner_or_text).

    tag in {h2,h3,p,ul,ol}; list tags' content is concatenated <li>…</li>.
    Footnotes are (display_num_str, html_text) in order used.
    """
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        footnotes = load_footnotes(zf)
        num_kinds = load_numbering_kinds(zf)

    body = root.find("w:body", W)
    if body is None:
        return [], []
    paras = list(body.findall("w:p", W))

    if slug == "build-and-fight":
        paras = select_build_and_fight_tab(paras)
    elif slug == "put-your-name-on-something" or skip_outline:
        paras = slice_put_your_name(paras)
    elif slug == "resurrection-jesus-is-king":
        paras = slice_resurrection(paras)

    blocks: list[tuple[str, str]] = []
    used_fns: list[str] = []
    list_buf: list[str] = []
    list_kind: str | None = None

    def flush_list():
        nonlocal list_buf, list_kind
        if list_buf and list_kind:
            blocks.append((list_kind, "".join(list_buf)))
        list_buf = []
        list_kind = None

    for p in paras:
        inner = _para_inner_html(p)
        plain = _plain(inner)
        if not plain and "[[FN:" not in inner:
            flush_list()
            continue
        # skip tab markers / pull-out notes if any remain
        low = plain.lower()
        if low in {"tab 1", "tab 2"} or low.startswith("pull out titus"):
            flush_list()
            continue

        style = _para_style(p)
        num_id, _ilvl = _num_info(p)
        tag = style_tag(style, plain, page_title)

        if tag == "skip":
            flush_list()
            continue

        if num_id is not None and tag is None and not (
            promote_caps and is_all_caps_heading(plain)
        ):
            kind = num_kinds.get(num_id, "ul")
            if list_kind and list_kind != kind:
                flush_list()
            list_kind = kind
            li_inner = apply_fn_markers(inner, used_fns)
            # strip leading numbering leftovers like "1." if Word also embeds them
            list_buf.append(f"<li>{li_inner}</li>")
            continue

        flush_list()

        if tag is None and promote_caps and is_all_caps_heading(plain):
            tag = "h2"
            # title-case all-caps headings for reading comfort
            if plain.isupper():
                plain = plain.title()
                inner = html.escape(plain, quote=False)

        if tag in {"h2", "h3"}:
            blocks.append((tag, apply_fn_markers(inner if "<" in inner else html.escape(plain, quote=False), used_fns)))
            continue

        blocks.append(("p", apply_fn_markers(inner, used_fns)))

    flush_list()

    blocks = postprocess_blocks(blocks, slug=slug, page_title=page_title)

    fn_blocks: list[tuple[str, str]] = []
    for i, fid in enumerate(used_fns, 1):
        text = footnotes.get(fid, "")
        if text:
            fn_blocks.append((str(i), html.escape(text, quote=False)))
    return blocks, fn_blocks


def write_rich_reading(
    path: Path,
    blocks: list[tuple[str, str]],
    footnotes: list[tuple[str, str]] | None = None,
) -> None:
    parts = ['<div class="reading-body">']
    for tag, content in blocks:
        content = (content or "").strip()
        if not content:
            continue
        if tag in {"ul", "ol"}:
            parts.append(f"<{tag}>{content}</{tag}>")
        else:
            parts.append(f"<{tag}>{content}</{tag}>")
    parts.append("</div>")
    if footnotes:
        parts.append('<aside class="reading-footnotes" aria-label="Footnotes">')
        parts.append("<h3>Footnotes</h3>")
        parts.append("<ol>")
        for num, text in footnotes:
            parts.append(f'<li id="fn-{num}">{text} <a href="#fnref-{num}" title="Back to reference">↩</a></li>')
        parts.append("</ol>")
        parts.append("</aside>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
