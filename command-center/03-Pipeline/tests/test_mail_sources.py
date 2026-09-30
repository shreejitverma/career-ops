"""Behavior tests for mail_sources.py: python3 -m unittest discover -s command-center/03-Pipeline/tests

The core property is "nothing is missed": over any sequence of runs, however the
time budget cuts them, the messages returned cover every message in the window,
and a checkpoint never claims coverage of something that was not returned.
"""

import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mail_sources as ms  # noqa: E402

NOW = datetime(2026, 9, 30, 9, 0, 0)


# ── Apple Mail fake ──────────────────────────────────────────────────────────

class FakeMail:
    """Emulates the scan / scanfrom / content AppleScripts over newest-first lists.
    Every call and every message read costs clock time, and the scripts' time
    limits are checked against that clock, so budgets bite as they do for real."""

    def __init__(self, boxes, clock, cost_per_call=1.0, cost_per_msg=0.5):
        self.boxes = boxes  # {(account, index): {"name": str, "msgs": [(datetime, subject, sender, mid, body)]}}
        self.clock = clock
        self.cost_per_call, self.cost_per_msg = cost_per_call, cost_per_msg
        self.now = NOW
        self.calls = []

    def _msgs(self, acc, ix):
        box = self.boxes[(acc, int(ix))]
        box["msgs"].sort(key=lambda m: m[0], reverse=True)
        return box

    def _row(self, ix, pos, m):
        return ms.US.join(["R", str(ix), str(pos), m[0].isoformat(), m[1], m[2], m[3]])

    def _age(self, m):
        return (self.now - m[0]).total_seconds()

    def __call__(self, op, args, timeout):
        self.calls.append(op)
        self.clock.t += self.cost_per_call
        start = self.clock.t
        out = []
        if op == "check":
            return "ok"
        if op == "scan":
            acc, limit = args[0], int(args[2])
            for spec in [r.split(ms.US) for r in args[1].split(ms.RS) if r]:
                ix, name, stop_age = int(spec[0]), spec[1], int(spec[2])
                box = self._msgs(acc, ix)
                if box["name"] != name:
                    out.append(ms.US.join(["E", str(ix), f"mailbox moved: expected {name}, found {box['name']}"]))
                    continue
                msgs = box["msgs"]
                n = len(msgs)
                out.append(ms.US.join(["B", str(ix), str(n)]))
                pos, size = 1, min(25, int(args[3]))
                while pos <= n:
                    if self.clock.t - start > limit:
                        out.append(ms.US.join(["T", str(ix), str(pos)]))
                        return ms.RS.join(out)
                    end = min(n, pos + size - 1)
                    rows = msgs[pos - 1:end]
                    self.clock.t += self.cost_per_msg * len(rows)
                    out += [self._row(ix, pos + k, m) for k, m in enumerate(rows)]
                    if self._age(rows[-1]) > stop_age:
                        break
                    pos, size = end + 1, min(size * 2, int(args[3]))
                out.append(ms.US.join(["D", str(ix)]))
            return ms.RS.join(out)
        box = self._msgs(args[0], args[1])
        if box["name"] != args[2]:
            raise ms.MailError(f"{op}: mailbox moved: expected {args[2]}, found {box['name']}")
        msgs = box["msgs"]
        n = len(msgs)
        if op == "scanfrom":
            from_age, to_age, limit = int(args[3]), int(args[4]), int(args[5])
            out.append(ms.US.join(["B", str(args[1]), str(n)]))
            lo, hi = 1, n + 1
            while lo < hi:
                mid = (lo + hi) // 2
                self.clock.t += self.cost_per_msg
                if self._age(msgs[mid - 1]) > from_age:
                    hi = mid
                else:
                    lo = mid + 1
            pos = max(1, lo - 1)
            while pos <= n:
                if self.clock.t - start > limit:
                    out.append(ms.US.join(["T", str(args[1]), str(pos)]))
                    return ms.RS.join(out)
                end = min(n, pos + int(args[6]) - 1)
                rows = msgs[pos - 1:end]
                self.clock.t += self.cost_per_msg * len(rows)
                out += [self._row(args[1], pos + k, m) for k, m in enumerate(rows)]
                if self._age(rows[-1]) > to_age:
                    break
                pos = end + 1
            out.append(ms.US.join(["D", str(args[1])]))
            return ms.RS.join(out)
        if op == "content":
            by_mid = {m[3].lower(): m for m in msgs}
            for pair in [r.split(ms.US) for r in args[3].split(ms.RS) if r]:
                m = by_mid.get(pair[1].lower())
                out.append(ms.US.join([pair[1], m[4] if m else "!notfound"]))
            return ms.RS.join(out)
        raise AssertionError(op)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def mk(i, when, subject=None, sender="Recruiter <talent@acme.test>", body="Thanks for applying"):
    # Mail's `message id` has no angle brackets (checked against real Mail).
    return (when, subject or f"Message {i}", sender, f"m{i}@acme.test", body)


def exchange(boxes_spec):
    """Account with mailboxes {index: path}."""
    return ms.Account("Exchange", "account", "me@school.edu", "", [(i, p) for i, p in boxes_spec.items()])


class AppleMailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cps_path = Path(self.tmp.name) / "cp.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_once(self, fake, acc, now, budget, returned, backfill=30):
        cps = ms.Checkpoints(self.cps_path)
        seen = set(returned)

        def keep(m):
            # As in sync_job_emails.fetch_messages: skip anything already handled,
            # including earlier in this run (backfill overlaps the new-mail pass).
            if m["message_id"] in seen:
                return False
            seen.add(m["message_id"])
            return True

        fake.now = now
        src = ms.AppleMailSource([acc], backfill_days=backfill, budget_s=budget, runner=fake, now=now, clock=fake.clock)
        res = src.fetch(cps, keep)
        cps.commit()
        got = [m["message_id"] for m in res.messages]
        for mid in got:
            self.assertNotIn(mid, returned, "a message was returned twice")
            returned.add(mid)
        return res, cps

    def test_reads_everything_in_window_and_nothing_twice(self):
        clock = Clock()
        msgs = [mk(i, NOW - timedelta(hours=7 * i)) for i in range(200)]  # ~58 days
        fake = FakeMail({("Exchange", 1): {"name": "Inbox", "msgs": list(msgs)}}, clock)
        returned: set[str] = set()
        self.run_once(fake, exchange({1: "Inbox"}), NOW, budget=10_000, returned=returned)
        want = {ms.clean_mid(m[3]) for m in msgs if m[0] >= NOW - timedelta(days=30)}
        self.assertTrue(want <= returned, f"missed {sorted(want - returned)[:5]}")
        cp = ms.Checkpoints(self.cps_path).data
        self.assertEqual(list(cp.values())[0]["hi"], NOW.isoformat())

    def test_budget_cuts_resume_without_gaps_property(self):
        """Random mailboxes, arrival patterns and tiny budgets: after enough runs every
        message in the window has been returned exactly once."""
        rng = random.Random(20260930)
        for trial in range(40):
            clock = Clock()
            n = rng.randint(0, 400)
            base = [mk(i, NOW - timedelta(minutes=rng.randint(0, 60 * 24 * 40))) for i in range(n)]
            box = {"name": "JOB", "msgs": list(base)}
            fake = FakeMail({("Exchange", 7): box}, clock, cost_per_msg=rng.choice([0.1, 0.5, 2.0]))
            acc = exchange({7: "JOB"})
            returned: set[str] = set()
            now = NOW
            all_msgs = list(base)
            self.cps_path = Path(self.tmp.name) / f"cp-{trial}.json"
            for run in range(60):
                # New mail between runs, including some that Mail downloads late with an older date.
                for k in range(rng.randint(0, 6)):
                    age = timedelta(hours=rng.choice([1, 5, 20, 30])) if rng.random() < 0.3 else timedelta(minutes=rng.randint(1, 600))
                    m = mk(10_000 * (trial + 1) + 100 * run + k, now - age)
                    box["msgs"].append(m)
                    all_msgs.append(m)
                self.run_once(fake, acc, now, budget=rng.choice([15, 40, 120, 10_000]), returned=returned)
                now += timedelta(hours=rng.choice([6, 24]))
            # Final generous run with no new mail.
            self.run_once(fake, acc, now, budget=100_000, returned=returned)
            target = NOW - timedelta(days=30)
            want = {ms.clean_mid(m[3]) for m in all_msgs if m[0] >= target}
            self.assertTrue(want <= returned, f"trial {trial}: missed {len(want - returned)} of {len(want)}")

    def test_checkpoint_from_the_future_does_not_hide_mail(self):
        clock = Clock()
        msgs = [mk(i, NOW - timedelta(hours=i)) for i in range(10)]
        fake = FakeMail({("Exchange", 1): {"name": "Inbox", "msgs": list(msgs)}}, clock)
        cps = ms.Checkpoints(self.cps_path)
        future = (NOW + timedelta(days=10)).isoformat()
        cps.stage("mail:Exchange:Inbox", {"hi": future, "lo": (NOW - timedelta(days=40)).isoformat(),
                                          "target": (NOW - timedelta(days=40)).isoformat()})
        cps.commit()
        returned: set[str] = set()
        self.run_once(fake, exchange({1: "Inbox"}), NOW, budget=1000, returned=returned)
        self.assertEqual(returned, {ms.clean_mid(m[3]) for m in msgs})

    def test_budget_cut_mid_backfill_keeps_what_was_read(self):
        clock = Clock()
        msgs = [mk(i, NOW - timedelta(hours=3 * i)) for i in range(300)]
        fake = FakeMail({("Exchange", 1): {"name": "Inbox", "msgs": list(msgs)}}, clock, cost_per_msg=1.0)
        returned: set[str] = set()
        res, cps = self.run_once(fake, exchange({1: "Inbox"}), NOW, budget=150, returned=returned)
        cp = list(ms.Checkpoints(self.cps_path).data.values())[0]
        lo = datetime.fromisoformat(cp["lo"])
        covered = {ms.clean_mid(m[3]) for m in msgs if m[0] >= lo and m[0] <= NOW}
        self.assertTrue(covered <= returned, "checkpoint claims coverage of messages that were not returned")
        self.assertEqual(res.health[0].status, "partial")

    def test_budget_cut_in_new_pass_does_not_advance(self):
        clock = Clock()
        msgs = [mk(i, NOW - timedelta(minutes=10 * i)) for i in range(100)]
        fake = FakeMail({("Exchange", 1): {"name": "Inbox", "msgs": list(msgs)}}, clock, cost_per_msg=1.0)
        res, _ = self.run_once(fake, exchange({1: "Inbox"}), NOW, budget=5, returned=set())
        self.assertEqual(res.health[0].status, "partial")
        # No coverage is claimed; only the backfill target is pinned to this first attempt.
        self.assertEqual(ms.Checkpoints(self.cps_path).data,
                         {"mail:Exchange:Inbox": {"target": (NOW - timedelta(days=30)).isoformat()}})

    def test_moved_mailbox_is_an_error_and_not_checkpointed(self):
        clock = Clock()
        fake = FakeMail({("Exchange", 1): {"name": "Renamed", "msgs": [mk(1, NOW)]}}, clock)
        res, _ = self.run_once(fake, exchange({1: "Inbox"}), NOW, budget=100, returned=set())
        self.assertEqual(res.health[0].status, "error")
        self.assertIn("mailbox moved", res.health[0].error)
        self.assertNotIn("hi", ms.Checkpoints(self.cps_path).data.get("mail:Exchange:Inbox", {}))

    def test_message_ids_with_commas_and_pipes_survive(self):
        clock = Clock()
        odd = (NOW - timedelta(hours=1), "Update", "Recruiter <talent@acme.test>", "a,b|c@odspnotify", "Body text")
        fake = FakeMail({("Exchange", 1): {"name": "GA Job", "msgs": [odd]}}, clock)
        returned: set[str] = set()
        res, _ = self.run_once(fake, exchange({1: "GA Job"}), NOW, budget=1000, returned=returned)
        self.assertEqual(returned, {"a,b|c@odspnotify"})
        self.assertEqual(res.messages[0]["snippet"], "Body text")
        self.assertEqual(res.health[0].status, "ok")

    def test_old_mail_is_never_body_fetched(self):
        clock = Clock()
        old = [mk(i, NOW - timedelta(days=200 + i)) for i in range(30)]
        fake = FakeMail({("Exchange", 1): {"name": "Trading Challenge", "msgs": list(old)}}, clock)
        res, _ = self.run_once(fake, exchange({1: "Trading Challenge"}), NOW, budget=1000, returned=set())
        self.assertEqual(res.messages, [])
        self.assertNotIn("content", fake.calls)
        self.assertEqual(res.health[0].read, 0)
        cp = list(ms.Checkpoints(self.cps_path).data.values())[0]
        self.assertEqual(cp["lo"], cp["target"])  # the whole mailbox was read: nothing left to backfill

    def test_duplicate_folder_names_get_their_own_checkpoints(self):
        clock = Clock()
        fake = FakeMail({("Exchange", 40): {"name": "Handshake", "msgs": [mk(1, NOW - timedelta(hours=1))]},
                         ("Exchange", 43): {"name": "Handshake", "msgs": [mk(2, NOW - timedelta(hours=2))]}}, clock)
        acc = ms.Account("Exchange", "account", "me@school.edu", "", [(40, "JOB/Handshake"), (43, "JOB/Handshake")])
        returned: set[str] = set()
        self.run_once(fake, acc, NOW, budget=1000, returned=returned)
        self.assertEqual(returned, {"m1@acme.test", "m2@acme.test"})
        self.assertEqual(len(ms.Checkpoints(self.cps_path).data), 2)

    def test_own_outgoing_mail_is_skipped_and_snippet_fetched(self):
        clock = Clock()
        box = {"name": "All Mail", "msgs": [mk(1, NOW - timedelta(hours=1), sender="Me <me@gmail.com>"),
                                           mk(2, NOW - timedelta(hours=2), body="We regret to inform you")]}
        fake = FakeMail({("Google", 3): box}, clock)
        acc = ms.Account("Google", "imap account", "me@gmail.com", "imap.gmail.com", [(3, "[Gmail]/All Mail")])
        returned: set[str] = set()
        res, _ = self.run_once(fake, acc, NOW, budget=1000, returned=returned)
        self.assertEqual([m["message_id"] for m in res.messages], ["m2@acme.test"])
        self.assertEqual(res.messages[0]["snippet"], "We regret to inform you")
        self.assertIn("gmail fallback", res.health[0].method)

    def test_gmail_fallback_reads_all_mail_spam_trash_and_job_labels_first(self):
        acc = ms.Account("Google", "imap account", "me@gmail.com", "imap.gmail.com",
                         [(1, "[Gmail]/Important"), (3, "[Gmail]/All Mail"), (7, "[Gmail]/Spam"), (6, "[Gmail]/Bin"),
                          (5, "[Gmail]/Sent Mail"), (25, "Job"), (24, "Job/Rejections"), (37, "INBOX"), (12, "CFA")])
        src = ms.AppleMailSource([acc], backfill_days=1, budget_s=1, runner=lambda *a: "")
        self.assertEqual([p for _, p in src.selected(acc)],
                         ["Job", "Job/Rejections", "[Gmail]/All Mail", "[Gmail]/Spam", "[Gmail]/Bin"])

    def test_gmail_without_all_mail_in_mail_app_reads_every_folder(self):
        acc = ms.Account("sverma16@stevens.edu", "imap account", "me@school.edu", "imap.gmail.com",
                         [(1, "INBOX"), (2, "[Gmail]/Starred"), (3, "Offers"), (4, "[Gmail]/Spam")])
        src = ms.AppleMailSource([acc], backfill_days=1, budget_s=1, runner=lambda *a: "")
        self.assertEqual(sorted(p for _, p in src.selected(acc)), ["INBOX", "Offers", "[Gmail]/Spam"])

    def test_every_non_system_folder_is_read_for_other_accounts(self):
        acc = exchange({1: "Inbox", 2: "JOB", 3: "JOB/Handshake", 4: "Junk Email", 5: "Deleted Items",
                        6: "Sent Items", 7: "Drafts", 8: "Outbox", 9: "Tasks", 10: "Tasks/SSV", 11: "LinkedIn"})
        src = ms.AppleMailSource([acc], backfill_days=1, budget_s=1, runner=lambda *a: "")
        self.assertEqual(sorted(p for _, p in src.selected(acc)),
                         sorted(["Inbox", "JOB", "JOB/Handshake", "Junk Email", "Deleted Items", "LinkedIn"]))

    def test_enumerate_parses_accounts_and_flat_mailboxes(self):
        raw = ms.RS.join([
            ms.US.join(["A", "Exchange", "account", "me@school.edu", "missing value"]),
            ms.US.join(["M", "1", "Inbox"]), ms.US.join(["M", "40", "JOB/Handshake"]),
            ms.US.join(["A", "Google", "imap account", "me@gmail.com", "imap.gmail.com"]),
            ms.US.join(["M", "3", "[Gmail]/All Mail"]),
        ])
        accs = ms.enumerate_accounts(lambda op, args, t: raw)
        self.assertEqual([(a.name, a.server, a.gmail, a.imap_capable) for a in accs],
                         [("Exchange", "", False, False), ("Google", "imap.gmail.com", True, True)])
        self.assertEqual(accs[0].mailboxes, [(1, "Inbox"), (40, "JOB/Handshake")])


# ── IMAP fake ───────────────────────────────────────────────────────────────

def rfc822(frm, subject, mid, body="Thanks for applying to Acme."):
    return (f"From: {frm}\r\nSubject: {subject}\r\nMessage-ID: <{mid}>\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n\r\n{body}\r\n").encode()


class FakeImap:
    def __init__(self, boxes):
        self.boxes = boxes  # raw name -> {"flags": "\\All", "uidvalidity": 1, "msgs": [dict(uid, date, labels, raw)]}
        self.cur = None
        self.fail_fetch = False
        self.searches = []
        self.untagged = {}

    def login(self, user, pw):
        if pw != "secret":
            raise RuntimeError("AUTHENTICATIONFAILED")
        return "OK", [b"ok"]

    def list(self):
        return "OK", [f'({b["flags"]}) "/" "{name}"'.encode() for name, b in self.boxes.items()]

    def select(self, name, readonly=False):
        self.cur = self.boxes[name.strip('"')]
        uidnext = max([m["uid"] for m in self.cur["msgs"]], default=0) + 1
        self.untagged = {"UIDVALIDITY": [str(self.cur["uidvalidity"]).encode()], "UIDNEXT": [str(uidnext).encode()]}
        return "OK", [str(len(self.cur["msgs"])).encode()]

    def response(self, code):
        return code, self.untagged.pop(code, [None])

    def uid(self, cmd, *args):
        msgs = self.cur["msgs"]
        if cmd == "SEARCH":
            crit = list(args[1:])
            self.searches.append(crit)
            if crit[0] == "UID":
                lo = int(crit[1].split(":")[0])
                hits = [m["uid"] for m in msgs if m["uid"] >= lo] or ([max(m["uid"] for m in msgs)] if msgs else [])
            else:
                since = datetime.strptime(crit[1], "%d-%b-%Y").date()
                before = datetime.strptime(crit[3], "%d-%b-%Y").date() if len(crit) > 3 else None
                hits = [m["uid"] for m in msgs if m["date"].date() >= since and (before is None or m["date"].date() < before)]
            return "OK", [" ".join(map(str, hits)).encode()]
        if cmd == "FETCH":
            if self.fail_fetch:
                return "NO", [b"server error"]
            want = {int(u) for u in args[0].split(",")}
            out = []
            for m in msgs:
                if m["uid"] not in want:
                    continue
                date = m["date"].strftime("%d-%b-%Y %H:%M:%S %z")
                labels = " ".join(f'"{lb}"' for lb in m["labels"])
                if "HEADER.FIELDS" in args[1]:
                    head = m["raw"].split(b"\r\n\r\n")[0] + b"\r\n\r\n"
                    # Labels after the literal, as some servers order them.
                    out.append((f'1 (UID {m["uid"]} INTERNALDATE "{date}" BODY[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID)] {{{len(head)}}}'.encode(), head))
                    out.append(f' X-GM-LABELS ({labels}))'.encode())
                else:
                    out.append((f'1 (UID {m["uid"]} BODY[]<0> {{{len(m["raw"])}}}'.encode(), m["raw"]))
                    out.append(b")")
            return "OK", out
        raise AssertionError(cmd)

    def logout(self):
        return "BYE", []


TZ = timezone(timedelta(hours=-4))


def gmail_boxes(msgs, uidvalidity=1):
    return {"[Gmail]/All Mail": {"flags": "\\HasNoChildren \\All", "uidvalidity": uidvalidity, "msgs": msgs},
            "[Gmail]/Spam": {"flags": "\\HasNoChildren \\Junk", "uidvalidity": 1, "msgs": []},
            "[Gmail]/Sent Mail": {"flags": "\\HasNoChildren \\Sent", "uidvalidity": 1, "msgs": []},
            "INBOX": {"flags": "\\HasNoChildren", "uidvalidity": 1, "msgs": []}}


class ImapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cps = ms.Checkpoints(Path(self.tmp.name) / "cp.json")
        self.acc = ms.Account("Google", "imap account", "me@gmail.com", "imap.gmail.com")
        self.now = datetime(2026, 9, 30, 9, 0, tzinfo=TZ)

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, server, password="secret"):
        return ms.ImapSource([self.acc], backfill_days=30, password_for=lambda a: password, connect=lambda h: server, now=self.now)

    def msg(self, uid, days_ago, labels=("\\Inbox",), frm="Acme <talent@acme.test>", subject=None, body="Thanks for applying"):
        return {"uid": uid, "date": self.now - timedelta(days=days_ago), "labels": list(labels),
                "raw": rfc822(frm, subject or f"Update {uid}", f"m{uid}@acme.test", body)}

    def test_first_run_backfills_window_and_checkpoints(self):
        server = FakeImap(gmail_boxes([self.msg(1, 90), self.msg(2, 10, ("\\Inbox", "Job")), self.msg(3, 1),
                                       self.msg(4, 1, ("\\Sent",), frm="Me <me@gmail.com>")]))
        res = self.source(server).fetch(self.cps, lambda m: True)
        self.assertEqual(sorted(m["message_id"] for m in res.messages), ["m2@acme.test", "m3@acme.test"])
        job = next(m for m in res.messages if m["message_id"] == "m2@acme.test")
        self.assertTrue(job["dedicated"])
        self.assertEqual(job["mailbox"], "Job")
        self.assertEqual(job["snippet"], "Thanks for applying")
        self.assertEqual(self.cps.get("imap:me@gmail.com:[Gmail]/All Mail")["last_uid"], 4)
        self.assertEqual({h.mailbox for h in res.health}, {"[Gmail]/All Mail", "[Gmail]/Spam"})

    def test_late_arriving_old_message_is_still_read(self):
        """The exactness guarantee: UIDs grow even when the message's date is old."""
        msgs = [self.msg(1, 2), self.msg(2, 1)]
        server = FakeImap(gmail_boxes(msgs))
        self.source(server).fetch(self.cps, lambda m: True)
        self.cps.commit()
        msgs.append(self.msg(3, 20))  # delivered late, dated 20 days ago
        res = self.source(server).fetch(self.cps, lambda m: True)
        self.assertEqual([m["message_id"] for m in res.messages], ["m3@acme.test"])

    def test_uidvalidity_change_rescans_window(self):
        msgs = [self.msg(1, 2), self.msg(2, 1)]
        self.source(FakeImap(gmail_boxes(msgs))).fetch(self.cps, lambda m: True)
        self.cps.commit()
        res = self.source(FakeImap(gmail_boxes(msgs, uidvalidity=2))).fetch(self.cps, lambda m: True)
        self.assertEqual(len(res.messages), 2)

    def test_fetch_failure_is_reported_and_not_checkpointed(self):
        server = FakeImap(gmail_boxes([self.msg(1, 1)]))
        server.fail_fetch = True
        res = self.source(server).fetch(self.cps, lambda m: True)
        allmail = next(h for h in res.health if h.mailbox == "[Gmail]/All Mail")
        self.assertEqual(allmail.status, "error")
        self.assertIsNone(self.cps.get("imap:me@gmail.com:[Gmail]/All Mail"))

    def test_missing_password_and_bad_login_are_errors(self):
        res = self.source(FakeImap(gmail_boxes([])), password=None).fetch(self.cps, lambda m: True)
        self.assertIn("no Keychain password", res.health[0].error)
        res = self.source(FakeImap(gmail_boxes([])), password="wrong").fetch(self.cps, lambda m: True)
        self.assertIn("login failed", res.health[0].error)

    def test_longer_backfill_extends_coverage_backwards(self):
        msgs = [self.msg(1, 50), self.msg(2, 1)]
        server = FakeImap(gmail_boxes(msgs))
        self.source(server).fetch(self.cps, lambda m: True)
        self.cps.commit()
        src = ms.ImapSource([self.acc], backfill_days=90, password_for=lambda a: "secret", connect=lambda h: server, now=self.now)
        res = src.fetch(self.cps, lambda m: True)
        self.assertEqual([m["message_id"] for m in res.messages], ["m1@acme.test"])

    def test_gmail_without_all_mail_over_imap_is_an_error(self):
        boxes = gmail_boxes([])
        del boxes["[Gmail]/All Mail"]
        res = self.source(FakeImap(boxes)).fetch(self.cps, lambda m: True)
        self.assertTrue(any("All Mail is not visible" in h.error for h in res.health))

    def test_keep_filter_skips_body_fetch(self):
        server = FakeImap(gmail_boxes([self.msg(1, 1)]))
        res = self.source(server).fetch(self.cps, lambda m: False)
        self.assertEqual(res.messages, [])
        self.assertEqual(self.cps.get("imap:me@gmail.com:[Gmail]/All Mail")["last_uid"], 1)


class HelpersTest(unittest.TestCase):
    def test_parse_list_handles_quotes_and_literals(self):
        rows = ms.parse_list([b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"', b'(\\Noselect) "/" "[Gmail]"',
                              (b'(\\HasNoChildren) "/" {5}', b"Jobs2"), b'(\\HasNoChildren) "/" INBOX'])
        self.assertEqual([(sorted(f), n) for f, n in rows],
                         [(["\\all", "\\hasnochildren"], "[Gmail]/All Mail"), (["\\noselect"], "[Gmail]"),
                          (["\\hasnochildren"], "Jobs2"), (["\\hasnochildren"], "INBOX")])

    def test_imap_utf7_names(self):
        self.assertEqual(ms.imap_utf7_decode("&JxQ-"), "✔")
        self.assertEqual(ms.imap_utf7_decode("Job &- Offers"), "Job & Offers")

    def test_snippet_prefers_plain_text_and_strips_html(self):
        html = (b"Content-Type: text/html\r\n\r\n<html><style>x{}</style><p>We regret&nbsp;to inform you</p></html>")
        self.assertEqual(ms.text_snippet(html), "We regret to inform you")
        self.assertEqual(ms.text_snippet(b"not a mime message at all"), "not a mime message at all")

    def test_dedicated_paths(self):
        self.assertTrue(ms.is_dedicated("JOB/Handshake"))
        self.assertTrue(ms.is_dedicated("Rejections"))
        self.assertFalse(ms.is_dedicated("[Gmail]/All Mail"))

    def test_checkpoints_commit_only_staged(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cp.json"
            c = ms.Checkpoints(p)
            c.stage("k", {"hi": "x"})
            self.assertFalse(p.exists())
            c.commit()
            self.assertEqual(ms.Checkpoints(p).data, {"k": {"hi": "x"}})

    def test_seen_cache_prunes_old_entries(self):
        with tempfile.TemporaryDirectory() as d:
            s = ms.SeenCache(Path(d) / "seen.json", days=30)
            s.add("old@x", "2026-07-01")
            s.add("new@x", "2026-09-29")
            s.save("2026-09-30")
            s2 = ms.SeenCache(Path(d) / "seen.json", days=30)
            self.assertEqual((s2.has("old@x"), s2.has("new@x")), (False, True))


if __name__ == "__main__":
    unittest.main()
