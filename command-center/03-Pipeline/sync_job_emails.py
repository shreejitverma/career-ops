#!/usr/bin/env python3
"""Sync job-search email from Apple Mail into the Interview Command Center.

Pipeline:
  1. fetch   - read recent messages from the Apple Mail accounts below (AppleScript),
               or from a JSON fixture with --from-json (no Mail needed; used by tests).
  2. filter  - keep job-related messages (dedicated folders, or keyword match).
  3. classify- label each message: offer, rejection, assessment, interview,
               recruiter, received, or other; suggest the pipeline stage it implies.
  4. match   - link it to a tracker note by company name or recruiter email domain.
  5. record  - append new events to .sync/events.jsonl (keyed by a content hash,
               so re-running never duplicates anything).
  6. review  - regenerate _Inbox-Review.md: recent events, and the trackers whose
               current stage disagrees with what the email suggests.
  7. apply   - with --apply, add one dated line per name-matched event to the tracker's
               "## Timeline" section, tagged with its event id so it is added once.
               Domain-only matches (e.g. an agency recruiter) appear only in the review note.

Frontmatter is never modified: stage and every other field stay under human
control; the review note only suggests changes.

Usage:
  sync_job_emails.py --mode daily            # fetch, record, refresh review note
  sync_job_emails.py --mode daily --apply    # also append tracker timeline lines
  sync_job_emails.py --dry-run               # show what would change, write nothing
  sync_job_emails.py --from-json FILE        # use a fixture instead of Apple Mail
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from tracker_frontmatter import read_frontmatter, read_list

PIPELINE = Path(__file__).resolve().parent
STATE_DIR = PIPELINE / ".sync"
EVENTS = STATE_DIR / "events.jsonl"
REVIEW = PIPELINE / "_Inbox-Review.md"
TRACKER_DIRS = ("Active", "Archive")

# Accounts and mailboxes to monitor.
TARGET_ACCOUNTS = [
    ("Exchange", ["Interviews", "Rejections", "In Progress", "GA Job", "BigInterview", "Career Brew", "Bloomberg", "Ford", "Inbox"]),
    ("Google", ["Bank of America", "Rejections", "Job"]),
    ("sverma357@gatech.edu", ["JOB", "Inbox"]),
    ("shreejitverma1234@gmail.com", ["Work", "INBOX"]),
    ("shreejitfinance@gmail.com", ["INBOX"]),
    ("shreejitabroad@gmail.com", ["INBOX"]),
    ("vermashreejit@gmail.com", ["INBOX"]),
    ("sverma16@stevens.edu", ["INBOX"]),
    ("iCloud", ["INBOX"]),
]
DEDICATED_HINTS = ("interview", "rejection", "job", "bank of america")

# Shared ATS and platform domains: they send mail for many companies, so they never identify a tracker.
SHARED_DOMAINS = (
    "greenhouse-mail.io", "greenhouse.io", "lever.co", "myworkday.com", "workday.com", "linkedin.com",
    "hackerrankforwork.com", "hackerrank.com", "criteriacorp.com", "icims.com", "ashbyhq.com",
    "smartrecruiters.com", "jobvite.com", "taleo.net",
)

JOB_KEYWORDS = [
    "interview", "application", "assessment", "hackerrank", "codesignal",
    "karat", "codility", "recruiter", "hiring", "offer", "rejection",
    "status of your application", "next steps", "phone screen", "technical round",
    "onsite", "take-home", "right to represent", "congratulations",
    "thank you for your interest", "applied", "candidacy", "position", "candidate",
    "rtr", "exclusivity", "screening",
]
EXCLUDE_PATTERNS = [
    "job alert", "jobs you may like", "recommended jobs", "daily job alert",
    "weekly digest", "newsletter", "promotions", "uber", "delivery", "order",
    "run failed", "jobright", "flipboard", "weekly wisdom", "samsung",
    "notifications@github.com", "e2ma.net", "substack.com", "biginterview.com",
]

# Signal -> pattern, checked in priority order (an offer email may also say "interview").
SIGNALS: list[tuple[str, re.Pattern]] = [
    ("offer", re.compile(r"pleased to (extend|offer)|offer (letter|of employment)|extend (you )?an offer", re.I)),
    ("rejection", re.compile(
        r"regret to inform|not (be )?moving forward|decided to (move|proceed) forward with other|"
        r"pursue other candidates|position has been filled|no longer under consideration|"
        r"will not be (progressing|proceeding)|unfortunately,? (we|after)", re.I)),
    ("assessment", re.compile(r"hackerrank|codesignal|codility|\bkarat\b|assessment|take-home|coding challenge|online test", re.I)),
    ("interview", re.compile(r"interview|phone screen|onsite|on-site|superday|final round|schedule (a )?(call|time)|your availability", re.I)),
    ("recruiter", re.compile(r"right to represent|\brtr\b|exclusivity|recruiter|opportunity", re.I)),
    ("received", re.compile(r"thank you for (applying|your application|your interest)|application (was )?(received|submitted)|we have received", re.I)),
]
ONSITE_RE = re.compile(r"onsite|on-site|superday|final round", re.I)

# Canonical pipeline stages, in order (see _Application-Schema.md).
STAGES = ["sourced", "applied", "recruiter", "OA", "phone", "onsite", "offer", "rejected", "withdrawn", "ghosted"]


def suggest_stage(signal: str, text: str) -> str | None:
    if signal == "interview":
        return "onsite" if ONSITE_RE.search(text) else "phone"
    return {"offer": "offer", "rejection": "rejected", "assessment": "OA",
            "recruiter": "recruiter", "received": "applied"}.get(signal)


@dataclass
class Tracker:
    path: Path
    company: str
    stage: str
    domains: set[str] = field(default_factory=set)
    aliases: list[str] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        """Company name plus Obsidian `aliases`, e.g. Fidelity for Fidelity Investments."""
        return [self.company, *self.aliases]


@dataclass
class Event:
    id: str
    date: str
    account: str
    mailbox: str
    subject: str
    sender: str
    signal: str
    suggested_stage: str | None
    tracker: str | None  # path relative to PIPELINE
    match: str | None = None  # "name" (company named in the email) or "domain" (sender domain only)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True)


# -- fetch -----------------------------------------------------------------------

def run_applescript(script: str, timeout_sec: int = 50) -> str:
    try:
        p = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout_sec)
        return p.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except OSError as e:
        print(f"warning: AppleScript error: {e}", file=sys.stderr)
        return ""


def fetch_mailbox_messages(acc: str, mb_name: str, limit: int = 30) -> list[dict]:
    script = f"""
    tell application "Mail"
        set accObj to account "{acc}"
        set mbList to (every mailbox of accObj whose name is "{mb_name}")
        if (count of mbList) is 0 then return "EMPTY"
        set mb to item 1 of mbList
        set msgCount to count of messages of mb
        if msgCount is 0 then return "EMPTY"
        set maxItems to {limit}
        if msgCount < maxItems then set maxItems to msgCount
        set outText to ""
        repeat with i from 1 to maxItems
            try
                set m to message i of mb
                set s to subject of m
                set snd to sender of m
                set dt to (date received of m as string)
                set msgContent to content of m
                set snippetLen to length of msgContent
                if snippetLen > 400 then set snippetLen to 400
                if snippetLen > 0 then
                    set snip to text 1 thru snippetLen of msgContent
                else
                    set snip to ""
                end if
                set outText to outText & s & "\u00abFIELD\u00bb" & snd & "\u00abFIELD\u00bb" & dt & "\u00abFIELD\u00bb" & snip & "\u00abRECORD\u00bb"
            end try
        end repeat
        return outText
    end tell
    """
    raw = run_applescript(script)
    if not raw or raw == "EMPTY":
        return []
    records = []
    for entry in raw.split("\u00abRECORD\u00bb"):
        parts = entry.split("\u00abFIELD\u00bb")
        if entry.strip() and len(parts) >= 4:
            records.append({
                "account": acc, "mailbox": mb_name, "subject": parts[0].strip(), "sender": parts[1].strip(),
                "date": parts[2].strip(), "snippet": parts[3].strip().replace("\r", " ").replace("\n", " "),
            })
    return records


def fetch_all(mode: str) -> list[dict]:
    limit = 20 if mode == "daily" else 60
    out = []
    for acc, mailboxes in TARGET_ACCOUNTS:
        for mb in mailboxes:
            dedicated = any(w in mb.lower() for w in DEDICATED_HINTS)
            msgs = fetch_mailbox_messages(acc, mb, limit=limit if dedicated else (15 if mode == "daily" else 40))
            for m in msgs:
                m["dedicated"] = dedicated
            out += msgs
    return out


# -- filter, classify, match ------------------------------------------------------

def is_job_related(msg: dict) -> bool:
    if msg.get("dedicated"):
        return True
    combined = f"{msg['subject']} {msg['sender']} {msg.get('snippet', '')}".lower()
    if any(ex in combined for ex in EXCLUDE_PATTERNS):
        return False
    return any(k in combined for k in JOB_KEYWORDS)


def classify(msg: dict) -> str:
    text = f"{msg['subject']} {msg.get('snippet', '')}"
    return next((name for name, rx in SIGNALS if rx.search(text)), "other")


def parse_date(raw: str) -> str:
    """Apple Mail dates look like 'Friday, August 28, 2026 at 1:00:10\u202fPM'; keep ISO dates as-is."""
    text = " ".join(raw.replace("\u202f", " ").replace("\u00a0", " ").split())
    for fmt in ("%A, %B %d, %Y at %I:%M:%S %p", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def is_iso_date(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))


def load_trackers(root: Path = PIPELINE) -> list[Tracker]:
    trackers = []
    for d in TRACKER_DIRS:
        for p in sorted((root / d).rglob("*.md")):
            text = p.read_text(errors="ignore")
            fm = read_frontmatter(text)
            if not fm.get("company") or "stage" not in fm:
                continue
            domains = {e.rsplit("@", 1)[1].lower() for e in re.findall(r"[\w.+-]+@[\w.-]+", " ".join(fm.values()))}
            trackers.append(Tracker(p, fm["company"], fm.get("stage", ""), domains, read_list(text, "aliases")))
    return trackers


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def words(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def is_shared_domain(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in SHARED_DOMAINS)


def name_matches(company: str, hay: str) -> bool:
    """Whole-word match, so 'drw' does not hit inside 'hdrworks'. Names of 6+ compact characters also match
    ignoring punctuation and spacing, so 'ATT-Labs' matches 'AT&T Labs' and 'morganstanley.com' matches 'Morgan Stanley'."""
    phrase, compact = words(company), norm(company)
    if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", hay):
        return True
    return len(compact) >= 6 and compact in norm(hay)


def match_tracker(msg: dict, trackers: list[Tracker]) -> tuple[Tracker | None, str | None]:
    """Return the tracker and how it matched: 'name' (company named in the email) or 'domain' (sender domain only)."""
    hay = words(f"{msg['subject']} {msg['sender']}")
    def matched(t: Tracker) -> int:
        """Length of the longest of the tracker's names found in the email, or 0."""
        return max((len(norm(n)) for n in t.names if len(norm(n)) >= 3 and name_matches(n, hay)), default=0)

    best = [(matched(t), t) for t in trackers]
    best = [(n, t) for n, t in best if n]
    if best:
        # prefer the longest matching name (e.g. "Morgan Stanley" over "Morgan"), and active over archived
        best.sort(key=lambda nt: (nt[0], "/Active/" in str(nt[1].path)), reverse=True)
        return best[0][1], "name"
    sender_domain = (re.findall(r"@([\w.-]+)", msg["sender"]) or [""])[-1].lower()
    if not sender_domain or is_shared_domain(sender_domain):
        return None, None
    owners = [t for t in trackers if sender_domain in t.domains]
    return (owners[0], "domain") if len({t.company for t in owners}) == 1 else (None, None)


def event_id(msg: dict) -> str:
    """Keyed on the message, not the mailbox: one Gmail message under two labels is one event."""
    key = "|".join(msg.get(k, "") for k in ("account", "subject", "sender", "date"))
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def find_tracker(rel: str, root: Path = PIPELINE) -> Path | None:
    """Resolve a recorded tracker path, following the file if it moved between Active/ and Archive/."""
    path = root / rel
    if path.exists():
        return path
    name = Path(rel).name
    return next((p for d in TRACKER_DIRS for p in sorted((root / d).rglob(name))), None)


def to_event(msg: dict, trackers: list[Tracker], root: Path = PIPELINE) -> Event:
    signal = classify(msg)
    t, how = match_tracker(msg, trackers)
    return Event(
        id=event_id(msg), date=parse_date(msg["date"]), account=msg["account"], mailbox=msg["mailbox"],
        subject=msg["subject"], sender=msg["sender"], signal=signal,
        suggested_stage=suggest_stage(signal, f"{msg['subject']} {msg.get('snippet', '')}"),
        tracker=str(t.path.relative_to(root)) if t else None, match=how,
    )


# -- record, review, apply ------------------------------------------------------------

def load_events(path: Path = EVENTS) -> dict[str, Event]:
    events = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                d["date"] = parse_date(d["date"])
                events[d["id"]] = Event(**d)
    return events


def record(new: list[Event], path: Path = EVENTS, dry_run: bool = False) -> list[Event]:
    known = load_events(path)
    fresh, seen = [], set(known)
    for e in new:
        if e.id not in seen:
            fresh.append(e)
            seen.add(e.id)
    if fresh and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            for e in fresh:
                f.write(e.to_json() + "\n")
    return fresh


def stage_rank(stage: str) -> int:
    s = stage.strip().lower()
    for i, name in enumerate(STAGES):
        if s == name.lower():
            return i
    return -1


def render_review(events: dict[str, Event], trackers: list[Tracker], today: str, days: int = 30,
                  root: Path = PIPELINE) -> str:
    since = (datetime.fromisoformat(today) - timedelta(days=days)).date().isoformat()
    recent = sorted((e for e in events.values() if is_iso_date(e.date) and e.date >= since),
                    key=lambda e: e.date, reverse=True)
    by_stem = {t.path.stem: t for t in trackers}

    def link(e: Event) -> str:
        if not e.tracker:
            return "unmatched"
        return f"[[{Path(e.tracker).stem}]]" + ("" if e.match == "name" else " (domain match, check)")

    attention = []
    for e in recent:
        t = by_stem.get(Path(e.tracker).stem) if e.tracker else None
        if t and e.suggested_stage and e.suggested_stage.lower() != t.stage.strip().lower():
            if e.suggested_stage in ("rejected", "offer") or stage_rank(e.suggested_stage) > stage_rank(t.stage):
                attention.append((e, t))

    lines = [
        "---", "type: playbook", "status: draft", "---", "",
        "# Inbox review", "",
        f"Generated by `sync_job_emails.py` on {today}; it is overwritten on every run.",
        "The sync never edits tracker frontmatter: update `stage` yourself when a suggestion is right.", "",
        "## Needs attention", "",
    ]
    if attention:
        lines += ["| Date | Tracker | Current stage | Email suggests | Subject |", "| :--- | :--- | :--- | :--- | :--- |"]
        lines += [f"| {e.date} | {link(e)} | {t.stage or '-'} | {e.suggested_stage} | {e.subject.replace('|', '/')} |" for e, t in attention]
    else:
        lines.append("Nothing: every matched email agrees with its tracker's stage.")
    untracked = [e for e in recent if not e.tracker and e.signal not in ("other", "received")]
    lines += ["", "## Possible untracked applications", ""]
    if untracked:
        lines += ["Job emails with a clear signal that match no tracker; create a tracker if they are real applications.", "",
                  "| Date | Signal | From | Subject |", "| :--- | :--- | :--- | :--- |"]
        lines += [f"| {e.date} | {e.signal} | {e.sender.replace('|', '/')} | {e.subject.replace('|', '/')} |" for e in untracked]
    else:
        lines.append("None.")
    lines += ["", f"## Last {days} days", ""]
    if recent:
        lines += ["| Date | Tracker | Signal | Subject |", "| :--- | :--- | :--- | :--- |"]
        lines += [f"| {e.date} | {link(e)} | {e.signal} | {e.subject.replace('|', '/')} |" for e in recent]
    else:
        lines.append("No job-related email in this window.")
    return "\n".join(lines) + "\n"


def apply_timeline(events: list[Event], root: Path = PIPELINE, dry_run: bool = False) -> int:
    """Append one line per name-matched event under '## Timeline'; the evt marker makes it idempotent.
    Domain-only matches are left to the review note: an agency domain also sends mail about other companies."""
    added = 0
    for e in sorted(events, key=lambda e: e.date):
        if not e.tracker or e.match != "name" or e.signal == "other":
            continue
        path = find_tracker(e.tracker, root)
        if path is None:
            print(f"warning: tracker {e.tracker} not found; skipping event {e.id}", file=sys.stderr)
            continue
        text = path.read_text()
        marker = f"<!-- evt:{e.id} -->"
        if marker in text:
            continue
        entry = f"- {e.date} {e.signal}: {e.subject} {marker}"
        if "\n## Timeline\n" in text:
            head, tail = text.split("\n## Timeline\n", 1)
            body_end = re.search(r"\n## ", tail)
            cut = body_end.start() if body_end else len(tail.rstrip("\n"))
            text = head + "\n## Timeline\n" + tail[:cut].rstrip("\n") + "\n" + entry + tail[cut:]
            if not text.endswith("\n"):
                text += "\n"
        else:
            text = text.rstrip("\n") + "\n\n## Timeline\n\n" + entry + "\n"
        added += 1
        if not dry_run:
            path.write_text(text)
    return added


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["daily", "full"], default="daily")
    ap.add_argument("--from-json", type=Path, help="read messages from a JSON list instead of Apple Mail")
    ap.add_argument("--apply", action="store_true", help="append timeline lines to matched trackers")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--today", default=datetime.now().date().isoformat(), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    msgs = json.loads(args.from_json.read_text()) if args.from_json else fetch_all(args.mode)
    trackers = load_trackers()
    events = [to_event(m, trackers) for m in msgs if is_job_related(m)]
    fresh = record(events, dry_run=args.dry_run)
    all_events = load_events()
    if args.dry_run:
        all_events.update({e.id: e for e in fresh})
    review = render_review(all_events, trackers, args.today)
    added = apply_timeline(list(all_events.values()), dry_run=args.dry_run) if args.apply else 0
    if not args.dry_run:
        REVIEW.write_text(review)

    matched = sum(1 for e in fresh if e.tracker)
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] mode={args.mode} fetched={len(msgs)} job_related={len(events)} "
          f"new={len(fresh)} matched={matched} timeline_added={added}{' (dry run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
