#!/usr/bin/env python3
"""Build the Speaking section from speaking/talks.json.

Writes speaking/index.html and speaking/<slug>/index.html. Dates sort newest
first. Sermons require scripture; conference talks do not. The page set is
Nathan Colestock at Christ the King only — the builder rejects other names.

    python3 scripts/build_speaking.py
"""
from __future__ import annotations

import html
import json
import re
import shutil
import sys
from pathlib import Path
from scripture_index import render_scripture_index

ROOT = Path(__file__).resolve().parents[1]
TALKS_PATH = ROOT / "speaking" / "talks.json"
SPEAKING = ROOT / "speaking"
SITE = "https://nathan.colestock.me"

MONTHS = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
SHORT_MONTHS = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

# Other preachers and guests the strict catalog keeps off this list.
FORBIDDEN = re.compile(
    r"\b(andy|naselli|wilson|dustin|piper|dodds|zeigler|wittenburg|abigail|jenni|manley)\b",
    re.I,
)
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

ICON = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAg"
    "MCA2NCA2NCI+PGNpcmNsZSBjeD0iMzIiIGN5PSIzMiIgcj0iMzIiIGZpbGw9IiM0QzVBMkIiLz48dGV4dCB4PSIzMiIgeT0i"
    "MzQiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGRvbWluYW50LWJhc2VsaW5lPSJjZW50cmFsIiBmb250LWZhbWlseT0iUGFsYXRp"
    "bm8sIEdlb3JnaWEsIHNlcmlmIiBmb250LXdlaWdodD0iNzAwIiBmb250LXNpemU9IjMwIiBmaWxsPSIjRUJFNEQwIj5OQzwv"
    "dGV4dD48L3N2Zz4="
)

THEME_BUTTON = """<button id="theme-toggle" type="button" aria-label="Toggle light and dark mode" title="Toggle theme">
  <svg class="moon" viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
  <svg class="sun" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/></svg>
</button>"""

THEME_SCRIPT = """<script>
  (function () {
    var root = document.documentElement;
    var stored = null;
    try { stored = localStorage.getItem("nc-theme"); } catch (e) {}
    var initial = stored || ((window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light");
    root.setAttribute("data-theme", initial);
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        try { localStorage.setItem("nc-theme", next); } catch (e) {}
      });
    }
  })();
</script>"""

ANALYTICS = """<script data-goatcounter="https://ncolestock.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>"""

SECTIONS = (
    ("Writing", "/"),
    ("Speaking", "/speaking/"),
    ("Index", "/index/"),
    ("Reading", "/reading/"),
    ("Thoughts", "/thoughts/"),
)

# Same block on Writing, Speaking, Reading, and Thoughts. Tabs come after it.
MASTHEAD = """    <section class="masthead">
      <div class="avatar" role="img" aria-label="Nathan Colestock"></div>
      <h1>Nathan Colestock</h1>
      <div class="role">
        <span>Pastor</span><span class="sep">·</span>
        <span>Head of School</span><span class="sep">·</span>
        <span>Husband &amp; father of four</span>
      </div>
      <p class="bio">
        I serve as a pastor at
        <a href="https://christtheking.build/" target="_blank" rel="noopener"><strong>Christ the King Church</strong></a>
        and as Head of School at
        <a href="https://valorcca.com/" target="_blank" rel="noopener"><strong>Valor Classical Academy</strong></a>.
        My wife Maddie and I are raising four children.
      </p>
      <div class="meta-row">
        <span class="place"><span class="pin" aria-hidden="true"></span> Stillwater, Minnesota</span>
        <a class="x-link" href="https://x.com/build_n_fight" target="_blank" rel="noopener me" aria-label="Nathan Colestock on X" title="@build_n_fight on X">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
          <span>@build_n_fight</span>
        </a>
      </div>
    </section>"""

TALK_JS = r"""<script>
(function () {
  var VIDEO_ID = "__VIDEO_ID__";
  var player = null;
  var cues = [];
  var buttons = [];
  var active = -1;
  var scrollLock = 0;
  var panel = document.getElementById("transcript-scroll");
  var hint = document.getElementById("transcript-hint");
  var stage = document.getElementById("talk-layout") || document.getElementById("talk-stage");
  var follow = document.getElementById("transcript");
  var collapseBtn = document.getElementById("follow-collapse");
  var expandBtn = document.getElementById("follow-expand");
  var smooth = !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var FALLBACK = "No captions are available for this talk yet. The video still plays above.";
  var followOpened = false;
  var userCollapsed = false;

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function fmt(t) {
    t = Math.max(0, Math.floor(t || 0));
    var h = Math.floor(t / 3600);
    var m = Math.floor((t % 3600) / 60);
    var s = t % 60;
    if (h) return h + ":" + pad(m) + ":" + pad(s);
    return m + ":" + pad(s);
  }
  function showExpand(show) {
    if (!expandBtn) return;
    expandBtn.hidden = !show;
  }
  function openFollow() {
    if (!stage || !follow || followOpened) return;
    follow.hidden = false;
    stage.classList.add("is-follow-open");
    followOpened = true;
    userCollapsed = false;
    showExpand(false);
  }
  function collapseFollow() {
    if (!stage || !follow) return;
    follow.hidden = true;
    stage.classList.remove("is-follow-open");
    followOpened = false;
    userCollapsed = true;
    showExpand(true);
  }
  function showFallback(message) {
    if (hint) hint.textContent = message;
    if (!panel) return;
    panel.innerHTML = "";
    var p = document.createElement("p");
    p.className = "transcript-fallback";
    p.textContent = message;
    panel.appendChild(p);
  }
  function offsetWithin(el, ancestor) {
    var y = 0;
    var node = el;
    while (node && node !== ancestor) {
      y += node.offsetTop;
      node = node.offsetParent;
    }
    return y;
  }
  function setActive(index, forceScroll) {
    if (index === active && !forceScroll) return;
    if (active >= 0 && buttons[active]) {
      buttons[active].classList.remove("is-current");
      buttons[active].removeAttribute("aria-current");
    }
    active = index;
    if (index < 0 || !buttons[index]) return;
    var el = buttons[index];
    el.classList.add("is-current");
    el.setAttribute("aria-current", "true");
    if (!panel) return;
    if (!forceScroll && Date.now() < scrollLock) return;
    var top = offsetWithin(el, panel);
    var target = top - (panel.clientHeight - el.offsetHeight) / 2;
    var max = Math.max(0, panel.scrollHeight - panel.clientHeight);
    if (target < 0) target = 0;
    if (target > max) target = max;
    panel.scrollTo({ top: target, behavior: forceScroll || !smooth ? "auto" : "smooth" });
  }
  function findCue(t) {
    var lo = 0, hi = cues.length - 1, ans = -1;
    while (lo <= hi) {
      var mid = (lo + hi) >> 1;
      if (cues[mid].start <= t + 0.08) { ans = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    if (ans < 0) return -1;
    var cue = cues[ans];
    if (t > cue.end + 0.35) {
      var next = cues[ans + 1];
      if (!next || t < next.start) {
        if (next && (next.start - cue.end) < 1.25) return ans;
        return -1;
      }
    }
    return ans;
  }
  function tick() {
    if (!player || typeof player.getCurrentTime !== "function" || !cues.length) return;
    var t = player.getCurrentTime();
    if (typeof t !== "number" || isNaN(t)) return;
    setActive(findCue(t), false);
  }
  function onStateChange(ev) {
    try {
      if (ev && ev.data === 1) {
        if (!userCollapsed) openFollow();
        else showExpand(true);
      }
    } catch (e) {}
    tick();
  }
  function render(list) {
    if (!Array.isArray(list)) list = [];
    cues = list.filter(function (c) {
      return c && typeof c.start === "number" && typeof c.text === "string" && c.text.trim();
    });
    if (!cues.length) { showFallback(FALLBACK); return; }
    if (hint) hint.textContent = "Follows the video. Click a line to jump.";
    panel.innerHTML = "";
    buttons = cues.map(function (cue, i) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cue";
      var time = document.createElement("span");
      time.className = "cue-time";
      time.textContent = fmt(cue.start);
      var text = document.createElement("span");
      text.className = "cue-text";
      text.textContent = cue.text;
      btn.appendChild(time);
      btn.appendChild(text);
      btn.addEventListener("click", function () {
        openFollow();
        setActive(i, true);
        scrollLock = Date.now() + 1600;
        if (player && typeof player.seekTo === "function") {
          player.seekTo(cue.start, true);
          try { if (player.getPlayerState() !== 1) player.playVideo(); } catch (e) {}
        }
      });
      panel.appendChild(btn);
      return btn;
    });
    tick();
  }
  if (collapseBtn) {
    collapseBtn.addEventListener("click", function () { collapseFollow(); });
  }
  if (expandBtn) {
    expandBtn.addEventListener("click", function () { openFollow(); });
  }
  if (panel) {
    ["wheel", "touchstart", "pointerdown"].forEach(function (name) {
      panel.addEventListener(name, function () { scrollLock = Date.now() + 7000; }, { passive: true });
    });
    panel.addEventListener("keydown", function (e) {
      if ({ArrowDown:1, ArrowUp:1, PageDown:1, PageUp:1, Home:1, End:1, " ":1}[e.key]) {
        scrollLock = Date.now() + 7000;
      }
    });
  }
  function mountPlayer() {
    if (player || !window.YT || !YT.Player) return;
    player = new YT.Player("yt-player", {
      events: { onReady: tick, onStateChange: onStateChange }
    });
    setInterval(tick, 250);
  }
  if (window.YT && YT.Player) {
    mountPlayer();
  } else {
    var prior = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      if (typeof prior === "function") prior();
      mountPlayer();
    };
    var api = document.createElement("script");
    api.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(api);
  }
  fetch("transcript.json", { credentials: "same-origin" })
    .then(function (res) { if (!res.ok) throw new Error("missing"); return res.json(); })
    .then(render)
    .catch(function () { showFallback(FALLBACK); });
})();
</script>
"""


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def parts(iso: str) -> tuple[int, int, int]:
    match = DATE.match(iso)
    if not match:
        raise SystemExit(f"bad date: {iso}")
    year, month, day = (int(match.group(i)) for i in (1, 2, 3))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise SystemExit(f"bad date: {iso}")
    return year, month, day


def full_date(iso: str) -> str:
    year, month, day = parts(iso)
    return f"{MONTHS[month]} {day}, {year}"


def rail_day(iso: str) -> str:
    _year, month, day = parts(iso)
    return f"{SHORT_MONTHS[month]} {day}"


def load_talks() -> list[dict]:
    raw = json.loads(TALKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("speaking/talks.json must be a list")
    if len(raw) != 18:
        raise SystemExit(f"expected 18 confirmed talks, found {len(raw)}")

    slugs: set[str] = set()
    videos: set[str] = set()
    for talk in raw:
        title = talk.get("title") or ""
        if FORBIDDEN.search(title) or FORBIDDEN.search(talk.get("scripture") or ""):
            raise SystemExit(f"refusing non-Nathan talk: {title}")
        slug = talk.get("slug") or ""
        video = talk.get("youtube") or ""
        if not SLUG.match(slug):
            raise SystemExit(f"bad slug: {slug}")
        if slug in slugs:
            raise SystemExit(f"duplicate slug: {slug}")
        slugs.add(slug)
        if not YOUTUBE_ID.match(video):
            raise SystemExit(f"bad youtube id for {slug}: {video}")
        if video in videos:
            raise SystemExit(f"duplicate youtube id: {video}")
        videos.add(video)
        parts(talk["date"])
        kind = talk.get("kind")
        scripture = talk.get("scripture")
        if kind == "sermon":
            if not scripture:
                raise SystemExit(f"sermon missing scripture: {slug}")
        elif kind == "conference":
            if scripture:
                raise SystemExit(f"conference talk should not carry scripture: {slug}")
        else:
            raise SystemExit(f"kind must be sermon or conference: {slug}")
        snippet = (talk.get("snippet") or "").strip()
        if not snippet or snippet == title:
            raise SystemExit(f"talk needs its own snippet: {slug}")
        if not 24 <= len(snippet) <= 200:
            raise SystemExit(f"snippet length out of range for {slug}: {len(snippet)}")
        talk["snippet"] = snippet

    raw.sort(key=lambda item: item["date"], reverse=True)
    return raw


def tabs(active: str) -> str:
    lines = ['    <nav class="tabs" aria-label="Sections">']
    for label, href in SECTIONS:
        if label == active:
            lines.append(
                f'      <a class="tab is-active" href="{href}" aria-current="page">{label}</a>'
            )
        else:
            lines.append(f'      <a class="tab" href="{href}">{label}</a>')
    lines.append("    </nav>")
    return "\n".join(lines)


def head(title: str, description: str, path: str) -> str:
    url = f"{SITE}{path}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Nathan Colestock">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:image" content="{SITE}/avatar.jpg">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{SITE}/avatar.jpg">
<meta name="theme-color" content="#4C5A2B">
<link rel="icon" type="image/svg+xml" href="{ICON}">
<title>{esc(title)} — Nathan Colestock</title>
<link rel="stylesheet" href="/style.css">
<link rel="stylesheet" href="/speaking/talk-header.css">
</head>"""


def chrome_close() -> str:
    return f"""{THEME_SCRIPT}

{ANALYTICS}
</body>
</html>
"""


def index_page(talks: list[dict]) -> str:
    description = "Sermons and talks by Nathan Colestock at Christ the King Church in Stillwater."
    items: list[str] = []
    year_open: int | None = None
    for talk in talks:
        year = parts(talk["date"])[0]
        if year != year_open:
            year_open = year
            items.append(
                f'      <li class="speaking-year"><h2 class="speaking-year-label">{year}</h2></li>'
            )
        kind = "Conference" if talk["kind"] == "conference" else "Sermon"
        meta_bits = [f'<span class="tag">{kind}</span>']
        if talk["scripture"]:
            meta_bits.append(f'<span>{esc(talk["scripture"])}</span>')
        meta_bits.append(
            f'<time datetime="{esc(talk["date"])}">{esc(full_date(talk["date"]))}</time>'
        )
        items.append(
            f"""      <li>
        <a class="post speaking-item" href="/speaking/{esc(talk["slug"])}/">
          <div class="speaking-date" aria-hidden="true"><span class="speaking-day">{esc(rail_day(talk["date"]))}</span></div>
          <div class="speaking-body">
            <div class="meta">{"".join(meta_bits)}</div>
            <h3>{esc(talk["title"])}</h3>
            <p class="dek">{esc(talk["snippet"])}</p>
          </div>
        </a>
      </li>"""
        )

    body = "\n".join(items)
    return f"""{head("Speaking", description, "/speaking/")}
<body>
<div id="mapbg" aria-hidden="true"></div>
{THEME_BUTTON}
<main class="view active" id="view-speaking">
  <div class="shell">
{MASTHEAD}
{tabs("Speaking")}
    <section class="speaking" aria-label="Speaking">
    <ul class="speaking-list">
{body}
    </ul>
    </section>
    <footer class="home-foot">© 2026 Nathan Colestock</footer>
  </div>
</main>
{chrome_close()}"""


def cue_count(slug: str) -> int:
    path = SPEAKING / slug / "transcript.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, list):
        return 0
    return sum(1 for cue in data if isinstance(cue, dict) and cue.get("text"))





def reading_block(slug: str) -> str:
    path = SPEAKING / slug / "reading.html"
    if not path.exists():
        return ""
    body = path.read_text(encoding="utf-8").strip()
    if not body:
        return ""
    return """      <section class="reading-transcript" aria-label="Transcript">
        %s
      </section>""" % body

def talk_page(talk: dict) -> str:
    title = talk["title"]
    kind = "Conference" if talk["kind"] == "conference" else "Sermon"
    when = full_date(talk["date"])
    scripture = talk["scripture"]
    if scripture:
        description = f"{title} — {scripture}. Nathan Colestock at Christ the King Church."
        meta_scripture = f"<span>·</span><span>{esc(scripture)}</span>"
    else:
        description = f"{title}. Nathan Colestock."
        meta_scripture = ""
    video = talk["youtube"]
    has_cues = cue_count(talk["slug"]) > 0
    if has_cues:
        stage_block = f"""      <div class="talk-layout" id="talk-layout">
        <div class="talk-main">
          <div class="talk-stage" id="talk-stage">
            <div class="video-wrap">
              <iframe id="yt-player" src="https://www.youtube.com/embed/{esc(video)}?enablejsapi=1&rel=0&playsinline=1" title="{esc(title)}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="eager" referrerpolicy="strict-origin-when-cross-origin"></iframe>
            </div>
            <button type="button" class="follow-expand" id="follow-expand" hidden>Follow along</button>
          </div>
          __READING_SLOT__
        </div>
        <section class="transcript follow-panel" id="transcript" aria-labelledby="transcript-h" hidden>
          <div class="transcript-bar">
            <div class="transcript-bar-row">
              <h2 id="transcript-h">Follow along</h2>
              <button type="button" class="follow-collapse" id="follow-collapse">Collapse</button>
            </div>
            <p class="transcript-hint" id="transcript-hint">Loading the transcript...</p>
          </div>
          <div class="transcript-scroll" id="transcript-scroll" tabindex="0" aria-label="Follow-along lines"></div>
        </section>
      </div>
      <noscript>
        <div class="video-wrap">
          <iframe src="https://www.youtube.com/embed/{esc(video)}" title="{esc(title)}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="eager" referrerpolicy="strict-origin-when-cross-origin"></iframe>
        </div>
      </noscript>"""
        player = "\n" + TALK_JS.replace("__VIDEO_ID__", video)
    else:
        stage_block = f"""      <div class="talk-stage" id="talk-stage">
        <div class="video-wrap">
          <iframe src="https://www.youtube.com/embed/{esc(video)}" title="{esc(title)}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen loading="eager" referrerpolicy="strict-origin-when-cross-origin"></iframe>
        </div>
      </div>"""
        player = ""

    return f"""{head(title, description, f"/speaking/{talk['slug']}/")}
<body>
<div id="mapbg" aria-hidden="true"></div>
{THEME_BUTTON}
<main class="view active">
  <div class="shell shell-talk">
    <a class="backlink" href="/speaking/">← Speaking</a>
    <article class="speaking-talk">
      <header class="art-head">
        <div class="art-meta"><span class="tag">{kind}</span><time datetime="{esc(talk["date"])}">{esc(when)}</time>{meta_scripture}</div>
        <h1 class="art-title">{esc(title)}</h1>
        <div class="art-byline">
          <span class="pic" role="img" aria-label="Nathan Colestock"></span>
          <span class="who"><b>Nathan Colestock</b><small>Christ the King Church</small></span>
        </div>
      </header>
      <div class="rule"></div>
{stage_block.replace("__READING_SLOT__", reading_block(talk["slug"])) if has_cues else (stage_block + "\n" + reading_block(talk["slug"]))}
    </article>
    <footer class="home-foot">© 2026 Nathan Colestock</footer>
  </div>
</main>
{player}
{chrome_close()}"""



def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    talks = load_talks()
    write(SPEAKING / "index.html", index_page(talks))
    # Reserved dirs the talk cleanup must not remove
    reserved = {"mens-preconference-2"}
    keep = set(reserved)
    for talk in talks:
        keep.add(talk["slug"])
        write(SPEAKING / talk["slug"] / "index.html", talk_page(talk))
    for child in SPEAKING.iterdir():
        if child.is_dir() and child.name not in keep:
            shutil.rmtree(child)
    write(
        ROOT / "index" / "index.html",
        render_scripture_index(
            talks,
            esc=esc,
            full_date=full_date,
            head=head,
            tabs=tabs,
            masthead=MASTHEAD,
            theme_button=THEME_BUTTON,
            chrome_close=chrome_close,
        ),
    )
    print(f"wrote {len(talks)} talks, newest {talks[0]['date']}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
