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
   record that the inbox review, the exit code and --doctor surface.

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
    covered time minus an overlap (new mail), then extends coverage backwards
    toward the backfill target in budgeted steps that resume where they stopped.
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
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Callable, Iterable

KEYCHAIN_SERVICE = "career-ops-mail"
# Re-read this much before the last covered time: Mail.app can download a
# message after the run that would have seen it, with an older received date.
OVERLAP = timedelta(days=2)
SNIPPET_CHARS = 1500
# Share of the remaining time budget a header read may use; bodies get the rest.
READ_SHARE = 0.6
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


# ── Persistent state ─────────────────────────────────────────────────────────

class Checkpoints:
    """Per-mailbox coverage. Sources stage updates; the caller commits them only
    after the messages they cover were recorded."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}
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

    def __init__(self, path: Path, days: int = 30):
        self.path, self.days = path, days
        self.data: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

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
    covered_from: str = ""
    covered_to: str = ""

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
    kind: str          # Mail.app class: "imap account", "account" (Exchange/EWS), ...
    user: str          # login address
    server: str        # IMAP host, '' for Exchange
    mailboxes: list[tuple[int, str]] = field(default_factory=list)  # (Mail.app index, full path)

    @property
    def gmail(self) -> bool:
        return self.server.lower().endswith("gmail.com") or self.server.lower().endswith("googlemail.com")

    @property
    def imap_capable(self) -> bool:
        return "imap" in self.kind.lower() and bool(self.server) and bool(self.user)


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
        out = []
        for flags, raw in parse_list(data):
            display = imap_utf7_decode(raw)
            if "\\noselect" in flags or "\\nonexistent" in flags:
                continue
            if acc.gmail:
                # All Mail holds every message in every label except Spam and Trash.
                if flags & {"\\all", "\\junk", "\\trash"}:
                    out.append((raw, display))
            elif not (flags & {"\\sent", "\\drafts", "\\all"}) and not SKIP_MAILBOX_RE.match(display.split("/")[-1]):
                out.append((raw, display))
        if acc.gmail and not any("all" in d.lower() for _, d in out):
            raise RuntimeError("Gmail All Mail is not visible over IMAP; enable 'Show in IMAP' for All Mail in Gmail settings")
        return out

    def fetch(self, cps: Checkpoints, keep: Callable[[dict], bool]) -> FetchResult:
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
                        res.messages += self.scan(conn, acc, raw, display, cps, keep, h)
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
    # index US name US stop-age-seconds, joined by RS), time limit in seconds.
    # Per mailbox: B(index, count), R rows newest-first until a chunk ends older
    # than the stop age, then D (done); E on a per-mailbox error; T (index,
    # position) when the time limit is reached, after which nothing else runs.
    "scan": r"""
on run argv
  set US to ASCII character 31
  set RS to ASCII character 30
  set limitSecs to (item 3 of argv) as integer
  set maxChunk to (item 4 of argv) as integer
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
          repeat while pos ≤ n
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
            set pos to e + 1
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
    # Backfill one mailbox. argv: account, index, name, from-age, to-age (seconds
    # before now), time limit. Binary-searches the first position older than
    # from-age (dates fall with position), then reads down until a chunk ends
    # older than to-age (D), the end of the mailbox (D), or the limit (T).
    "scanfrom": r"""
on run argv
  set US to ASCII character 31
  set RS to ASCII character 30
  set limitSecs to (item 6 of argv) as integer
  set maxChunk to (item 7 of argv) as integer
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
      repeat while pos ≤ n
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
        set pos to e + 1
      end repeat
    end tell
  end timeout
  return out & "D" & US & ix & RS
end run""",
    # Body text of the given messages. argv: account, index, name, records of
    # position US message-id joined by RS, max chars. Positions shift when new
    # mail arrives, so a Message-ID mismatch searches the neighbourhood. Each
    # body has its own 30 s limit: one message Mail must download slowly is
    # returned as !unavailable instead of failing the mailbox.
    "content": r"""
on run argv
  set US to ASCII character 31
  set RS to ASCII character 30
  set limit to (item 5 of argv) as integer
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
          set t to "!unavailable"
          try
            with timeout of 30 seconds
              set t to content of found
            end timeout
          end try
          if t is missing value then set t to ""
          if (length of t) > limit then set t to text 1 thru limit of t
          set out to out & want & US & t & RS
        end if
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

    def __call__(self, op: str, args: list[str], timeout: float) -> str:
        t0 = time.monotonic()
        try:
            return self._run(op, args, timeout)
        finally:
            if os.environ.get("MAIL_SYNC_TRACE"):
                print(f"trace: {op} {args[:3] if op != 'scan' else args[:1]} {time.monotonic() - t0:.1f}s", file=sys.stderr, flush=True)

    def _run(self, op: str, args: list[str], timeout: float) -> str:
        try:
            p = subprocess.run(["osascript", "-", *map(str, args)], input=APPLESCRIPT[op], capture_output=True,
                               text=True, timeout=max(30, timeout))
        except subprocess.TimeoutExpired as e:
            raise MailError(f"{op}: timed out after {int(timeout)}s") from e
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

    Checkpoint per mailbox: {"hi": time up to which everything is read, "lo":
    time back to which everything is read, "target": backfill target}. A run
    first reads new mail in every mailbox (one `scan` call per account, from the
    top down to hi - OVERLAP); only a mailbox whose pass completed moves hi to
    the run's start. With the budget that is left it extends each mailbox's lo
    back toward target (`scanfrom`), keeping progress after every chunk read.
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
        self.deadline = clock() + budget_s

    def remaining(self) -> float:
        return self.deadline - self.clock()

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

    def fetch(self, cps: Checkpoints, keep: Callable[[dict], bool]) -> FetchResult:
        res = FetchResult()
        try:
            self.runner("check", [], 120)  # ask Mail to sync before reading
        except MailError:
            pass
        accounts = sorted(self.accounts, key=lambda a: a.gmail)  # Gmail through Mail.app is the slow part
        plans: dict[tuple[str, int], tuple[Account, str, Health]] = {}
        for acc in accounts:
            for idx, path in self.selected(acc):
                plans[(acc.name, idx)] = (acc, path, Health(acc.name, path, self.method + (" (gmail fallback)" if acc.gmail else "")))
        for acc in accounts:
            self.new_mail(acc, plans, cps, keep, res.messages)
        for (name, idx), (acc, path, h) in plans.items():
            if h.status == "ok":
                self.backfill(acc, idx, path, h, cps, keep, res.messages)
        res.health = [h for _, _, h in plans.values()]
        return res

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

    def new_mail(self, acc, plans, cps, keep, sink) -> None:
        mine = [(idx, path, h) for (name, idx), (a, path, h) in plans.items() if name == acc.name]
        if not mine:
            return
        specs, starts = [], {}
        for idx, path, h in mine:
            cp = cps.get(self.key(acc, idx, path)) or {}
            # A checkpoint later than now (the clock moved backwards) must not hide mail.
            hi = min(datetime.fromisoformat(cp["hi"]), self.now) if cp.get("hi") else self.now
            stop_at = hi - OVERLAP
            starts[idx] = stop_at
            specs.append(US.join([str(idx), path.split("/")[-1], str(int((self.now - stop_at).total_seconds()))]))
        if self.remaining() <= 0:
            for idx, path, h in mine:
                h.status, h.error = "partial", "time budget reached; continues next run"
                cp = dict(cps.get(self.key(acc, idx, path)) or {})
                if not cp.get("target"):
                    cp["target"] = (self.now - timedelta(days=self.backfill_days)).isoformat()
                    cps.stage(self.key(acc, idx, path), cp)
            return
        try:
            # Reading headers may use 60% of what is left; the rest is for bodies.
            raw = self.runner("scan", [acc.name, RS.join(specs), int(self.remaining() * READ_SHARE), self.max_chunk(acc)],
                              self.remaining() + 120)
        except MailError as e:
            for _, _, h in mine:
                h.status, h.error = "error", str(e)
            return
        rows_by, counts, state = {}, {}, {}
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
        target = self.now - timedelta(days=self.backfill_days)

        def anchor_target(idx, path):
            """Pin the backfill target at the first attempt even when nothing finished, so a
            window that starts on a failed day does not slide forward past unread mail."""
            key = self.key(acc, idx, path)
            cp = dict(cps.get(key) or {})
            if not cp.get("target") or datetime.fromisoformat(cp["target"]) > target:
                cp["target"] = target.isoformat()
                cps.stage(key, cp)

        for idx, path, h in mine:
            st = state.get(idx, "T")  # never reached: the time limit ended the call first
            rows = rows_by.get(idx, [])
            # Read to the bottom: everything down to the target counts now; otherwise
            # only mail since the stop point (older mail is covered, or backfilled).
            read_all = st == "D" and len(rows) >= counts.get(idx, 0)
            msgs = self._messages(acc, path, rows, h, keep, target if read_all else starts[idx])
            if st == "E":
                h.status = "error"
                anchor_target(idx, path)
                continue
            try:
                done = self._fill_snippets(acc, idx, path, msgs, h)
            except MailError as e:
                h.status, h.error = "error", str(e)
                continue
            sink.extend(msgs[:done])  # the rest is re-read next run; nothing is dropped
            h.kept += done
            if done < len(msgs):
                h.status, h.error = "partial", "time budget reached while reading bodies; continues next run"
                anchor_target(idx, path)
                continue
            if st != "D":
                h.status, h.error = "partial", "time budget reached; continues next run"
                anchor_target(idx, path)
                continue
            key = self.key(acc, idx, path)
            cp = dict(cps.get(key) or {})
            cp["target"] = min(datetime.fromisoformat(cp["target"]), target).isoformat() if cp.get("target") else target.isoformat()
            if read_all:
                cp["lo"] = cp["target"]
            elif not cp.get("lo"):
                cp["lo"] = starts[idx].isoformat()
            cp["hi"] = self.now.isoformat()
            cps.stage(key, cp)
            h.covered_from, h.covered_to = cp["lo"][:10], cp["hi"][:10]

    def backfill(self, acc, idx, path, h, cps, keep, sink) -> None:
        key = self.key(acc, idx, path)
        cp = dict(cps.get(key) or {})
        if not cp.get("lo"):
            return
        lo, target = datetime.fromisoformat(cp["lo"]), datetime.fromisoformat(cp["target"])
        if lo <= target:
            return
        if self.remaining() <= 0:
            h.status, h.error = "partial", "backfill continues next run"
            return
        try:
            raw = self.runner("scanfrom", [acc.name, idx, path.split("/")[-1],
                                           int((self.now - (lo + OVERLAP)).total_seconds()),
                                           int((self.now - target).total_seconds()), int(self.remaining() * READ_SHARE),
                                           self.max_chunk(acc)],
                              self.remaining() + 120)
        except MailError as e:
            h.status, h.error = "error", str(e)
            return
        recs = self.parse(raw)
        rows = [f for f in recs if f[0] == "R"]
        done = any(f[0] == "D" for f in recs)
        msgs = self._messages(acc, path, rows, h, keep, target)
        try:
            filled = self._fill_snippets(acc, idx, path, msgs, h)
        except MailError as e:
            h.status, h.error = "error", str(e)
            return
        sink.extend(msgs[:filled])
        h.kept += filled
        if filled < len(msgs):
            # Coverage may only move down to the oldest message fully handled.
            if filled:
                cp["lo"] = min(lo, min(datetime.fromisoformat(m["received"]) for m in msgs[:filled])).isoformat()
                cps.stage(key, cp)
            h.status, h.error = "partial", "time budget reached while reading bodies; continues next run"
            return
        if done:
            cp["lo"] = target.isoformat()
        else:
            if rows:
                cp["lo"] = min(lo, min(datetime.fromisoformat(f[3]) for f in rows)).isoformat()
            h.status, h.error = "partial", "backfill continues next run"
        cps.stage(key, cp)
        h.covered_from = cp["lo"][:10]

    def _fill_snippets(self, acc, idx, path, msgs: list[dict], h: Health) -> int:
        """Fetch bodies in order until the budget ends; returns how many messages are done.
        A message's body is never skipped silently: it is either fetched, reported
        unavailable by Mail, or left for the next run with the messages after it."""
        name = path.split("/")[-1]
        for i in range(0, len(msgs), 40):
            if self.remaining() <= 0:
                return i
            chunk = [m for m in msgs[i:i + 40] if m["_mid_raw"]]
            if chunk:
                pairs = RS.join(US.join([str(m["_pos"]), m["_mid_raw"]]) for m in chunk)
                raw = self.runner("content", [acc.name, idx, name, pairs, SNIPPET_CHARS], max(600, self.remaining() + 120))
                texts = {}
                for f in self.parse(raw):
                    if len(f) >= 2:
                        texts[f[0].strip().lower()] = f[1]
                for m in chunk:
                    t = texts.get(m["_mid_raw"].strip().lower(), "!notfound")
                    if t in ("!notfound", "!unavailable"):
                        m["snippet"] = ""
                        h.error = h.error or "some message bodies were unavailable; classified from subject and sender"
                    else:
                        m["snippet"] = " ".join(t.split())
            for m in msgs[i:i + 40]:
                m.pop("_pos", None)
                m.pop("_mid_raw", None)
        return len(msgs)
