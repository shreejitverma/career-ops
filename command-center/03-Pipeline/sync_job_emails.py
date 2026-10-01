#!/usr/bin/env python3
"""Sync job-search email into the Interview Command Center, without missing any.

Pipeline:
  1. fetch   - read every new message from every mail account (mail_sources.py):
               Gmail-hosted and other IMAP accounts with an app password in the
               Keychain are read over IMAP by UID (exact); every other account,
               and those without a password, through Mail.app, every folder
               including nested ones, Junk and Trash. Each mailbox keeps a
               checkpoint of what was actually read, committed only after the
               messages are recorded, so nothing is skipped when a run fails,
               times out or runs out of its time budget. --from-json reads a
               fixture instead (tests; no Mail needed).
  2. filter  - keep job-related messages: anything filed in a job folder or
               label, anything from an applicant-tracking or assessment platform
               or naming a company you track, and keyword matches; bulk mail
               (CI notifications, newsletters, marketing) is dropped.
  3. classify- label each message: offer, rejection, assessment, interview,
               recruiter, received, reply (a Re:/Fwd: thread), or other; suggest
               the pipeline stage it implies.
  4. match   - link it to a tracker note by company name or recruiter email domain.
  5. record  - append new events to .sync/events.jsonl, keyed by the message's
               Message-ID, so a message seen twice (two labels, two sources,
               overlapping runs) is recorded once.
  6. review  - regenerate _Inbox-Review.md: sync health, recent events, the
               trackers whose current stage disagrees with what the email suggests,
               and every other unmatched job email from the last OTHER_DAYS days.
  7. apply   - with --apply, add one dated line per name-matched event to the tracker's
               "## Timeline" section, tagged with its event id so it is added once.
               Domain-only matches (e.g. an agency recruiter) appear only in the review note.

Frontmatter is never modified: stage and every other field stay under human
control; the review note only suggests changes.

Usage:
  sync_job_emails.py --apply --notify            # the daily run (run_daily_sync.sh)
  sync_job_emails.py --doctor                    # accounts, method, credentials, coverage
  sync_job_emails.py --backfill-days 365 --apply # extend coverage further back (resumable)
  sync_job_emails.py --dry-run                   # read and report; write nothing
  sync_job_emails.py --from-json FILE            # use a fixture instead of real mail

Gmail over IMAP needs an app password stored once per address:
  security add-generic-password -s career-ops-mail -a you@gmail.com -T /usr/bin/security -w
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import json
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import mail_sources as ms
from tracker_frontmatter import read_frontmatter, read_list

PIPELINE = Path(__file__).resolve().parent
STATE_DIR = PIPELINE / ".sync"
EVENTS = STATE_DIR / "events.jsonl"
CHECKPOINTS = STATE_DIR / "checkpoints.json"  # per-mailbox coverage (local; gitignored)
SEEN = STATE_DIR / "seen.json"                # recently read message ids (local; gitignored)
HEALTH = STATE_DIR / "health.json"            # last run's per-mailbox result (local; gitignored)
DEFAULT_BACKFILL_DAYS = 180
DEFAULT_BUDGET_MINUTES = 45
REVIEW = PIPELINE / "_Inbox-Review.md"
OTHER_DAYS = 14  # the review lists unmatched job email without a clear signal this far back
TRACKER_DIRS = ("Active", "Archive")

# Shared ATS and platform domains: they send mail for many companies, so they never identify a tracker.
SHARED_DOMAINS = (
    "greenhouse-mail.io", "greenhouse.io", "lever.co", "myworkday.com", "workday.com", "linkedin.com",
    "hackerrankforwork.com", "hackerrank.com", "criteriacorp.com", "icims.com", "ashbyhq.com",
    "smartrecruiters.com", "jobvite.com", "taleo.net",
)

# Applicant-tracking, scheduling and assessment platforms: mail from them is
# job mail even when neither subject nor body names a job keyword.
ATS_SENDER_DOMAINS = tuple(d for d in SHARED_DOMAINS if d != "linkedin.com") + (
    "myworkdayjobs.com", "myworkdaysite.com", "successfactors.com", "successfactors.eu", "oraclecloud.com",
    "avature.net", "eightfold.ai", "hirevue.com", "codesignal.com", "codility.com", "karat.com", "karat.io",
    "coderpad.io", "testgorilla.com", "modernhire.com", "pymetrics.ai", "pymetrics.com", "hackerearth.com",
    "gem.com", "paradox.ai", "workablemail.com", "workable.com", "recruitee.com", "bamboohr.com", "breezy.hr",
    "teamtailor.com", "jazzhr.com", "applytojob.com", "ultipro.com", "ukg.com", "phenompeople.com",
    "brassring.com", "kenexa.com", "goodtime.io", "hireez.com", "rippling.com", "dover.com",
    "wellfound.com", "otta.com", "welcometothejungle.com", "handshake-mail.com",
)
# LinkedIn sends everything from one domain; only these senders are about applications
# ("Your application was sent to ...", recruiter InMail).
ATS_SENDER_RE = re.compile(r"\b(jobs-noreply|jobs-listings|inmail-hit-reply|hit-reply)@linkedin\.com\b", re.I)

JOB_KEYWORDS = [
    "interview", "application", "assessment", "hackerrank", "codesignal",
    "karat", "codility", "recruiter", "hiring", "offer", "rejection",
    "status of your application", "next steps", "phone screen", "technical round",
    "onsite", "take-home", "right to represent", "congratulations",
    "thank you for your interest", "applied", "candidacy", "position", "candidate",
    "rtr", "exclusivity", "screening", "your application", "recruiting", "talent acquisition",
    "hiring manager", "hirevue", "coderpad", "background check", "offer letter", "next round",
    "final round", "superday", "your candidacy", "job opportunity",
]
EXCLUDE_PATTERNS = [
    "job alert", "jobs you may like", "recommended jobs", "daily job alert",
    "weekly digest", "newsletter", "promotions", "uber", "delivery", "order",
    "run failed", "jobright", "flipboard", "weekly wisdom", "samsung",
    "notifications@github.com", "e2ma.net", "substack.com", "biginterview.com",
]

# Bulk mail that is never about one of your applications, even when a mail rule
# files it under a job label (the Google "Job" label collects GitHub CI failures
# and newsletters): CI notifications, newsletters, marketing, career-center
# events, job-alert digests. It is checked against subject and sender only, so
# it also hides events recorded before a pattern was added.
NOISE_RE = re.compile(
    r"notifications@github\.com|\brun failed\b|newsletter|webinar|\bevents for\b|"
    r"career (center|services|development)|\bsave \d+%|\d+% off|monthly payment|"
    r"jobs you may like|job alert|jobalert|recommended jobs|hot tech jobs|\bmore\b.{0,40}\bjobs\b|"
    r"new jobs for|\bdigest\b|a scan has been completed|"
    r"event schedule|upcoming events|you'?re invited|fireside chat|career fair|register today|fire safety report|"
    r"@(e2ma\.net|substack\.com|symplicity\.com|careereco\.com|manhattanprep\.com|flipboard\.com)|"
    r"@([\w-]+\.)*(nytimes\.com|wsj\.com)\b",
    re.I,
)

# Signal -> (subject pattern, body pattern), checked in priority order (an offer
# email may also say "interview"). Subjects are short and specific, so a bare word
# counts there; in a body it must be job phrasing, because newsletters and news
# articles mention "interviews" and "assessments" all the time.
_OFFER = r"pleased to (extend|offer)|offer (letter|of employment)|extend (you )?an offer"
_REJECTION = (r"regret to inform|not (be )?moving forward|decided to (move|proceed) forward with other|"
              r"pursue other candidates|position has been filled|no longer under consideration|"
              r"will not be (progressing|proceeding)|unfortunately,? (we|after)")
_RECEIVED = (r"thank you for (applying|your application|your interest)|application (was )?(received|submitted)|"
             r"we have received")
SIGNALS: list[tuple[str, re.Pattern, re.Pattern]] = [
    ("offer", re.compile(_OFFER, re.I), re.compile(_OFFER, re.I)),
    ("rejection", re.compile(_REJECTION, re.I), re.compile(_REJECTION, re.I)),
    ("assessment",
     re.compile(r"hackerrank|codesignal|codility|\bkarat\b|assessment|take-home|coding challenge|online test", re.I),
     re.compile(r"hackerrank|codesignal|codility|\bkarat\b|coding challenge|online (assessment|test)|take-home|"
                r"complete (the|an|your) (online |technical )?assessment|assessment (link|invitation)", re.I)),
    ("interview",
     re.compile(r"interview|phone screen|onsite|on-site|superday|final round|schedule (a )?(call|time)|your availability", re.I),
     re.compile(r"schedule (an|your|a) (\w+ )?interview|interview (invitation|request|confirmation|schedule|slot)|"
                r"invite you to (an? )?(\w+ )?interview|phone screen|onsite interview|superday|final round|"
                r"next round|your availability", re.I)),
    ("recruiter",
     re.compile(r"right to represent|\brtr\b|exclusivity|recruiter|opportunity", re.I),
     re.compile(r"right to represent|\brtr\b|exclusivity|i'?m a recruiter|i am a recruiter|recruiter (at|with|for)|"
                r"reaching out (about|regarding|with) (a|an|the) (\w+ )?(role|position|opportunity)|"
                r"submit you (to|for) (our|my|the|a) client|on behalf of (our|my|a) client|"
                r"(a|an) (\w+ )?(role|position|opportunity) (with|at|for) (our|my|a) client|"
                r"(about|regarding|came across|saw|reviewed) your (cv|resume)", re.I)),
    ("received", re.compile(_RECEIVED, re.I), re.compile(_RECEIVED, re.I)),
    # A reply or forward on job mail is a conversation with a person (a recruiter
    # thread about a role), even when no other signal word appears.
    ("reply", re.compile(r"^\s*(re|fw|fwd)\s*:", re.I), re.compile(r"(?!x)x")),
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
    message_id: str | None = None  # RFC Message-ID; absent on events recorded before it was kept

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True)


# -- filter, classify, match ------------------------------------------------------

def is_noise(subject: str, sender: str) -> bool:
    return bool(NOISE_RE.search(f"{subject} {sender}"))


def sender_domain(sender: str) -> str:
    return (re.findall(r"@([\w.-]+)", sender) or [""])[-1].lower()


def is_ats_sender(sender: str) -> bool:
    d = sender_domain(sender)
    return bool(ATS_SENDER_RE.search(sender)) or (bool(d) and any(d == x or d.endswith("." + x) for x in ATS_SENDER_DOMAINS))


def is_job_related(msg: dict, trackers: list[Tracker] = ()) -> bool:
    if is_noise(msg["subject"], msg["sender"]):
        return False
    if msg.get("dedicated") or is_ats_sender(msg["sender"]):
        return True
    # A tracker's own recruiter domain is precise; a company name alone is not (Bank of
    # America or Fidelity also send statements), so name matches still need job wording.
    if trackers and match_tracker(msg, trackers)[1] == "domain":
        return True
    head = f"{msg['subject']} {msg['sender']}".lower()
    if any(ex in head for ex in EXCLUDE_PATTERNS):
        return False
    return any(k in f"{head} {msg.get('snippet', '')}".lower() for k in JOB_KEYWORDS)


def classify(msg: dict) -> str:
    subject, body = msg["subject"], msg.get("snippet", "")
    return next((name for name, subj, bod in SIGNALS if subj.search(subject) or bod.search(body)), "other")


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
    """Keyed on the message, not the mailbox: its Message-ID when it has one (the same message
    read from two labels or two sources is one event); otherwise account, subject, sender, date."""
    mid = ms.clean_mid(msg.get("message_id"))
    key = f"mid:{mid}" if mid else "|".join(msg.get(k, "") for k in ("account", "subject", "sender", "date"))
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def fingerprint(date: str, subject: str, sender: str) -> tuple[str, str, str]:
    """Day, subject and sender address. Events recorded before Message-IDs were kept have
    content-hash ids, so a re-read of one of those messages is recognised by this instead."""
    addr = (re.findall(r"[\w.+-]+@[\w.-]+", sender) or [sender])[-1].lower()
    return parse_date(date), norm(subject)[:80], addr


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
        message_id=ms.clean_mid(msg.get("message_id")) or None,
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
    mids = {e.message_id for e in known.values() if e.message_id}
    # Each legacy event (no Message-ID) stands for exactly one message: it absorbs one
    # re-read with its fingerprint and no more, so two different messages with the same
    # day, subject and sender are both kept even when only one was recorded before. The
    # absorbed Message-ID is written onto the legacy event, so this holds across runs.
    legacy: dict[tuple[str, str, str], list[str]] = {}
    for e in known.values():
        if not e.message_id:
            legacy.setdefault(fingerprint(e.date, e.subject, e.sender), []).append(e.id)
    absorbed: dict[str, str] = {}
    for e in new:
        if e.id in seen or (e.message_id and e.message_id in mids):
            continue
        fp = fingerprint(e.date, e.subject, e.sender)
        if e.message_id and legacy.get(fp):
            absorbed[legacy[fp].pop(0)] = e.message_id
            mids.add(e.message_id)
            continue
        fresh.append(e)
        seen.add(e.id)
        if e.message_id:
            mids.add(e.message_id)
    if dry_run:
        return fresh
    if absorbed:
        rewrite_events(path, absorbed, fresh)
    elif fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            for e in fresh:
                f.write(e.to_json() + "\n")
    return fresh


def rewrite_events(path: Path, absorbed: dict[str, str], fresh: list[Event]) -> None:
    """Set message_id on the absorbed legacy events and append `fresh`, atomically. Every
    other line is kept byte for byte and in order."""
    lines = path.read_text().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("id") in absorbed:
            d["message_id"] = absorbed[d["id"]]
            lines[i] = json.dumps(d, sort_keys=True) + ("\n" if line.endswith("\n") else "")
    if fresh and lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines += [e.to_json() + "\n" for e in fresh]
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text("".join(lines))
    tmp.replace(path)


def stage_rank(stage: str) -> int:
    s = stage.strip().lower()
    for i, name in enumerate(STAGES):
        if s == name.lower():
            return i
    return -1


def health_lines(health: dict | None, today: str) -> list[str]:
    """The review's "Sync health" section: any mailbox that failed or is behind,
    and accounts not read the complete way, so a gap is never silent."""
    lines = ["## Sync health", ""]
    if not health:
        return lines + ["No sync has recorded its health yet.", ""]
    boxes = health.get("mailboxes", [])
    errors = [b for b in boxes if b["status"] == "error"]
    partial = [b for b in boxes if b["status"] == "partial"]
    # Backfill still on its way back to the target: progress, never a failure.
    behind = [b for b in boxes if b["status"] == "ok" and b.get("target") and b.get("covered_from", "") > b["target"]]
    bodiless = [b for b in boxes if b.get("unavailable") or (b["status"] == "ok" and b.get("error"))]
    ran = health.get("finished_at", "")[:16].replace("T", " ")
    stale = health.get("finished_at", "")[:10] < (datetime.fromisoformat(today) - timedelta(days=2)).date().isoformat()
    lines.append(f"Last run {ran}: {len(boxes)} mailboxes in {len({b['account'] for b in boxes})} accounts, "
                 f"{sum(b['read'] for b in boxes)} messages read, {sum(b['kept'] for b in boxes)} new to check.")
    if stale:
        lines.append("**The last run is more than two days old: check the launchd job and sync.log.**")
    if not errors and not partial and not bodiless and not behind:
        lines.append("Every mailbox read completely.")
    if errors:
        lines += ["", f"**{len(errors)} mailbox(es) failed; they are read again next run:**", "",
                  "| Account | Mailbox | Error |", "| :--- | :--- | :--- |"]
        lines += [f"| {b['account']} | {b['mailbox']} | {b['error'].replace('|', '/')} |" for b in errors]
    if partial:
        lines += ["", (f"{len(partial)} mailbox(es) hit the time budget and continue next run "
                       f"(one still partial after {ms.STARVED_RUNS} runs in a row is listed as failed):"), ""]
        lines += [f"- {b['account']}/{b['mailbox']}: {b['error']}" for b in partial[:8]]
        if len(partial) > 8:
            lines.append(f"- and {len(partial) - 8} more")
    if bodiless:
        lines += ["", (f"{len(bodiless)} mailbox(es) had message bodies Mail could not return; those messages were "
                       "classified from subject and sender only, and any not recorded is read again while it is inside "
                       "the two-day re-read window:"), ""]
        lines += [f"- {b['account']}/{b['mailbox']}: {b.get('unavailable', 0)} message(s)" for b in bodiless]
    if behind:
        lines += ["", "Older mail is still being read back to the backfill target, a little more each run "
                  "(new mail is read first):", ""]
        for acc in sorted({b["account"] for b in behind}):
            mine = [b for b in behind if b["account"] == acc]
            lines.append(f"- backfill in progress: {acc} covered back to {max(b['covered_from'] for b in mine)}, "
                         f"target {min(b['target'] for b in mine)}")
    fallback = sorted({b["account"] for b in boxes if "gmail fallback" in b["method"]})
    if fallback:
        lines += ["", "Read through Mail.app, which is slow for Gmail and can miss a message that Mail downloads more "
                  f"than two days late: {', '.join(fallback)}. Store an app password to read them exactly over IMAP "
                  "(`sync_job_emails.py --doctor` prints the command)."]
    return lines + [""]


def render_review(events: dict[str, Event], trackers: list[Tracker], today: str, days: int = 30,
                  root: Path = PIPELINE, untracked_days: int = 180, health: dict | None = None) -> str:
    def window(n: int) -> list[Event]:
        since = (datetime.fromisoformat(today) - timedelta(days=n)).date().isoformat()
        return sorted((e for e in events.values()
                       if is_iso_date(e.date) and e.date >= since and not is_noise(e.subject, e.sender)),
                      key=lambda e: e.date, reverse=True)

    recent = window(days)
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
        *health_lines(health, today),
        "## Needs attention", "",
    ]
    if attention:
        lines += ["| Date | Tracker | Current stage | Email suggests | Subject |", "| :--- | :--- | :--- | :--- | :--- |"]
        lines += [f"| {e.date} | {link(e)} | {t.stage or '-'} | {e.suggested_stage} | {e.subject.replace('|', '/')} |" for e, t in attention]
    else:
        lines.append("Nothing: every matched email agrees with its tracker's stage.")
    # A missing tracker matters long after the email, so this looks further back than the activity list.
    untracked = [e for e in window(untracked_days) if not e.tracker and e.signal not in ("other", "received")]
    lines += ["", "## Possible untracked applications", ""]
    if untracked:
        lines += [f"Job emails from the last {untracked_days} days with a clear signal that match no tracker; "
                  "create a tracker if they are real applications.", "",
                  "| Date | Signal | From | Subject |", "| :--- | :--- | :--- | :--- |"]
        lines += [f"| {e.date} | {e.signal} | {e.sender.replace('|', '/')} | {e.subject.replace('|', '/')} |" for e in untracked]
    else:
        lines.append("None.")
    lines += ["", f"## Last {days} days", ""]
    # Everything matched to a tracker or carrying a clear signal; the rest has its own list below.
    shown = [e for e in recent if e.tracker or e.signal != "other"]
    if shown:
        lines += ["| Date | Tracker | Signal | Subject |", "| :--- | :--- | :--- | :--- |"]
        lines += [f"| {e.date} | {link(e)} | {e.signal} | {e.subject.replace('|', '/')} |" for e in shown]
    else:
        lines.append("No job-related email with a clear signal in this window.")
    other = [e for e in window(OTHER_DAYS) if not e.tracker and e.signal == "other"]
    lines += ["", f"## Other job email (last {OTHER_DAYS} days)", ""]
    if other:
        lines += ["Job-related emails that match no tracker and carry no clear signal; skim them so none is missed.", "",
                  "| Date | From | Subject |", "| :--- | :--- | :--- |"]
        lines += [f"| {e.date} | {e.sender.replace('|', '/')} | {e.subject.replace('|', '/')} |" for e in other]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def apply_timeline(events: list[Event], root: Path = PIPELINE, dry_run: bool = False) -> int:
    """Append one line per name-matched event under '## Timeline'; the evt marker makes it idempotent.
    Domain-only matches are left to the review note: an agency domain also sends mail about other companies."""
    added = 0
    for e in sorted(events, key=lambda e: e.date):
        if not e.tracker or e.match != "name" or e.signal == "other" or is_noise(e.subject, e.sender):
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


class RunFilter:
    """Which messages a run reads for classification, and which it already delivered.

    A message counts as delivered only once a source actually returns it (`sunk`), so a
    mailbox that fails after reading a message's header never hides that message from
    another mailbox holding it (a job label and All Mail)."""

    def __init__(self, own: set[str], known: dict[str, Event], seen: ms.SeenCache, trackers: list[Tracker] = ()):
        self.own, self.known, self.seen, self.trackers = own, known, seen, trackers
        self.known_mids = {e.message_id for e in known.values() if e.message_id}
        self.delivered: set[str] = set()

    def keep(self, m: dict) -> bool:
        """Read for classification? Not bulk mail, not a message already handled, and not
        one its subject and sender already rule out: bodies are the slow part of a read,
        and is_job_related would reject these whatever the body says."""
        if is_noise(m["subject"], m["sender"]):
            return False
        if email.utils.parseaddr(m["sender"])[1].lower() in self.own:
            return False
        if not (m.get("dedicated") or is_ats_sender(m["sender"])
                or (self.trackers and match_tracker(m, self.trackers)[1] == "domain")):
            head = f"{m['subject']} {m['sender']}".lower()
            if any(ex in head for ex in EXCLUDE_PATTERNS):
                return False
        mid = m["message_id"]
        return not (mid and (mid in self.delivered or mid in self.known_mids or self.seen.has(mid)
                             or event_id(m) in self.known))

    def sunk(self, m: dict) -> None:
        if m["message_id"]:
            self.delivered.add(m["message_id"])


def fetch_messages(args, known: dict[str, Event], cps: ms.Checkpoints, seen: ms.SeenCache,
                   trackers: list[Tracker] = ()) -> ms.FetchResult:
    """Route every account to its most complete source and read everything new."""
    runner = ms.OsaRunner()
    accounts = ms.enumerate_accounts(runner)
    if not accounts:
        raise ms.MailError("Mail.app reported no accounts; nothing was read")
    # Mail from any of your own addresses is outgoing, wherever it was filed or copied.
    flt = RunFilter({a.user.lower() for a in accounts if a.user}, known, seen, trackers)
    imap_accs = [a for a in accounts if a.imap_capable and ms.keychain_password(a.user)]
    mail_accs = [a for a in accounts if a not in imap_accs]
    backfill = args.backfill_days
    result = ms.FetchResult()
    if imap_accs:
        r = ms.ImapSource(imap_accs, backfill_days=backfill).fetch(cps, flt.keep, flt.sunk)
        result.messages += r.messages
        result.health += r.health
    if mail_accs:
        r = ms.AppleMailSource(mail_accs, backfill_days=backfill, budget_s=args.budget_minutes * 60,
                               runner=runner).fetch(cps, flt.keep, flt.sunk)
        result.messages += r.messages
        result.health += r.health
    if not result.health:
        raise ms.MailError(f"no mailboxes selected in {len(accounts)} account(s); nothing was read")
    return result


def doctor(args) -> int:
    """Accounts, how each is read, whether its app password is stored, and its coverage."""
    runner = ms.OsaRunner()
    accounts = ms.enumerate_accounts(runner)
    cps = ms.Checkpoints(CHECKPOINTS, dry_run=True)  # --doctor only reads
    health = json.loads(HEALTH.read_text()) if HEALTH.exists() else {}
    print(f"accounts[{len(accounts)}]{{account,method,mailboxes,covered_from,last_run_errors}}:")
    missing = []
    for a in accounts:
        has_pw = a.imap_capable and ms.keychain_password(a.user) is not None
        method = "imap" if has_pw else ("mail (gmail fallback)" if a.gmail else "mail")
        if a.imap_capable and not has_pw:
            missing.append(a)
        prefix = f"imap:{a.user}:" if has_pw else f"mail:{a.name}:"
        covered = sorted((v.get("since") or v.get("lo") or "")[:10] for k, v in cps.data.items() if k.startswith(prefix))
        errs = sum(1 for b in health.get("mailboxes", []) if b["account"] == a.name and b["status"] == "error")
        boxes = len(ms.AppleMailSource([a], backfill_days=0, budget_s=0, runner=runner).selected(a)) if not has_pw else "all mail+spam+trash"
        print(f"  {a.name},{method},{boxes},{covered[-1] if covered else 'not yet'},{errs}")
    if missing:
        print("\nnext: store an app password to read these exactly and fast over IMAP (Gmail: myaccount.google.com/apppasswords;")
        print("iCloud: account.apple.com > App-Specific Passwords). Each command prompts for the password:")
        for a in missing:
            print(f"  security add-generic-password -s {ms.KEYCHAIN_SERVICE} -a {a.user} -T /usr/bin/security -w")
    return 0


def notify(text: str) -> None:
    """A macOS notification, so a failing unattended run is noticed."""
    safe = text.replace("\\", "").replace('"', "'")[:200]
    subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "Job email sync"'],
                   capture_output=True, timeout=30)


def fail_run(args, known: dict[str, Event], trackers: list[Tracker], started: str, error: str) -> int:
    """A run that could not read mail at all: as loud as a failed mailbox, never quieter."""
    row = ms.Health("all accounts", "*", "sync", "error", error=error[:300]).to_dict()
    health = {"started_at": started, "finished_at": datetime.now().isoformat(timespec="seconds"), "mailboxes": [row]}
    if not args.dry_run:
        ms.atomic_write_json(HEALTH, health)
        REVIEW.write_text(render_review(known, trackers, args.today, health=health))
    print(f"ERROR {error}", file=sys.stderr)
    if args.notify:
        notify("Job email sync could not run; see _Inbox-Review.md")
    return 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-json", type=Path, help="read messages from a JSON list instead of real mail")
    ap.add_argument("--apply", action="store_true", help="append timeline lines to matched trackers")
    ap.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")
    ap.add_argument("--doctor", action="store_true", help="show accounts, read method, credentials and coverage")
    ap.add_argument("--backfill-days", type=int, default=DEFAULT_BACKFILL_DAYS,
                    help=f"cover mail this far back (default {DEFAULT_BACKFILL_DAYS}); extending it later resumes")
    ap.add_argument("--budget-minutes", type=float, default=DEFAULT_BUDGET_MINUTES,
                    help="time allowed for Mail.app reads; unfinished mailboxes continue next run")
    ap.add_argument("--notify", action="store_true", help="macOS notification when a mailbox fails")
    ap.add_argument("--today", default=datetime.now().date().isoformat(), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.doctor:
        return doctor(args)

    trackers = load_trackers()
    known = load_events(EVENTS)
    started = datetime.now().isoformat(timespec="seconds")
    if args.from_json:
        msgs, health_rows, cps, seen = json.loads(args.from_json.read_text()), [], None, None
    else:
        try:
            cps, seen = ms.Checkpoints(CHECKPOINTS, dry_run=args.dry_run), ms.SeenCache(SEEN, dry_run=args.dry_run)
            result = fetch_messages(args, known, cps, seen, trackers)
        except Exception as e:  # noqa: BLE001 - reported in health, the review, the exit code and a notification
            traceback.print_exc()
            return fail_run(args, known, trackers, started, f"sync could not run: {type(e).__name__}: {e}")
        msgs, health_rows = result.messages, [h.to_dict() for h in result.health]
        health_rows += [ms.Health("all accounts", state.path.name, "state", "error", error=state.problem).to_dict()
                        for state in (cps, seen) if state.problem]
    related = [m for m in msgs if is_job_related(m, trackers)]
    events = [to_event(m, trackers) for m in related]
    fresh = record(events, EVENTS, dry_run=args.dry_run)
    health = {"started_at": started, "finished_at": datetime.now().isoformat(timespec="seconds"),
              "mailboxes": health_rows} if cps is not None else (json.loads(HEALTH.read_text()) if HEALTH.exists() else None)
    if not args.dry_run and cps is not None:
        # Only now, with every message recorded, may coverage move forward.
        cps.commit()
        recorded = {id(m) for m in related}
        for m in msgs:
            if not m.get("body_unavailable") or id(m) in recorded:
                seen.add(m.get("message_id", ""), m["date"])
        seen.save(args.today)
        ms.atomic_write_json(HEALTH, health)
    all_events = load_events(EVENTS)
    if args.dry_run:
        all_events.update({e.id: e for e in fresh})
    review = render_review(all_events, trackers, args.today, health=health)
    added = apply_timeline(list(all_events.values()), dry_run=args.dry_run) if args.apply else 0
    if not args.dry_run:
        REVIEW.write_text(review)

    errors = [h for h in health_rows if h["status"] == "error"]
    partial = [h for h in health_rows if h["status"] == "partial"]
    matched = sum(1 for e in fresh if e.tracker)
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] mailboxes={len(health_rows)} read={sum(h['read'] for h in health_rows)} "
          f"checked={len(msgs)} job_related={len(events)} new={len(fresh)} matched={matched} timeline_added={added} "
          f"errors={len(errors)} partial={len(partial)}{' (dry run)' if args.dry_run else ''}")
    for h in errors:
        print(f"ERROR {h['account']}/{h['mailbox']}: {h['error']}", file=sys.stderr)
    if errors and args.notify:
        notify(f"{len(errors)} mailbox(es) failed; see _Inbox-Review.md")
    return 2 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
