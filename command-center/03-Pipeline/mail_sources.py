#!/usr/bin/env python3
"""Complete, checkpointed fetch of job-search email for sync_job_emails.py.

Nothing may be missed, so every source keeps three rules:

1. Coverage is tracked per mailbox as what has actually been read, never as
   "the newest N messages". A mailbox's checkpoint is only staged after its
   messages were read, and the caller commits it only after they were recorded,
   so a crash, a timeout or an exhausted time budget means "read again next run",
   never "skipped".
2. Every folder is read: every enabled account, every mailbox including nested
   and duplicate-named ones (addressed by position, not name), Junk/Spam and
   Trash. Only outgoing or system folders (Sent, Drafts, Outbox, Notes, Tasks,
   Journal, ...) are skipped, plus Gmail's aggregate views where a complete
   source replaces them.
3. Failures are loud: each mailbox reports ok / partial / error in a Health
   record that the inbox review, the exit code and --doctor surface. A mailbox
   is partial when its new mail was not all read, when a stretch of recent mail
   is still unread, or when its backfill was given time and made no progress;
   left partial for STARVED_RUNS runs in a row it becomes an error. A backfill
   that moved further back is progress, not a failure, and stays ok.

Sources
-------
ImapSource
    Gmail-hosted and other IMAP accounts whose app password is in the macOS
    Keychain (service "career-ops-mail", account = the address). Server-side
    UID search makes it exact: a message that arrives late still gets a higher
    UID than the checkpoint. For Gmail it reads All Mail, Spam and Trash, which
    together hold every message in every label, and reads each message's labels
    (X-GM-LABELS) so a message filed under a job label counts as job mail.
AppleMailSource
    Every other account, through Mail.app's AppleScript API. Mail keeps every
    mailbox ordered newest-first, so a run reads from the top down to the last
    covered time minus an overlap (new mail), then reads any stretch an earlier
    run left unread, then extends coverage backwards toward the backfill target,
    all in budgeted steps that resume where they stopped. Fast accounts are read
    before the slow Gmail-fallback ones, and a share of the budget is kept for
    unread stretches and backfill, so slow new mail cannot starve them.
"""

from __future__ import annotations

import email
import email.policy
import email.utils
import hashlib
import imaplib
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Callable, ClassVar, Iterable

KEYCHAIN_SERVICE = "career-ops-mail"
# Re-read this much before the last covered time: Mail.app can download a
# message after the run that would have seen it, with an older received date.
OVERLAP = timedelta(days=2)
SNIPPET_CHARS = 1500
# Share of the remaining time budget a header read may use; bodies get the rest.
READ_SHARE = 0.6
# Share of the Mail.app budget kept for unread stretches and backfill: new-mail
# passes may not spend it, so a slow account's new mail cannot take every run.
RESERVE_SHARE = 0.3
# Consecutive Mail.app chunk reads overlap by this many positions, so a message
# deleted or moved above the cursor between two chunks cannot shift one past it.
CHUNK_OVERLAP = 5
# A mailbox still partial after this many runs in a row is reported as an error.
STARVED_RUNS = 3
# Checkpoint key holding scheduling state (which slow account goes first next run).
SCHEDULE_KEY = "_schedule"
BODY_BYTES = 65536

# Outgoing and system folders; never incoming mail about an application.
SKIP_MAILBOX_RE = re.compile(
    r"^(sent|sent items|sent messages|sent mail|drafts|outbox|notes|journal|tasks|conversation history|"
    r"sync issues|conflicts|local failures|server failures|recordings)$", re.I)
# What a Gmail account without an app password is read through in Mail.app:
# All Mail (every message in every label, including archived mail that left
# INBOX), Spam and Trash, plus the user's job labels read first so their
# messages carry the "dedicated" mark. Other labels and INBOX are subsets of
# All Mail and would only be read twice.
GMAIL_FALLBACK_RE = re.compile(r"^(all mail|spam|bin|trash)$", re.I)
# A folder or Gmail label on any of these words holds job mail by the user's own filing.
DEDICATED_HINTS = ("interview", "rejection", "job", "bank of america", "career", "recruit", "application")

US, RS = "\x1f", "\x1e"


# ── Small helpers ────────────────────────────────────────────────────────────

def clean_mid(mid: str | None) -> str:
    """RFC Message-ID without angle brackets or whitespace, lowercased; '' when absent."""
    if not mid or str(mid).strip().lower() == "missing value":
        return ""
    return str(mid).strip().strip("<>").strip().lower()


def is_dedicated(path: str) -> bool:
    """A mailbox path or label (any component) the user files job mail under."""
    return any(h in part.lower() for part in re.split(r"[/\\]", path) for h in DEDICATED_HINTS)


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    return unescape(re.sub(r"(?s)<[^>]+>", " ", html))


def text_snippet(raw: bytes) -> str:
    """First SNIPPET_CHARS of a message's readable text (plain part, else stripped HTML)."""
    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        part = msg.get_body(preferencelist=("plain", "html"))
        text = part.get_content() if part is not None else ""
        if part is not None and part.get_content_type() == "text/html":
            text = html_to_text(text)
    except Exception:  # a truncated or malformed body still yields something below
        text = raw.decode("utf-8", errors="replace")
    return " ".join(text.split())[:SNIPPET_CHARS]


def keychain_password(address: str) -> str | None:
    """App password stored with `security add-generic-password -s career-ops-mail -a <address> -w`."""
    try:
        p = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", address, "-w"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.rstrip("\n") if p.returncode == 0 and p.stdout.strip() else None


def atomic_write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")
    tmp.replace(path)


def load_state(path: Path, *, move_aside: bool = True) -> tuple[dict, str]:
    """A state file's contents and a problem report. A file that is not a JSON object is
    moved aside to <name>.corrupt-<timestamp> (never overwriting an earlier copy) and
    reported; the empty state that replaces it costs a re-read, never a miss. With
    move_aside=False (dry runs, --doctor) the file is only reported and left in place."""
    if not path.exists():
        return {}, ""
    try:
        data = json.loads(path.read_text())
    except ValueError:
        data = None
    if isinstance(data, dict):
        return data, ""
    if not move_aside:
        return {}, f"{path.name} is unreadable; left in place (dry run or --doctor), a real run moves it aside and re-reads mail"
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    aside = path.with_name(f"{path.name}.corrupt-{stamp}")
    n = 1
    while aside.exists():
        n += 1
        aside = path.with_name(f"{path.name}.corrupt-{stamp}-{n}")
    path.replace(aside)
    return {}, f"{path.name} was unreadable; moved to {aside.name} and rebuilt by re-reading mail"


# ── Persistent state ─────────────────────────────────────────────────────────

class Checkpoints:
    """Per-mailbox coverage. Sources stage updates; the caller commits them only
    after the messages they cover were recorded."""

    def __init__(self, path: Path, *, dry_run: bool = False):
        self.path = path
        self.data, self.problem = load_state(path, move_aside=not dry_run)
        self.staged: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self.staged.get(key) or self.data.get(key)

    def stage(self, key: str, value: dict) -> None:
        self.staged[key] = value

    def commit(self) -> None:
        if self.staged:
            self.data.update(self.staged)
            self.staged = {}
            atomic_write_json(self.path, self.data)


class SeenCache:
    """Message ids read in the last `days`, so overlap re-reads skip the slow body fetch."""

    def __init__(self, path: Path, days: int = 30, *, dry_run: bool = False):
        self.path, self.days = path, days
        self.data, self.problem = load_state(path, move_aside=not dry_run)

    @staticmethod
    def key(mid: str) -> str:
        return hashlib.sha1(mid.encode()).hexdigest()[:16]

    def has(self, mid: str) -> bool:
        return bool(mid) and self.key(mid) in self.data

    def add(self, mid: str, date: str) -> None:
        if mid:
            self.data[self.key(mid)] = date

    def save(self, today: str) -> None:
        cutoff = (datetime.fromisoformat(today) - timedelta(days=self.days)).date().isoformat()
        self.data = {k: d for k, d in self.data.items() if d >= cutoff}
        atomic_write_json(self.path, self.data)


@dataclass
class Health:
    account: str
    mailbox: str
    method: str
    status: str = "ok"  # ok | partial | error
    read: int = 0
    kept: int = 0
    error: str = ""
    unavailable: int = 0  # messages classified without their body (Mail could not return it)
    covered_from: str = ""
    covered_to: str = ""
    target: str = ""  # backfill target date; covered_from later than it means backfill is in progress

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FetchResult:
    messages: list[dict] = field(default_factory=list)
    health: list[Health] = field(default_factory=list)


def message(account, mailbox, subject, sender, received: datetime, mid, *, dedicated, source, snippet="") -> dict:
    local = received.astimezone() if received.tzinfo else received
    return {
        "account": account, "mailbox": mailbox, "subject": subject or "", "sender": sender or "",
        "date": local.date().isoformat(), "received": local.replace(tzinfo=None).isoformat(timespec="seconds"),
        "message_id": clean_mid(mid), "snippet": snippet, "dedicated": dedicated, "source": source,
    }


# ── Accounts ────────────────────────────────────────────────────────────────

@dataclass
class Account:
    name: str          # Mail.app account name; the event's `account`
    kind: str          # Mail.app class: "imap account", "iCloud account", "account" (Exchange/EWS), ...
    user: str          # login address
    server: str        # IMAP host, '' for Exchange
    mailboxes: list[tuple[int, str]] = field(default_factory=list)  # (Mail.app index, full path)

    @property
    def gmail(self) -> bool:
        return self.server.lower().endswith("gmail.com") or self.server.lower().endswith("googlemail.com")

    @property
    def imap_capable(self) -> bool:
        return self.kind.lower() in ("imap account", "icloud account") and bool(self.server) and bool(self.user)


# ── IMAP ────────────────────────────────────────────────────────────────────

LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<delim>"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$')


def _unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return re.sub(r'\\(.)', r'\1', s[1:-1])
    return s


def imap_utf7_decode(s: str) -> str:
    """Modified UTF-7 mailbox names (RFC 3501 5.1.3) to text, for display only."""
    def dec(m):
        b64 = m.group(1).replace(",", "/")
        if not b64:
            return "&"
        import base64
        return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-be", errors="replace")
    return re.sub(r"&([A-Za-z0-9+,]*)-", dec, s)


def parse_list(data: Iterable) -> list[tuple[set[str], str]]:
    """IMAP LIST response -> [(flags, raw name)]."""
    out, pending = [], None
    for item in data:
        if isinstance(item, tuple):  # name sent as a literal
            pending = item[0].decode(errors="replace")
            m = re.match(r'^\((?P<flags>[^)]*)\)', pending)
            out.append(({f.lower() for f in (m.group("flags").split() if m else [])}, item[1].decode(errors="replace")))
            continue
        if item is None:
            continue
        line = item.decode(errors="replace") if isinstance(item, bytes) else str(item)
        m = LIST_RE.match(line)
        if m:
            out.append(({f.lower() for f in m.group("flags").split()}, _unquote(m.group("name"))))
    return out


def parse_fetch(data: Iterable) -> list[dict]:
    """IMAP FETCH response -> [{uid, internaldate, labels, literal}] (one literal per message)."""
    recs: list[dict] = []
    for item in data:
        if isinstance(item, tuple):
            recs.append({"meta": item[0].decode(errors="replace"), "literal": item[1]})
        elif isinstance(item, bytes):
            text = item.decode(errors="replace")
            if re.match(r"^\d+ \(", text):
                recs.append({"meta": text, "literal": b""})
            elif recs:
                recs[-1]["meta"] += text
    out = []
    for r in recs:
        meta = r["meta"]
        uid = re.search(r"\bUID (\d+)", meta)
        if not uid:
            continue
        date = re.search(r'INTERNALDATE "([^"]+)"', meta)
        labels = re.search(r'X-GM-LABELS \(((?:[^()"]|"(?:[^"\\]|\\.)*")*)\)', meta)
        out.append({
            "uid": int(uid.group(1)),
            "internaldate": datetime.strptime(date.group(1), "%d-%b-%Y %H:%M:%S %z") if date else None,
            "labels": [imap_utf7_decode(_unquote(t)) for t in re.findall(r'"(?:[^"\\]|\\.)*"|[^\s"]+', labels.group(1))] if labels else [],
            "literal": r["literal"],
        })
    return out


def imap_date(d) -> str:
    return d.strftime("%d-%b-%Y")


class ImapSource:
    method = "imap"

    def __init__(self, accounts: list[Account], *, backfill_days: int, password_for=keychain_password,
                 connect: Callable[[str], imaplib.IMAP4] | None = None, now: datetime | None = None):
        self.accounts = accounts
        self.backfill_days = backfill_days
        self.password_for = password_for
        self.connect = connect or (lambda host: imaplib.IMAP4_SSL(host, 993, timeout=120))
        self.now = now or datetime.now().astimezone()

    def mailboxes(self, conn, acc: Account) -> list[tuple[str, str]]:
        """[(raw name to SELECT, display name)] to read for this account."""
        typ, data = conn.list()
        if typ != "OK":
            raise RuntimeError(f"LIST failed: {data}")
        out, has_all = [], False
        for flags, raw in parse_list(data):
            display = imap_utf7_decode(raw)
            if "\\noselect" in flags or "\\nonexistent" in flags:
                continue
            if acc.gmail:
                # All Mail holds every message in every label except Spam and Trash.
                if flags & {"\\all", "\\junk", "\\trash"}:
                    out.append((raw, display))
                    has_all = has_all or "\\all" in flags
            elif not (flags & {"\\sent", "\\drafts", "\\all"}) and not SKIP_MAILBOX_RE.match(display.split("/")[-1]):
                out.append((raw, display))
        if acc.gmail and not has_all:
            raise RuntimeError("Gmail All Mail is not visible over IMAP; enable 'Show in IMAP' for All Mail in Gmail settings")
        return out

    def fetch(self, cps: Checkpoints, keep: Callable[[dict], bool],
              sunk: Callable[[dict], None] = lambda m: None) -> FetchResult:
        """`keep` decides whether a message is read for classification; `sunk` is told about
        every message actually delivered in the result, and only those."""
        res = FetchResult()
        for acc in self.accounts:
            password = self.password_for(acc.user)
            if not password:
                res.health.append(Health(acc.name, "*", self.method, "error", error=f"no Keychain password for {acc.user}"))
                continue
            try:
                conn = self.connect(acc.server)
                conn.login(acc.user, password)
            except Exception as e:  # noqa: BLE001 - every failure is reported, none is fatal to other accounts
                res.health.append(Health(acc.name, "*", self.method, "error", error=f"login failed: {e}"))
                continue
            try:
                for raw, display in self.mailboxes(conn, acc):
                    h = Health(acc.name, display, self.method)
                    try:
                        got = self.scan(conn, acc, raw, display, cps, keep, h)
                        res.messages += got
                        for m in got:
                            sunk(m)
                    except Exception as e:  # noqa: BLE001
                        h.status, h.error = "error", str(e)[:300]
                    res.health.append(h)
            except Exception as e:  # noqa: BLE001
                res.health.append(Health(acc.name, "*", self.method, "error", error=str(e)[:300]))
            finally:
                try:
                    conn.logout()
                except Exception:  # noqa: BLE001
                    pass
        return res

    def scan(self, conn, acc: Account, raw: str, display: str, cps: Checkpoints, keep, h: Health) -> list[dict]:
        typ, data = conn.select('"' + raw.replace("\\", "\\\\").replace('"', '\\"') + '"', readonly=True)
        if typ != "OK":
            raise RuntimeError(f"SELECT {display} failed: {data}")
        uidvalidity = int(conn.response("UIDVALIDITY")[1][0])
        uidnext_resp = conn.response("UIDNEXT")[1]
        uidnext = int(uidnext_resp[0]) if uidnext_resp and uidnext_resp[0] else None
        key = f"imap:{acc.user}:{display}"
        cp = cps.get(key)
        target = (self.now - timedelta(days=self.backfill_days)).date()

        def search(*criteria) -> list[int]:
            typ, data = conn.uid("SEARCH", None, *criteria)
            if typ != "OK":
                raise RuntimeError(f"SEARCH failed: {data}")
            return [int(u) for u in b" ".join(d for d in data if d).split()]

        if cp and cp.get("uidvalidity") == uidvalidity:
            last, since = cp["last_uid"], datetime.fromisoformat(cp["since"]).date()
            uids = [u for u in search("UID", f"{last + 1}:*") if u > last]
            if target < since:  # a longer backfill was asked for since the last run
                uids += search("SINCE", imap_date(target), "BEFORE", imap_date(since))
                since = target
        else:  # first run, or the server renumbered the mailbox: rescan the whole window
            last, since = 0, target
            uids = search("SINCE", imap_date(target))
        uids = sorted(set(uids))
        h.read = len(uids)

        kept, out = [], []
        for i in range(0, len(uids), 300):
            batch = ",".join(map(str, uids[i:i + 300]))
            items = "(UID INTERNALDATE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID)]" + (" X-GM-LABELS)" if acc.gmail else ")")
            typ, data = conn.uid("FETCH", batch, items)
            if typ != "OK":
                raise RuntimeError(f"FETCH headers failed: {data}")
            for rec in parse_fetch(data):
                labels = rec["labels"]
                if "\\Sent" in labels or "\\Draft" in labels:
                    continue
                hdr = email.message_from_bytes(rec["literal"], policy=email.policy.default)
                sender = str(hdr.get("From", "") or "")
                if email.utils.parseaddr(sender)[1].lower() == acc.user.lower() and "\\Inbox" not in labels:
                    continue  # our own outgoing mail filed outside Sent
                job_labels = [lb for lb in labels if not lb.startswith("\\") and is_dedicated(lb)]
                mailbox = job_labels[0] if job_labels else ("INBOX" if "\\Inbox" in labels else
                          next((lb for lb in labels if not lb.startswith("\\")), display))
                m = message(acc.name, mailbox, str(hdr.get("Subject", "") or ""), sender,
                            rec["internaldate"] or self.now, hdr.get("Message-ID", ""),
                            dedicated=bool(job_labels) or is_dedicated(display), source=self.method)
                m["_uid"] = rec["uid"]
                if keep(m):
                    kept.append(m)
        for i in range(0, len(kept), 50):
            chunk = kept[i:i + 50]
            typ, data = conn.uid("FETCH", ",".join(str(m["_uid"]) for m in chunk), f"(UID BODY.PEEK[]<0.{BODY_BYTES}>)")
            if typ != "OK":
                raise RuntimeError(f"FETCH bodies failed: {data}")
            bodies = {r["uid"]: r["literal"] for r in parse_fetch(data)}
            for m in chunk:
                m["snippet"] = text_snippet(bodies.get(m.pop("_uid"), b""))
                out.append(m)
        h.kept = len(out)
        new_last = max(uids + [last] + ([uidnext - 1] if uidnext else []))
        cps.stage(key, {"uidvalidity": uidvalidity, "last_uid": new_last, "since": since.isoformat(),
                        "at": self.now.replace(tzinfo=None).isoformat(timespec="seconds")})
        h.covered_from, h.covered_to = since.isoformat(), self.now.date().isoformat()
        return out


# ── Apple Mail ──────────────────────────────────────────────────────────────

APPLESCRIPT = {
    # Every enabled account and every mailbox, flat and addressed by position:
    # Mail lists nested mailboxes in `every mailbox of account`, and `container`
    # gives the real parent, so the full path is rebuilt from it.
    "enumerate": r'''
on run argv
  set US to ASCII character 31
  set RS to ASCII character 30
  set out to ""
  with timeout of 900 seconds
    tell application "Mail"
      repeat with acc in (every account whose enabled is true)
        set sv to ""
        set un to ""
        try
          set sv to (server name of acc) as string
        end try
        try
          set un to (user name of acc) as string
        end try
        set out to out & "A" & US & (name of acc) & US & ((class of acc) as string) & US & un & US & sv & RS
        set mbs to every mailbox of acc
        repeat with i from 1 to count of mbs
          set mb to item i of mbs
          set p to name of mb
          set c to container of mb
          repeat while ((class of c) as string) is "container"
            set p to (name of c) & "/" & p
            set c to container of c
          end repeat
          set out to out & "M" & US & i & US & p & RS
        end repeat
      end repeat
    end tell
  end timeout
  return out
end run''',
    # New mail in many mailboxes in one call. argv: account, specs (records of
    # index US name US stop-age-seconds, joined by RS), time limit in seconds,
    # chunk cap, chunk overlap. Per mailbox: B(index, count, again whenever the
    # count changes), R rows newest-first until a chunk ends older than the stop
    # age or the mailbox ends, then D (done); E on a per-mailbox error; T (index,
    # position) when the time limit is reached, after which nothing else runs.
    # Consecutive chunks overlap, so R rows can repeat.
    "scan": r"""
on run argv
  set US to ASCII character 31
  set RS to ASCII character 30
  set limitSecs to (item 3 of argv) as integer
  set maxChunk to (item 4 of argv) as integer
  set ovl to (item 5 of argv) as integer
  set t0 to current date
  set AppleScript's text item delimiters to RS
  set specs to text items of (item 2 of argv)
  set AppleScript's text item delimiters to ""
  set out to ""
  with timeout of 7200 seconds
    tell application "Mail"
      set acc to account (item 1 of argv)
      repeat with spec in specs
        set AppleScript's text item delimiters to US
        set f to text items of spec
        set AppleScript's text item delimiters to ""
        set ix to (item 1 of f) as integer
        try
          set mb to mailbox ix of acc
          if (name of mb) is not (item 2 of f) then error "mailbox moved: expected " & (item 2 of f) & ", found " & (name of mb)
          set stopAge to (item 3 of f) as integer
          set n to count of messages of mb
          set out to out & "B" & US & ix & US & n & RS
          set pos to 1
          set sz to 25
          if sz > maxChunk then set sz to maxChunk
          set perMsg to 0
          repeat
            set n2 to count of messages of mb
            if n2 is not n then
              set n to n2
              set out to out & "B" & US & ix & US & n & RS
            end if
            if pos > n then exit repeat
            -- Stop before a chunk that would overrun the limit, not after it.
            if ((current date) - t0) + (perMsg * sz) > limitSecs then
              return out & "T" & US & ix & US & pos & RS
            end if
            set c0 to current date
            set e to pos + sz - 1
            if e > n then set e to n
            set {ds, ss, fs, ids} to {date received, subject, sender, message id} of messages pos thru e of mb
            set nowD to current date
            set perMsg to (nowD - c0) / (count of ds)
            repeat with k from 1 to count of ds
              set s to item k of ss
              if s is missing value then set s to ""
              set fr to item k of fs
              if fr is missing value then set fr to ""
              set m to item k of ids
              if m is missing value then set m to ""
              set out to out & "R" & US & ix & US & (pos + k - 1) & US & ((item k of ds) as «class isot» as string) & US & s & US & fr & US & m & RS
            end repeat
            if (nowD - (item (count of ds) of ds)) > stopAge then exit repeat
            if e ≥ n then
              set pos to e + 1
            else
              set np to e + 1 - ovl
              if np ≤ pos then set np to pos + 1
              set pos to np
            end if
            set sz to sz * 2
            if sz > maxChunk then set sz to maxChunk
          end repeat
          set out to out & "D" & US & ix & RS
        on error errMsg
          set out to out & "E" & US & ix & US & errMsg & RS
        end try
      end repeat
    end tell
  end timeout
  return out
end run""",
    # Read one mailbox backwards. argv: account, index, name, from-age, to-age
    # (seconds before now), time limit, chunk size, chunk overlap. Binary-searches
    # the first position older than from-age (dates fall with position), then
    # reads down in overlapping chunks until a chunk ends older than to-age (D),
    # the end of the mailbox (D), or the limit (T).
    "scanfrom": r"""
on run argv
  set US to ASCII character 31
  set RS to ASCII character 30
  set limitSecs to (item 6 of argv) as integer
  set maxChunk to (item 7 of argv) as integer
  set ovl to (item 8 of argv) as integer
  set perMsg to 0
  set fromAge to (item 4 of argv) as integer
  set toAge to (item 5 of argv) as integer
  set t0 to current date
  set out to ""
  set ix to (item 2 of argv) as integer
  with timeout of 7200 seconds
    tell application "Mail"
      set mb to mailbox ix of account (item 1 of argv)
      if (name of mb) is not (item 3 of argv) then error "mailbox moved: expected " & (item 3 of argv) & ", found " & (name of mb)
      set n to count of messages of mb
      set out to out & "B" & US & ix & US & n & RS
      set lo to 1
      set hi to n + 1
      repeat while lo < hi
        set md to (lo + hi) div 2
        if ((current date) - (date received of message md of mb)) > fromAge then
          set hi to md
        else
          set lo to md + 1
        end if
      end repeat
      set pos to lo - 1
      if pos < 1 then set pos to 1
      repeat
        set n2 to count of messages of mb
        if n2 is not n then
          set n to n2
          set out to out & "B" & US & ix & US & n & RS
        end if
        if pos > n then exit repeat
        if ((current date) - t0) + (perMsg * maxChunk) > limitSecs then return out & "T" & US & ix & US & pos & RS
        set c0 to current date
        set e to pos + maxChunk - 1
        if e > n then set e to n
        set {ds, ss, fs, ids} to {date received, subject, sender, message id} of messages pos thru e of mb
        set nowD to current date
        set perMsg to (nowD - c0) / (count of ds)
        repeat with k from 1 to count of ds
          set s to item k of ss
          if s is missing value then set s to ""
          set fr to item k of fs
          if fr is missing value then set fr to ""
          set m to item k of ids
          if m is missing value then set m to ""
          set out to out & "R" & US & ix & US & (pos + k - 1) & US & ((item k of ds) as «class isot» as string) & US & s & US & fr & US & m & RS
        end repeat
        if (nowD - (item (count of ds) of ds)) > toAge then return out & "D" & US & ix & RS
        if e ≥ n then
          set pos to e + 1
        else
          set np to e + 1 - ovl
          if np ≤ pos then set np to pos + 1
          set pos to np
        end if
      end repeat
    end tell
  end timeout
  return out & "D" & US & ix & RS
end run""",
    # Body text of the given messages. argv: account, index, name, records of
    # position US message-id joined by RS, max chars, time limit in seconds.
    # Positions shift when new mail arrives, so a Message-ID mismatch searches the
    # neighbourhood. Each body has its own 30 s limit: one message Mail must
    # download slowly is returned as !unavailable instead of failing the mailbox.
    # T when the next message could overrun the time limit, after which nothing
    # else runs; the messages not returned are left for the next run.
    "content": r"""
on run argv
  set US to ASCII character 31
  set RS to ASCII character 30
  set limit to (item 5 of argv) as integer
  set limitSecs to (item 6 of argv) as integer
  set t0 to current date
  set perMsg to 0
  set AppleScript's text item delimiters to RS
  set pairs to text items of (item 4 of argv)
  set AppleScript's text item delimiters to ""
  set out to ""
  with timeout of 3600 seconds
    tell application "Mail"
      set mb to mailbox ((item 2 of argv) as integer) of account (item 1 of argv)
      if (name of mb) is not (item 3 of argv) then error "mailbox moved: expected " & (item 3 of argv) & ", found " & (name of mb)
      set n to count of messages of mb
      repeat with pr in pairs
        -- Stop before a message that would overrun the limit, as slow as the slowest yet.
        if ((current date) - t0) + perMsg > limitSecs then return out & "T" & RS
        set c0 to current date
        set AppleScript's text item delimiters to US
        set ix to (text item 1 of pr) as integer
        set want to text item 2 of pr
        set AppleScript's text item delimiters to ""
        set found to missing value
        repeat with delta in {0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 8, 12, 20, 30}
          set j to ix + delta
          if j ≥ 1 and j ≤ n then
            set mid to message id of message j of mb
            if mid is not missing value and mid is want then
              set found to message j of mb
              exit repeat
            end if
          end if
        end repeat
        if found is missing value then
          set out to out & want & US & "!notfound" & RS
        else
          -- The raw RFC 822 source, decoded in Python: `content` makes Mail render HTML
          -- mail through WebKit, which crashed Mail (SIGSEGV in NSHTMLReader) live.
          set t to "!unavailable"
          try
            with timeout of 30 seconds
              set t to source of found
            end timeout
          end try
          if t is missing value then set t to ""
          if (length of t) > limit then set t to text 1 thru limit of t
          -- Our field and record separators must not appear inside the payload.
          set AppleScript's text item delimiters to {US, RS}
          set parts to text items of t
          set AppleScript's text item delimiters to " "
          set t to parts as text
          set AppleScript's text item delimiters to ""
          set out to out & want & US & t & RS
        end if
        if ((current date) - c0) > perMsg then set perMsg to ((current date) - c0)
      end repeat
    end tell
  end timeout
  return out
end run""",
    "check": r'''
on run argv
  tell application "Mail" to check for new mail
  return "ok"
end run''',
}


class MailError(RuntimeError):
    pass


class OsaRunner:
    """Runs the scripts above with osascript; arguments go through argv, never
    into the script text."""

    # "Application isn't running" and "Connection is invalid": Mail quit or crashed mid-run.
    MAIL_GONE_RE = re.compile(r"\((-600|-609)\)")
    # argv position of the script's own time limit, which a retry must shorten too.
    LIMIT_ARG: ClassVar[dict[str, int]] = {"scan": 2, "scanfrom": 5, "content": 5}
    RELAUNCH_WAIT = 120

    def __init__(self, run=subprocess.run, sleep=time.sleep, clock=time.monotonic):
        self.run, self.sleep, self.clock = run, sleep, clock

    def _once(self, op: str, args: list[str], timeout: float):
        try:
            return self.run(["osascript", "-", *map(str, args)], input=APPLESCRIPT[op], capture_output=True,
                            text=True, timeout=max(30, timeout))
        except subprocess.TimeoutExpired as e:
            raise MailError(f"{op}: timed out after {int(timeout)}s") from e

    def _answers(self, cmd: list[str], timeout: float) -> bool:
        try:
            return self.run(cmd, capture_output=True, text=True, timeout=max(1, timeout)).returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def relaunch_mail(self) -> bool:
        """Start Mail again in the background and wait (up to 2 minutes) until it answers."""
        deadline = self.clock() + self.RELAUNCH_WAIT
        self._answers(["open", "-g", "-a", "Mail"], 60)
        while self.clock() < deadline:
            self.sleep(5)
            if self._answers(["osascript", "-e", 'tell application "Mail" to count of accounts'],
                             min(60, deadline - self.clock())):
                return True
        return False

    def __call__(self, op: str, args: list[str], timeout: float) -> str:
        start = self.clock()
        p = self._once(op, args, timeout)
        if p.returncode != 0 and self.MAIL_GONE_RE.search(p.stderr) and op != "check":
            # One crash must not fail every mailbox after it: relaunch and retry once,
            # within what is left of the time this call was given.
            if self.relaunch_mail():
                spent = self.clock() - start
                args = list(args)
                if op in self.LIMIT_ARG:
                    i = self.LIMIT_ARG[op]
                    args[i] = max(0, int(int(args[i]) - spent))
                if timeout - spent <= 0 or (op in self.LIMIT_ARG and args[self.LIMIT_ARG[op]] == 0):
                    raise MailError(f"{op}: Mail relaunched after a crash, but no time is left to retry")
                p = self._once(op, args, timeout - spent)
        if p.returncode != 0:
            raise MailError(f"{op}: {p.stderr.strip()[:300]}")
        return p.stdout.rstrip("\n")


def enumerate_accounts(runner, timeout: float = 900) -> list[Account]:
    accounts: list[Account] = []
    for rec in runner("enumerate", [], timeout).split(RS):
        f = rec.split(US)
        if f[0] == "A" and len(f) >= 5:
            clean = lambda v: "" if v.strip() == "missing value" else v.strip()  # noqa: E731
            accounts.append(Account(f[1], f[2], clean(f[3]), clean(f[4])))
        elif f[0] == "M" and len(f) >= 3 and accounts:
            accounts[-1].mailboxes.append((int(f[1]), f[2]))
    return accounts


class AppleMailSource:
    """Newest-first, checkpointed reads through Mail.app.

    Checkpoint per mailbox: {"hi": time up to which mail is read, "lo": time back
    to which it is read, "gaps": [[from, to], ...] stretches inside lo..hi still
    unread, "target": backfill target, "partial_runs": runs in a row left partial}.
    New mail in a mailbox is read by one `scan` call per account, from the top
    down to hi - OVERLAP. A pass that completes moves hi to the run's start; a
    pass the time budget cuts moves hi too, and the unread stretch between
    hi - OVERLAP and the oldest message it handled becomes a gap. Catching up
    reads gaps (`scanfrom` from a gap's top + OVERLAP down to its bottom) before
    extending lo back toward target, keeping progress after every read.

    Scheduling, so that every mailbox converges: the fast accounts (everything but
    Gmail through Mail.app, which takes seconds per message) read their new mail,
    then catch up, before the slow accounts read theirs. New-mail passes never
    spend the last RESERVE_SHARE of the budget, which is kept for catching up,
    and while slow accounts are still to be read the fast ones may use only half
    of it, so the slow accounts' gaps get the other half. Whatever is left at the
    end goes to the fast accounts' catch-up again. A scan call, and each catch-up
    phase, that runs out of time starts at the mailbox it stopped in next run, so
    the mailboxes after it are not starved.
    The reading loops run inside AppleScript: a process per call costs far more
    than Mail does, so calls are per account and per mailbox, never per message.
    """

    method = "mail"

    def __init__(self, accounts: list[Account], *, backfill_days: int, budget_s: float, runner=None,
                 now: datetime | None = None, clock=time.monotonic):
        self.accounts = accounts
        self.backfill_days = backfill_days
        self.runner = runner or OsaRunner()
        self.now = (now or datetime.now()).replace(microsecond=0, tzinfo=None)
        self.clock = clock
        self.budget_s = budget_s
        self.deadline = clock() + budget_s
        # Time the current step must leave unspent for the steps after it.
        self.floor = 0.0
        # Per run: why a mailbox's new-mail pass did not finish, and its lo when its
        # backfill was first given time (to tell progress from a stall).
        self.new_cut: dict[tuple[str, int], str] = {}
        self.backfill_from: dict[tuple[str, int], str] = {}

    def remaining(self) -> float:
        return self.deadline - self.clock()

    def available(self) -> float:
        """Time the current step may spend."""
        return self.remaining() - self.floor

    def selected(self, acc: Account) -> list[tuple[int, str]]:
        out = []
        # All Mail replaces INBOX and the labels only when Mail actually shows it.
        has_all_mail = acc.gmail and any(p.split("/")[-1].lower() == "all mail" for _, p in acc.mailboxes)
        for idx, path in acc.mailboxes:
            leaf = path.split("/")[-1]
            if SKIP_MAILBOX_RE.match(leaf) or path.lower().startswith(("tasks/", "notes/", "journal/")):
                continue
            if has_all_mail and not (GMAIL_FALLBACK_RE.match(leaf) or is_dedicated(path)):
                continue
            if acc.gmail and not has_all_mail and leaf.lower() in ("important", "starred", "chats"):
                continue
            out.append((idx, path))
        # Job folders first: a message read there keeps its "dedicated" mark when
        # the same message comes up again in All Mail (the caller skips repeats).
        return sorted(out, key=lambda ip: not is_dedicated(ip[1]))

    @staticmethod
    def max_chunk(acc: Account) -> int:
        """Gmail through Mail.app takes seconds per message; small chunks keep the
        time limit accurate. Exchange and iCloud are fast enough for big chunks."""
        return 25 if acc.gmail else 200

    def key(self, acc: Account, idx: int, path: str) -> str:
        dup = sum(1 for _, p in acc.mailboxes if p == path) > 1
        return f"mail:{acc.name}:{path}" + (f"#{idx}" if dup else "")

    @staticmethod
    def parse(raw: str) -> list[list[str]]:
        return [rec.split(US) for rec in raw.split(RS) if rec]

    @staticmethod
    def unique(rows: list[list[str]]) -> list[list[str]]:
        """R rows in reading order without the repeats that overlapping chunks produce."""
        seen, out = set(), []
        for r in rows:
            k = r[6] or (r[3], r[4], r[5])
            if k not in seen:
                seen.add(k)
                out.append(r)
        return out

    @staticmethod
    def handled_to(rows: list[list[str]], msgs: list[dict], done: int) -> datetime | None:
        """Oldest receive time down to which every row read was handled (delivered, or
        not kept), or None when no row was. Rows come newest-first, so when bodies ran
        out at msgs[done], only rows strictly newer than it count."""
        dates = [datetime.fromisoformat(r[3]) for r in rows]
        if done < len(msgs):
            cut = datetime.fromisoformat(msgs[done]["received"])
            dates = [d for d in dates if d > cut]
        return min(dates, default=None)

    @staticmethod
    def clip(gaps: list[list[str]], top: datetime) -> list[list[str]]:
        """Gaps cut off at `top` (everything above it is read), merged and sorted."""
        out: list[list[str]] = []
        for lo, hi in sorted([g[0], min(g[1], top.isoformat())] for g in gaps if g[0] <= top.isoformat()):
            if out and lo <= out[-1][1]:
                out[-1][1] = max(out[-1][1], hi)
            else:
                out.append([lo, hi])
        return out

    def fetch(self, cps: Checkpoints, keep: Callable[[dict], bool],
              sunk: Callable[[dict], None] = lambda m: None) -> FetchResult:
        """`keep` decides whether a message is read for classification; `sunk` is told about
        every message actually delivered in the result, and only those."""
        res = FetchResult()

        def sink(msgs: list[dict]) -> None:
            res.messages.extend(msgs)
            for m in msgs:
                sunk(m)

        try:
            self.runner("check", [], 120)  # ask Mail to sync before reading
        except MailError:
            pass
        # Gmail through Mail.app takes seconds per message; everything else is fast.
        fast = [a for a in self.accounts if not a.gmail]
        slow = [a for a in self.accounts if a.gmail]
        # Slow accounts take turns going first, so a budget that fits only some of them
        # never starves the same ones run after run (seen live: the first Gmail account
        # used the whole slow share every run).
        sched = dict(cps.get(SCHEDULE_KEY) or {})
        names = [a.name for a in slow]
        if sched.get("slow_start") in names:
            k = names.index(sched["slow_start"])
            slow = slow[k:] + slow[:k]
        plans: dict[tuple[str, int], tuple[Account, str, Health]] = {}
        for acc in fast + slow:
            for idx, path in self.selected(acc):
                plans[(acc.name, idx)] = (acc, path, Health(acc.name, path, self.method + (" (gmail fallback)" if acc.gmail else "")))

        def group(accs: list[Account]) -> list[tuple[int, Account, str, Health]]:
            names = {a.name for a in accs}
            return [(idx, acc, path, h) for (name, idx), (acc, path, h) in plans.items() if name in names]

        reserve = RESERVE_SHARE * self.budget_s
        self.floor = reserve  # new-mail passes leave the reserve for catching up
        for acc in fast:
            self.new_mail(acc, plans, cps, keep, sink)
        before = self.remaining()
        # With slow accounts still to read, the fast ones may catch up with half the reserve.
        self.floor = max(0.0, before - reserve / 2) if slow else 0.0
        self.catch_up("fast", group(fast), cps, keep, sink)
        self.floor = max(0.0, reserve - (before - self.remaining()))
        for acc in slow:
            self.new_mail(acc, plans, cps, keep, sink)
        if slow:
            cps.stage(SCHEDULE_KEY, {"slow_start": slow[1 % len(slow)].name})
        self.floor = 0.0
        if slow:
            self.catch_up("slow", group(slow), cps, keep, sink)
            self.catch_up("fast", group(fast), cps, keep, sink)  # whatever time is left
        for (_, idx), (acc, path, h) in plans.items():
            self.settle(acc, idx, path, h, cps)
        res.health = [h for _, _, h in plans.values()]
        return res

    def catch_up(self, name: str, mailboxes: list[tuple[int, Account, str, Health]], cps, keep, sink) -> None:
        """Gaps (unread stretches of recent mail) in every mailbox of the group, then
        backfill. Each phase starts at the mailbox it stopped in last time and goes
        round, so a mailbox the budget did not reach is first next run."""
        live = [mb for mb in mailboxes if mb[3].status != "error"]
        for phase, step in (("gaps", self.fill_gaps), ("backfill", self.backfill)):
            rotation = f"catch-up:{phase}:{name}"
            keys = [self.key(acc, idx, path) for idx, acc, path, _ in live]
            start = (cps.get(rotation) or {}).get("start")
            k = keys.index(start) if start in keys else 0
            stopped = None
            for idx, acc, path, h in live[k:] + live[:k]:
                if not step(acc, idx, path, h, cps, keep, sink) and stopped is None:
                    stopped = self.key(acc, idx, path)
            if (cps.get(rotation) or {}).get("start") != stopped:
                cps.stage(rotation, {"start": stopped})

    def _messages(self, acc, path, rows, h: Health, keep, since: datetime) -> list[dict]:
        """Messages for rows received at or after `since`. Reads overshoot by up to a
        chunk; older rows are already covered or belong to another pass, and bodies
        are slow to fetch, so they are dropped here."""
        out = []
        for r in rows:
            _, _, pos, iso, subject, sender, mid = r[:7]
            if datetime.fromisoformat(iso) < since:
                continue
            h.read += 1
            if acc.user and email.utils.parseaddr(sender)[1].lower() == acc.user.lower():
                continue  # our own outgoing mail (All Mail includes Sent)
            m = message(acc.name, path, subject, sender, datetime.fromisoformat(iso), mid,
                        dedicated=is_dedicated(path), source=self.method)
            m["_pos"], m["_mid_raw"] = int(pos), mid
            if keep(m):
                out.append(m)
        return out

    def _pin_target(self, cp: dict) -> None:
        """Pin the backfill target at the first attempt, so a window that starts on a
        failed day does not slide forward past unread mail."""
        target = self.now - timedelta(days=self.backfill_days)
        if not cp.get("target") or datetime.fromisoformat(cp["target"]) > target:
            cp["target"] = target.isoformat()

    def scan_order(self, acc: Account, mine: list[tuple[int, str, Health]], cps: Checkpoints) -> list[tuple[int, str]]:
        """Order of the account's scan call: job folders before the rest (their messages
        must keep the job mark when they come up again in All Mail), each group starting
        at the mailbox where the previous call ran out of time."""
        start = (cps.get(f"rotation:{acc.name}") or {}).get("start")
        out: list[tuple[int, str]] = []
        for dedicated in (True, False):
            group = [(idx, path) for idx, path, _ in mine if is_dedicated(path) == dedicated]
            k = next((n for n, (idx, _) in enumerate(group) if idx == start), 0)
            out += group[k:] + group[:k]
        return out

    def new_mail(self, acc, plans, cps, keep, sink) -> None:
        mine = [(idx, path, h) for (name, idx), (a, path, h) in plans.items() if name == acc.name]
        if not mine:
            return
        starts = {}
        for idx, path, h in mine:
            cp = cps.get(self.key(acc, idx, path)) or {}
            # A checkpoint later than now (the clock moved backwards) must not hide mail.
            hi = min(datetime.fromisoformat(cp["hi"]), self.now) if cp.get("hi") else self.now
            starts[idx] = hi - OVERLAP
        order = self.scan_order(acc, mine, cps)
        rows_by, counts, state = {}, {}, {}
        if self.available() > 0:
            specs = [US.join([str(idx), path.split("/")[-1], str(int((self.now - starts[idx]).total_seconds()))])
                     for idx, path in order]
            try:
                # Reading headers may use 60% of what is left; the rest is for bodies.
                raw = self.runner("scan", [acc.name, RS.join(specs), int(self.available() * READ_SHARE),
                                           self.max_chunk(acc), CHUNK_OVERLAP], self.remaining() + 120)
            except MailError as e:
                for _, _, h in mine:
                    h.status, h.error = "error", str(e)
                return
            for f in self.parse(raw):
                ix = int(f[1])
                if f[0] == "B":
                    counts[ix] = int(f[2])
                elif f[0] == "R":
                    rows_by.setdefault(ix, []).append(f)
                elif f[0] in ("D", "T"):
                    state[ix] = f[0]
                elif f[0] == "E":
                    state[ix] = "E"
                    plans[(acc.name, ix)][2].error = f[2] if len(f) > 2 else "error"
        # Never reached: the time limit ended the call first.
        cut = next((idx for idx, _ in order if state.get(idx, "T") == "T"), None)
        rotation = f"rotation:{acc.name}"
        if (cps.get(rotation) or {}).get("start") != cut:
            cps.stage(rotation, {"start": cut})
        target = self.now - timedelta(days=self.backfill_days)

        for idx, path, h in mine:
            key = self.key(acc, idx, path)
            st = state.get(idx, "T")
            if st == "E":
                h.status = "error"
                cp = dict(cps.get(key) or {})
                self._pin_target(cp)
                cps.stage(key, cp)
                continue
            rows = self.unique(rows_by.get(idx, []))
            # Read to the bottom: everything down to the target counts now; otherwise
            # only mail since the stop point (older mail is covered, or backfilled).
            read_all = st == "D" and max((int(r[2]) for r in rows), default=0) >= counts.get(idx, 0)
            msgs = self._messages(acc, path, rows, h, keep, target if read_all else starts[idx])
            try:
                done = self._fill_snippets(acc, idx, path, msgs, h)
            except MailError as e:
                h.status, h.error = "error", str(e)
                continue
            sink(msgs[:done])  # the rest is re-read next run; nothing is dropped
            h.kept += done
            cp = dict(cps.get(key) or {})
            self._pin_target(cp)
            if st == "D" and done == len(msgs):
                if read_all:
                    cp["lo"], cp["gaps"] = cp["target"], []
                else:
                    cp["lo"] = cp.get("lo") or starts[idx].isoformat()
                    cp["gaps"] = self.clip(cp.get("gaps") or [], starts[idx])
            else:
                handled = self.handled_to(rows, msgs, done)
                upto = handled or self.now
                if cp.get("hi"):
                    gaps = (cp.get("gaps") or []) + ([[starts[idx].isoformat(), upto.isoformat()]] if upto >= starts[idx] else [])
                    cp["lo"] = min(datetime.fromisoformat(cp["lo"]), upto).isoformat()
                    cp["gaps"] = self.clip(gaps, upto)
                else:
                    cp["lo"], cp["gaps"] = upto.isoformat(), []
                self.new_cut[(acc.name, idx)] = (
                    "time budget reached while reading bodies; the rest is read next run" if done < len(msgs)
                    else "time budget reached; the rest is read next run" if rows
                    else "not reached before the time budget ran out; read first next run")
            cp["hi"] = self.now.isoformat()
            cps.stage(key, cp)

    def _read_back(self, acc, idx, path, h: Health, keep, sink, top: datetime, bottom: datetime) -> tuple[bool, datetime | None]:
        """Read one mailbox from top + OVERLAP down to bottom and deliver what was handled.
        Returns (True, None) when everything down to bottom was handled; otherwise
        (False, the oldest time down to which it was, or None when nothing was)."""
        raw = self.runner("scanfrom", [acc.name, idx, path.split("/")[-1],
                                       max(0, int((self.now - (top + OVERLAP)).total_seconds())),
                                       int((self.now - bottom).total_seconds()), int(self.available() * READ_SHARE),
                                       self.max_chunk(acc), CHUNK_OVERLAP],
                          self.remaining() + 120)
        recs = self.parse(raw)
        rows = self.unique([f for f in recs if f[0] == "R"])
        msgs = self._messages(acc, path, rows, h, keep, bottom)
        done = self._fill_snippets(acc, idx, path, msgs, h)
        sink(msgs[:done])
        h.kept += done
        if done == len(msgs) and any(f[0] == "D" for f in recs):
            return True, None
        return False, self.handled_to(rows, msgs, done)

    def fill_gaps(self, acc, idx, path, h, cps, keep, sink) -> bool:
        """Read the stretches an earlier, cut-short pass left unread, newest first,
        shrinking each gap to what is still unread after every read. True when no
        gap is left (or the mailbox failed and is reported)."""
        key = self.key(acc, idx, path)
        cp = dict(cps.get(key) or {})
        gaps = sorted(cp.get("gaps") or [], key=lambda g: g[1], reverse=True)
        while gaps and self.available() > 0:
            lo, hi = gaps[0]
            try:
                complete, upto = self._read_back(acc, idx, path, h, keep, sink,
                                                 datetime.fromisoformat(hi), datetime.fromisoformat(lo))
            except MailError as e:
                h.status, h.error = "error", str(e)
                return True
            if complete or (upto is not None and upto.isoformat() <= lo):
                gaps.pop(0)
            elif upto is not None:
                gaps[0] = [lo, min(hi, upto.isoformat())]
            cp["gaps"] = sorted(gaps)
            cps.stage(key, cp)
            if not complete:
                break
        return not gaps

    def backfill(self, acc, idx, path, h, cps, keep, sink) -> bool:
        """Extend coverage back toward the target. True when there is nothing left to
        backfill (or the mailbox failed and is reported)."""
        key = self.key(acc, idx, path)
        cp = dict(cps.get(key) or {})
        if not cp.get("lo"):
            return True
        lo, target = datetime.fromisoformat(cp["lo"]), datetime.fromisoformat(cp["target"])
        if lo <= target:
            return True
        if self.available() <= 0:
            return False
        self.backfill_from.setdefault((acc.name, idx), cp["lo"])
        try:
            complete, upto = self._read_back(acc, idx, path, h, keep, sink, lo, target)
        except MailError as e:
            h.status, h.error = "error", str(e)
            return True
        if complete:
            cp["lo"] = target.isoformat()
        elif upto is not None:
            # Coverage may only move down to the oldest message fully handled.
            cp["lo"] = min(lo, upto).isoformat()
        cps.stage(key, cp)
        return complete

    def settle(self, acc, idx, path, h, cps) -> None:
        """The mailbox's status for this run. Partial (counted in partial_runs; past
        STARVED_RUNS in a row an error) only for what stops convergence: new mail not
        all read, a gap still open, or a backfill that was given time and did not move.
        A backfill still on its way back to the target, or not reached this run, is ok."""
        if h.status == "error":
            return
        key = self.key(acc, idx, path)
        cp = dict(cps.get(key) or {})
        reasons = []
        if (acc.name, idx) in self.new_cut:
            reasons.append(self.new_cut[(acc.name, idx)])
        gaps = cp.get("gaps") or []
        if gaps:
            reasons.append(f"{len(gaps)} unread stretch(es) of mail, the newest ending "
                           f"{max(g[1] for g in gaps)[:10]}; continues next run")
        started = self.backfill_from.get((acc.name, idx))
        if started and cp.get("lo") and cp["lo"] > cp["target"] and cp["lo"] >= started:
            reasons.append("backfill made no progress this run")
        if reasons:
            h.status, h.error = "partial", "; ".join(reasons)
        runs = cp.get("partial_runs", 0) + 1 if reasons else 0
        if runs != cp.get("partial_runs", 0):
            cp["partial_runs"] = runs
            cps.stage(key, cp)
        if runs >= STARVED_RUNS:
            h.status = "error"
            h.error = (f"still partial after {runs} runs in a row ({h.error}); raise --budget-minutes"
                       + (" or store an app password" if acc.gmail else ""))
        if cp.get("hi"):
            h.covered_from, h.covered_to, h.target = cp["lo"][:10], cp["hi"][:10], cp["target"][:10]

    def _fill_snippets(self, acc, idx, path, msgs: list[dict], h: Health) -> int:
        """Fetch bodies in order until the budget ends; returns how many messages are done.
        A message's body is never skipped silently: it is either fetched, reported
        unavailable by Mail (counted in h.unavailable and marked body_unavailable), or
        left for the next run with the messages after it."""
        name = path.split("/")[-1]
        for i in range(0, len(msgs), 40):
            if self.available() <= 0:
                return i
            batch = msgs[i:i + 40]
            chunk = [m for m in batch if m["_mid_raw"]]
            if chunk:
                pairs = RS.join(US.join([str(m["_pos"]), m["_mid_raw"]]) for m in chunk)
                # The script stops itself at the limit; the timeout only covers the
                # one message in flight when it does.
                raw = self.runner("content", [acc.name, idx, name, pairs, BODY_BYTES, int(self.available())],
                                  self.remaining() + 120)
                texts, cut = {}, False
                for f in self.parse(raw):
                    if len(f) >= 2:
                        texts[f[0].strip().lower()] = f[1]
                    elif f == ["T"]:
                        cut = True
                if cut:
                    # Bodies come back in order: everything from the first one not
                    # returned is left for the next run.
                    left = next((n for n, m in enumerate(batch)
                                 if m["_mid_raw"] and m["_mid_raw"].strip().lower() not in texts), len(batch))
                    batch = batch[:left]
                    chunk = [m for m in batch if m["_mid_raw"]]
                for m in chunk:
                    t = texts.get(m["_mid_raw"].strip().lower(), "!notfound")
                    if t in ("!notfound", "!unavailable"):
                        m["snippet"], m["body_unavailable"] = "", True
                        h.unavailable += 1
                        h.error = h.error or "some message bodies were unavailable; classified from subject and sender"
                    else:
                        m["snippet"] = text_snippet(t.encode("utf-8", "replace"))
            for m in batch:
                m.pop("_pos", None)
                m.pop("_mid_raw", None)
            if len(batch) < len(msgs[i:i + 40]):
                return i + len(batch)
        return len(msgs)
