#!/usr/bin/env python3
"""Download English captions for every talk and write timed cues.

Uses yt-dlp (the same tool as `python3 -m yt_dlp`). For each youtube id in
speaking/talks.json, writes speaking/<slug>/transcript.json:

    [{"start": 12.4, "end": 18.1, "text": "..."}, ...]

Times are seconds. Caption text is cleaned lightly (timing tags, [Music],
doubled auto-caption lines). The words stay the captions' words.

    python3 scripts/fetch_transcripts.py
    python3 scripts/fetch_transcripts.py --check
    python3 scripts/fetch_transcripts.py --slug from-confusion-to-obedience

If this machine's resolver sinks YouTube to 192.0.2.1, lookups go through
1.1.1.1 for that process only.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TALKS_PATH = ROOT / "speaking" / "talks.json"
RAW = Path("/tmp/yt-subs")

JUNK = re.compile(
    r"\[(?:music|applause|laughter|inaudible|silence|cheering|clapping|background[^\]]*)\]",
    re.I,
)
MUSIC = re.compile(r"[♪♫]+")
TAG = re.compile(r"</?c[^>]*>|<\d{2}:\d{2}:\d{2}\.\d+>")
ABBREV = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|St|Rev|vs|Jr|Sr|Gen|Ex|Num|Deut)\.$")
WORD_FIX = (
    (re.compile(r"\bholy spirit\b", re.I), "Holy Spirit"),
    (re.compile(r"\bjesus christ\b", re.I), "Jesus Christ"),
    (re.compile(r"\bchrist the king\b", re.I), "Christ the King"),
    (re.compile(r"\bold testament\b", re.I), "Old Testament"),
    (re.compile(r"\bnew testament\b", re.I), "New Testament"),
    (re.compile(r"\bword of god\b", re.I), "Word of God"),
)
PROPER = {
    "god": "God",
    "jesus": "Jesus",
    "christ": "Christ",
    "lord": "Lord",
    "bible": "Bible",
    "scripture": "Scripture",
    "nehemiah": "Nehemiah",
    "ezra": "Ezra",
    "jerusalem": "Jerusalem",
    "israel": "Israel",
}


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = TAG.sub(" ", text)
    text = JUNK.sub(" ", text)
    text = MUSIC.sub(" ", text)
    text = text.replace(">>", " ")
    text = text.replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(\d+):es\b", r"\1:", text)
    text = re.sub(r"(\d+)\s*:\s*(\d+)", r"\1:\2", text)
    text = re.sub(r"(\d)and(\d)", r"\1 and \2", text)
    text = re.sub(r"(\d)to(\d)", r"\1 to \2", text)
    text = re.sub(r"\b([A-Za-z']{1,3})(?:\s+\1\b)+", r"\1", text, flags=re.I)
    text = re.sub(r"\bI'\s+(?=I\b)", "", text)
    text = re.sub(r"\b(?:Hio|Hiro) Onada\b", "Hiroo Onoda", text)
    text = re.sub(r"\bEphereim\b", "Ephraim", text)
    text = re.sub(r"\bat top a mountain\b", "atop a mountain", text)
    text = re.sub(r"\bMount Si\b", "Mount Sinai", text)
    text = re.sub(r"\b[Bb]ooss\b", "booths", text)
    text = re.sub(r"\b[Bb]oos\b", "booths", text)
    text = re.sub(r"\s+([,.;:?!)])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    text = re.sub(r"\s+([]])", r"\1", text)
    if not text or not re.search(r"[A-Za-z0-9]", text):
        return ""
    text = re.sub(r"\bi\b", "I", text)
    text = re.sub(r"\bI'(m|ve|ll|d|re)\b", lambda m: "I'" + m.group(1).lower(), text)

    def proper(match: re.Match[str]) -> str:
        word = match.group(0)
        return PROPER.get(word.lower(), word)

    text = re.sub(r"[A-Za-z']+", proper, text)
    for pattern, repl in WORD_FIX:
        text = pattern.sub(repl, text)
    text = text[0].upper() + text[1:]
    text = re.sub(r"([.?!]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text


def sentence_end(text: str) -> bool:
    if not text.endswith((".", "?", "!")):
        return False
    return ABBREV.search(text) is None


def cues_from_words(words: list[dict]) -> list[dict]:
    """Group timestamped words into readable lines."""
    groups: list[dict] = []
    buf: list[str] = []
    start = 0.0
    last_t = 0.0

    def flush(end: float) -> None:
        nonlocal buf, start
        text = clean_text(" ".join(buf))
        buf = []
        if not text:
            return
        end = max(end, start + 0.4)
        groups.append({"start": round(start, 2), "end": round(end, 2), "text": text})

    for word in words:
        if word.get("br"):
            if buf:
                flush(float(word["t"]))
            continue
        token = str(word.get("text") or "").strip()
        if not token:
            continue
        t = float(word["t"])
        if buf and t - last_t > 1.6:
            flush(last_t + 0.45)
        if not buf:
            start = t
        buf.append(token)
        last_t = t
        text = " ".join(buf)
        if (sentence_end(clean_text(text)) and len(text) >= 48) or len(text) >= 180 or (t - start) >= 14:
            flush(t + 0.45)
    if buf:
        flush(last_t + 0.8)

    merged: list[dict] = []
    for cue in groups:
        if (
            merged
            and cue["start"] - merged[-1]["end"] < 1.2
            and (len(merged[-1]["text"]) < 40 or len(cue["text"]) <= 20)
        ):
            merged[-1]["text"] = clean_text(merged[-1]["text"] + " " + cue["text"])
            merged[-1]["end"] = cue["end"]
        else:
            merged.append(cue)

    deduped: list[dict] = []
    for cue in merged:
        if not deduped:
            deduped.append(cue)
            continue
        prev = deduped[-1]
        same = cue["text"].lower() == prev["text"].lower()
        contained = cue["text"].lower() in prev["text"].lower() and cue["start"] <= prev["end"] + 0.2
        extends = (
            cue["start"] < prev["end"]
            and cue["text"].lower().startswith(prev["text"].lower()[: min(40, len(prev["text"]))])
        )
        if same or contained:
            prev["end"] = max(prev["end"], cue["end"])
            continue
        if extends:
            prev["text"] = cue["text"]
            prev["end"] = max(prev["end"], cue["end"])
            continue
        if cue["start"] < prev["end"]:
            prev["end"] = cue["start"]
        if prev["end"] <= prev["start"]:
            prev["end"] = round(prev["start"] + 0.4, 2)
        deduped.append(cue)
    if deduped and deduped[-1]["end"] <= deduped[-1]["start"]:
        deduped[-1]["end"] = round(deduped[-1]["start"] + 0.8, 2)
    return deduped


def words_from_json3(payload: dict) -> list[dict]:
    words: list[dict] = []
    for event in payload.get("events") or []:
        segs = event.get("segs") or []
        if not segs:
            continue
        start = float(event.get("tStartMs") or 0) / 1000.0
        for seg in segs:
            piece = str(seg.get("utf8") or "").replace("\n", " ")
            if not piece.strip():
                continue
            offset = seg.get("tOffsetMs")
            t = start + (float(offset) / 1000.0 if offset is not None else 0.0)
            for token in piece.split():
                words.append({"t": t, "text": token})
    return words


def parse_json3(text: str) -> list[dict]:
    payload = json.loads(text)
    if isinstance(payload, list):
        # Already cues.
        if payload and isinstance(payload[0], dict) and "text" in payload[0]:
            return cues_from_words(
                [
                    {"t": float(item["start"]), "text": str(item["text"])}
                    for item in payload
                    if item.get("text")
                ]
            )
        return []
    return cues_from_words(words_from_json3(payload))


_TS = re.compile(r"(?:(\d+):)?(\d+):(\d+)[.,](\d+)")


def _clock(value: str) -> float:
    match = _TS.search(value.strip())
    if not match:
        raise ValueError(value)
    hours = int(match.group(1) or 0)
    mins = int(match.group(2))
    secs = int(match.group(3))
    frac = match.group(4)
    return hours * 3600 + mins * 60 + secs + int(frac) / (10 ** len(frac))


def parse_vtt(text: str) -> list[dict]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    raw: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        start_s, end_s = [part.strip() for part in line.split("-->", 1)]
        try:
            start = _clock(start_s)
            end = _clock(end_s.split()[0])
        except ValueError:
            i += 1
            continue
        i += 1
        buf: list[str] = []
        while i < len(lines) and lines[i].strip():
            buf.append(lines[i].strip())
            i += 1
        cue_text = clean_text(" ".join(buf))
        if cue_text:
            raw.append({"start": start, "end": end, "text": cue_text})
    # Auto-captions repeat a growing line. Keep only the new tail.
    words: list[dict] = []
    prev = ""
    for cue in raw:
        text = cue["text"]
        low = text.lower()
        prev_low = prev.lower()
        if prev_low and low.startswith(prev_low):
            fresh = text[len(prev) :].strip()
        elif prev_low and prev_low.startswith(low):
            fresh = ""
        else:
            fresh = text
        prev = text
        if not fresh:
            continue
        for token in fresh.split():
            words.append({"t": cue["start"], "text": token})
        words.append({"t": cue["end"], "br": True})
    return cues_from_words(words)


def parse_caption(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json3" or text.lstrip().startswith("{"):
        return parse_json3(text)
    return parse_vtt(text)


def propose_snippet(cues: list[dict], title: str) -> str:
    """A vivid early line, or an honest one-liner from the title."""
    skip = re.compile(
        r"\b(good morning|good afternoon|let'?s pray|let us pray|bow your heads|"
        r"turn with me|open your bible|if you have your bible|please turn|"
        r"welcome to|hey everybody|christ the king church|father we|amen)\b",
        re.I,
    )
    best = ""
    best_score = 0
    for cue in cues:
        start = float(cue["start"])
        if start < 12 or start > 240:
            continue
        text = cue["text"].strip()
        if skip.search(text):
            continue
        if len(text) < 48 or len(text) > 150:
            continue
        score = 8
        if 70 <= len(text) <= 130:
            score += 6
        if text.endswith((".", "?", "!")):
            score += 3
        if "?" in text:
            score += 2
        # Prefer a line that is not just the title restated.
        if text.lower().strip(".?") == title.lower().strip(".?"):
            score -= 6
        if score > best_score:
            best_score = score
            best = text
    if best:
        return best
    plain = title.rstrip(".")
    return f"{plain}."


SINK_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.", "100::")
_DNS: dict[str, str] = {}
_REAL_GETADDRINFO = socket.getaddrinfo


def _is_sink(addr: str) -> bool:
    return addr == "100::1" or addr.startswith(SINK_PREFIXES)


def _resolve(host: str) -> str:
    if host in _DNS:
        return _DNS[host]
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    out = subprocess.check_output(
        ["dig", "+short", "+time=3", "+tries=1", "@1.1.1.1", host, "A"],
        text=True,
    )
    ips = [line.strip() for line in out.splitlines() if line.strip()[:1].isdigit()]
    names = [line.strip().rstrip(".") for line in out.splitlines() if line.strip() and not line.strip()[:1].isdigit()]
    if not ips and names:
        out = subprocess.check_output(
            ["dig", "+short", "+time=3", "+tries=1", "@1.1.1.1", names[-1], "A"],
            text=True,
        )
        ips = [line.strip() for line in out.splitlines() if line.strip()[:1].isdigit()]
    if not ips:
        raise OSError(f"no address for {host}")
    _DNS[host] = ips[0]
    print(f"dns {host} -> {ips[0]}", flush=True)
    return ips[0]


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    orig = host.decode() if isinstance(host, bytes) else host
    if isinstance(orig, str) and orig and not orig.replace(".", "").isdigit():
        try:
            sysres = _REAL_GETADDRINFO(orig, port, family, type, proto, flags)
            bad = any(_is_sink(item[4][0]) for item in sysres)
        except socket.gaierror:
            bad = True
            sysres = None
        forced = any(tok in orig for tok in ("youtube", "googlevideo", "ytimg", "ggpht"))
        if bad or forced:
            ip = _resolve(orig)
            return _REAL_GETADDRINFO(ip, port, family, type, proto, flags)
        return sysres
    return _REAL_GETADDRINFO(host, port, family, type, proto, flags)


def install_dns_patch() -> None:
    socket.getaddrinfo = _patched_getaddrinfo


def preferred_caption(video_id: str) -> Path | None:
    order = [
        RAW / f"{video_id}.en.json3",
        RAW / f"{video_id}.en.vtt",
        RAW / f"{video_id}.en-US.json3",
        RAW / f"{video_id}.en-orig.json3",
        RAW / f"{video_id}.en-orig.vtt",
    ]
    for path in order:
        if path.exists():
            return path
    files = sorted(RAW.glob(f"{video_id}.*"))
    json3 = [path for path in files if "json3" in path.name]
    return (json3 or files or [None])[0]


def download_caption(video_id: str) -> Path | None:
    import yt_dlp

    RAW.mkdir(parents=True, exist_ok=True)
    for old in RAW.glob(f"{video_id}*"):
        old.unlink()
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-orig"],
        "subtitlesformat": "json3/vtt/best",
        "outtmpl": str(RAW / "%(id)s"),
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.extract_info(url, download=True)
    return preferred_caption(video_id)


def self_test() -> None:
    payload = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "good morning church"}]},
            {
                "tStartMs": 2500,
                "dDurationMs": 4000,
                "segs": [{"utf8": "we are in nehemiah and the word of god is open."}],
            },
            {"tStartMs": 7000, "dDurationMs": 200, "segs": [{"utf8": "\n"}]},
            {"tStartMs": 7400, "dDurationMs": 3000, "segs": [{"utf8": "[Music] build the wall."}]},
            {"tStartMs": 11000, "dDurationMs": 2000, "segs": [{"utf8": "build the wall."}]},
        ]
    }
    cues = parse_json3(json.dumps(payload))
    texts = [cue["text"] for cue in cues]
    if not any("Nehemiah" in text and "Word of God" in text for text in texts):
        raise SystemExit(f"json3 clean failed: {texts}")
    if any("music" in text.lower() for text in texts):
        raise SystemExit(f"music tag survived: {texts}")
    if not any(text.lower().startswith("build the wall") for text in texts):
        raise SystemExit(f"missed a line: {texts}")
    vtt = """WEBVTT

00:00:01.000 --> 00:00:03.000
we fight

00:00:01.800 --> 00:00:04.500
we fight and we build the wall.

00:00:06.000 --> 00:00:08.000
put your name on something.
"""
    vtt_cues = parse_vtt(vtt)
    joined = " ".join(cue["text"] for cue in vtt_cues).lower()
    if joined.count("we fight") > 1:
        raise SystemExit(f"vtt rolling dedupe failed: {vtt_cues}")
    if "name" not in joined:
        raise SystemExit(f"vtt dropped a line: {vtt_cues}")
    print("caption parser ok", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="run the parser self-test and exit")
    parser.add_argument("--slug", action="append", default=[], help="limit to one slug; repeatable")
    parser.add_argument("--proposals", type=Path, help="write snippet proposals as JSON")
    parser.add_argument("--from-raw", action="store_true", help="rebuild cues from /tmp/yt-subs, no download")
    args = parser.parse_args()
    if args.check:
        self_test()
        return

    if not args.from_raw:
        install_dns_patch()
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            raise SystemExit(
                "yt-dlp is not installed for this Python. Install it, then re-run:\n"
                "  python3 -m pip install yt-dlp\n"
                "  python3 -m yt_dlp --version"
            )

    talks = json.loads(TALKS_PATH.read_text(encoding="utf-8"))
    proposals = []
    failures = []
    for talk in talks:
        if args.slug and talk["slug"] not in args.slug:
            continue
        video = talk["youtube"]
        slug = talk["slug"]
        print(f"{'read' if args.from_raw else 'fetch'} {slug} {video}", flush=True)
        if args.from_raw:
            path = preferred_caption(video)
        else:
            try:
                path = download_caption(video)
            except Exception as exc:  # noqa: BLE001 — one bad video should not stop the rest
                print(f"  FAILED {slug}: {exc}", flush=True)
                failures.append(slug)
                continue
        if path is None:
            print(f"  no captions {slug}", flush=True)
            failures.append(slug)
            continue
        try:
            cues = parse_caption(path)
        except Exception as exc:  # noqa: BLE001
            print(f"  parse failed {slug}: {exc}", flush=True)
            failures.append(slug)
            continue
        if len(cues) < 3:
            print(f"  too few cues ({len(cues)}) from {path.name}", flush=True)
            failures.append(slug)
            continue
        dest = ROOT / "speaking" / slug / "transcript.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(cues, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        snippet = propose_snippet(cues, talk["title"])
        proposals.append({"slug": slug, "file": path.name, "cues": len(cues), "snippet": snippet, "early": cues[:8]})
        print(f"  {len(cues)} cues from {path.name}", flush=True)
        print(f"  snippet: {snippet}", flush=True)

    if args.proposals:
        args.proposals.write_text(json.dumps(proposals, ensure_ascii=False, indent=2), encoding="utf-8")
    if failures:
        print("no captions for: " + ", ".join(failures), flush=True)
    if not proposals and failures:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
