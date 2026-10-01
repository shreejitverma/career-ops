"""Behavior tests for mail_sources.py: python3 -m unittest discover -s command-center/03-Pipeline/tests

The core property is "nothing is missed": over any sequence of runs, however the
time budget cuts them, the messages returned cover every message in the window,
and a checkpoint never claims coverage of something that was not returned.
"""

import random
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mail_sources as ms  # noqa: E402
import sync_job_emails as sj  # noqa: E402

NOW = datetime(2026, 9, 30, 9, 0, 0)


# ── Apple Mail fake ──────────────────────────────────────────────────────────

class FakeMail:
    """Emulates the scan / scanfrom / content AppleScripts over newest-first lists.
    Every call and every message read costs clock time, and the scripts' time
    limits are checked against that clock, so budgets bite as they do for real."""

    def __init__(self, boxes, clock, cost_per_call=1.0, cost_per_msg=0.5, account_cost=None):
        self.boxes = boxes  # {(account, index): {"name": str, "msgs": [(datetime, subject, sender, mid, body)]}}
        self.clock = clock
        self.cost_per_call, self.cost_per_msg = cost_per_call, cost_per_msg
        self.account_cost = account_cost or {}  # account -> cost per message read, overriding cost_per_msg
        self.now = NOW
        self.calls = []
        self.scan_orders = []        # mailbox indexes of each scan call, in the order requested
        self.bodies = Counter()      # message id -> times its body was fetched
        self.fail_content = set()    # (account, index) whose content calls fail
        self.after_chunk = None      # callable(op, msgs) run after every chunk read; may change msgs

    def _msgs(self, acc, ix):
        box = self.boxes[(acc, int(ix))]
        box["msgs"].sort(key=lambda m: m[0], reverse=True)
        return box

    def _row(self, ix, pos, m):
        return ms.US.join(["R", str(ix), str(pos), m[0].isoformat(), m[1], m[2], m[3]])

    def _age(self, m):
        return (self.now - m[0]).total_seconds()

    def _cost(self, acc):
        return self.account_cost.get(acc, self.cost_per_msg)

    def __call__(self, op, args, timeout):
        self.calls.append(op)
        self.clock.t += self.cost_per_call
        start = self.clock.t
        out = []
        if op == "check":
            return "ok"
        if op == "scan":
            acc, limit, ovl = args[0], int(args[2]), int(args[4])
            specs = [r.split(ms.US) for r in args[1].split(ms.RS) if r]
            self.scan_orders.append([int(spec[0]) for spec in specs])
            for spec in specs:
                ix, name, stop_age = int(spec[0]), spec[1], int(spec[2])
                box = self._msgs(acc, ix)
                if box["name"] != name:
                    out.append(ms.US.join(["E", str(ix), f"mailbox moved: expected {name}, found {box['name']}"]))
                    continue
                msgs = box["msgs"]
                n = len(msgs)
                out.append(ms.US.join(["B", str(ix), str(n)]))
                pos, size = 1, min(25, int(args[3]))
                while True:
                    if len(msgs) != n:
                        n = len(msgs)
                        out.append(ms.US.join(["B", str(ix), str(n)]))
                    if pos > n:
                        break
                    if self.clock.t - start > limit:
                        out.append(ms.US.join(["T", str(ix), str(pos)]))
                        return ms.RS.join(out)
                    end = min(n, pos + size - 1)
                    rows = msgs[pos - 1:end]
                    self.clock.t += self._cost(acc) * len(rows)
                    out += [self._row(ix, pos + k, m) for k, m in enumerate(rows)]
                    if self.after_chunk:
                        self.after_chunk(op, msgs)
                    if self._age(rows[-1]) > stop_age:
                        break
                    pos, size = self._next(pos, end, n, ovl), min(size * 2, int(args[3]))
                out.append(ms.US.join(["D", str(ix)]))
            return ms.RS.join(out)
        box = self._msgs(args[0], args[1])
        if box["name"] != args[2]:
            raise ms.MailError(f"{op}: mailbox moved: expected {args[2]}, found {box['name']}")
        msgs = box["msgs"]
        n = len(msgs)
        if op == "scanfrom":
            from_age, to_age, limit, ovl = int(args[3]), int(args[4]), int(args[5]), int(args[7])
            out.append(ms.US.join(["B", str(args[1]), str(n)]))
            lo, hi = 1, n + 1
            while lo < hi:
                mid = (lo + hi) // 2
                self.clock.t += self._cost(args[0])
                if self._age(msgs[mid - 1]) > from_age:
                    hi = mid
                else:
                    lo = mid + 1
            pos = max(1, lo - 1)
            while True:
                if len(msgs) != n:
                    n = len(msgs)
                    out.append(ms.US.join(["B", str(args[1]), str(n)]))
                if pos > n:
                    break
                if self.clock.t - start > limit:
                    out.append(ms.US.join(["T", str(args[1]), str(pos)]))
                    return ms.RS.join(out)
                end = min(n, pos + int(args[6]) - 1)
                rows = msgs[pos - 1:end]
                self.clock.t += self._cost(args[0]) * len(rows)
                out += [self._row(args[1], pos + k, m) for k, m in enumerate(rows)]
                if self.after_chunk:
                    self.after_chunk(op, msgs)
                if self._age(rows[-1]) > to_age:
                    break
                pos = self._next(pos, end, n, ovl)
            out.append(ms.US.join(["D", str(args[1])]))
            return ms.RS.join(out)
        if op == "content":
            if (args[0], int(args[1])) in self.fail_content:
                raise ms.MailError("content: timed out after 600s")
            by_mid = {m[3].lower(): m for m in msgs}
            for pair in [r.split(ms.US) for r in args[3].split(ms.RS) if r]:
                m = by_mid.get(pair[1].lower())
                self.bodies[pair[1].lower()] += 1
                out.append(ms.US.join([pair[1], m[4] if m else "!notfound"]))
            return ms.RS.join(out)
        raise AssertionError(op)

    @staticmethod
    def _next(pos, end, n, ovl):
        """The scripts' next chunk start: `ovl` positions back, always moving forward."""
        if end >= n:
            return end + 1
        return max(end + 1 - ovl, pos + 1)


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
        """One run over one account, or a list of accounts."""
        cps = ms.Checkpoints(self.cps_path)
        delivered = set()

        # As in sync_job_emails.RunFilter: skip anything already handled, including
        # earlier in this run (backfill overlaps the new-mail pass).
        def keep(m):
            return m["message_id"] not in returned and m["message_id"] not in delivered

        fake.now = now
        src = ms.AppleMailSource(acc if isinstance(acc, list) else [acc], backfill_days=backfill, budget_s=budget,
                                 runner=fake, now=now, clock=fake.clock)
        res = src.fetch(cps, keep, lambda m: delivered.add(m["message_id"]))
        cps.commit()
        got = [m["message_id"] for m in res.messages]
        for mid in got:
            self.assertNotIn(mid, returned, "a message was returned twice")
            returned.add(mid)
        return res, cps

    def assert_honest(self, boxes_by_key, returned):
        """A checkpoint claims (lo, hi] minus its gaps; every message there must have been returned."""
        data = ms.Checkpoints(self.cps_path).data
        for key, msgs in boxes_by_key.items():
            cp = data.get(key) or {}
            if not cp.get("hi"):
                continue
            for m in msgs:
                t = m[0].isoformat()
                if cp["lo"] < t <= cp["hi"] and not any(lo <= t <= hi for lo, hi in cp.get("gaps") or []):
                    self.assertIn(ms.clean_mid(m[3]), returned, f"{key} claims {t}, which was never returned")

    def test_reads_everything_in_window_and_nothing_twice(self):
        clock = Clock()
        msgs = [mk(i, NOW - timedelta(hours=7 * i)) for i in range(200)]  # ~58 days
        fake = FakeMail({("Exchange", 1): {"name": "Inbox", "msgs": list(msgs)}}, clock)
        returned: set[str] = set()
        self.run_once(fake, exchange({1: "Inbox"}), NOW, budget=10_000, returned=returned)
        want = {ms.clean_mid(m[3]) for m in msgs if m[0] >= NOW - timedelta(days=30)}
        self.assertTrue(want <= returned, f"missed {sorted(want - returned)[:5]}")
        cp = ms.Checkpoints(self.cps_path).data
        self.assertEqual(cp["mail:Exchange:Inbox"]["hi"], NOW.isoformat())

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
                self.assert_honest({"mail:Exchange:JOB": box["msgs"]}, returned)
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
        cp = ms.Checkpoints(self.cps_path).data["mail:Exchange:Inbox"]
        lo = datetime.fromisoformat(cp["lo"])
        covered = {ms.clean_mid(m[3]) for m in msgs if m[0] >= lo and m[0] <= NOW}
        self.assertTrue(covered <= returned, "checkpoint claims coverage of messages that were not returned")
        self.assertEqual(res.health[0].status, "partial")

    def test_budget_cut_in_new_pass_records_the_unread_stretch_and_fills_it(self):
        clock = Clock()
        box = {"name": "Inbox", "msgs": [mk(i, NOW - timedelta(hours=6 * i)) for i in range(40)]}
        fake = FakeMail({("Exchange", 1): box}, clock, cost_per_msg=1.0)
        acc, key, returned = exchange({1: "Inbox"}), "mail:Exchange:Inbox", set()
        self.run_once(fake, acc, NOW, budget=10_000, returned=returned)
        # Three weeks away: far more new mail than one run's budget can read.
        later = NOW + timedelta(days=21)
        box["msgs"] += [mk(1000 + i, later - timedelta(minutes=30 * i)) for i in range(1000)]
        res, _ = self.run_once(fake, acc, later, budget=120, returned=returned)
        cp = ms.Checkpoints(self.cps_path).data[key]
        self.assertEqual(res.health[0].status, "partial")
        self.assertEqual(cp["hi"], later.isoformat())
        [(gap_lo, gap_hi)] = cp["gaps"]
        self.assertEqual(gap_lo, (NOW - ms.OVERLAP).isoformat())
        self.assert_honest({key: box["msgs"]}, returned)
        unread = [m for m in box["msgs"] if ms.clean_mid(m[3]) not in returned]
        self.assertTrue(unread)
        self.assertTrue(all(gap_lo <= m[0].isoformat() <= gap_hi for m in unread))
        # The next run reads the stretch; no body is fetched twice.
        res, _ = self.run_once(fake, acc, later + timedelta(hours=12), budget=100_000, returned=returned)
        self.assertEqual(res.health[0].status, "ok")
        self.assertEqual(ms.Checkpoints(self.cps_path).data[key]["gaps"], [])
        self.assertTrue({ms.clean_mid(m[3]) for m in box["msgs"]} <= returned)
        self.assertEqual(max(fake.bodies.values()), 1)

    def test_long_absence_converges_without_rereading_property(self):
        """Weeks of mail arrive while the machine is off, then every run has a tiny budget:
        the unread stretches still close, every message in the window is returned exactly
        once, no body is fetched twice, and no checkpoint ever claims unread mail."""
        rng = random.Random(20261001)
        for trial in range(12):
            clock = Clock()
            boxes = {"mail:Exchange:JOB": {"name": "JOB", "msgs": []}, "mail:Exchange:Inbox": {"name": "Inbox", "msgs": []}}
            fake = FakeMail({("Exchange", 2): boxes["mail:Exchange:JOB"], ("Exchange", 1): boxes["mail:Exchange:Inbox"]},
                            clock, cost_per_msg=rng.choice([0.05, 0.1, 0.2]))
            acc = exchange({1: "Inbox", 2: "JOB"})
            self.cps_path = Path(self.tmp.name) / f"absence-{trial}.json"
            returned: set[str] = set()
            seq = iter(range(10**6))
            now = NOW

            def arrive(days, per_day, now, boxes=boxes, seq=seq, trial=trial):
                for b in boxes.values():
                    for _ in range(int(days * per_day)):
                        b["msgs"].append(mk(f"{trial}-{next(seq)}", now - timedelta(minutes=rng.randint(0, int(days * 1440)))))

            arrive(10, 20, now)
            for _ in range(3):
                self.run_once(fake, acc, now, budget=10_000, returned=returned)
                now += timedelta(days=1)
                arrive(1, 20, now)
            away = rng.choice([14, 21, 28])
            now += timedelta(days=away)
            arrive(away, rng.choice([40, 80]), now)
            for run in range(200):
                self.run_once(fake, acc, now, budget=rng.choice([60, 120, 250]), returned=returned)
                self.assert_honest({k: b["msgs"] for k, b in boxes.items()}, returned)
                if all(ms.clean_mid(m[3]) in returned for b in boxes.values() for m in b["msgs"]):
                    break
                now += timedelta(hours=rng.choice([12, 24]))
                arrive(0.5, 10, now)
            missed = [m for b in boxes.values() for m in b["msgs"] if ms.clean_mid(m[3]) not in returned]
            self.assertEqual(missed, [], f"trial {trial}: {len(missed)} never returned after {run + 1} runs")
            self.assertLessEqual(max(fake.bodies.values()), 1, f"trial {trial}: a body was fetched twice")

    def test_mailbox_partial_for_three_runs_becomes_an_error(self):
        clock = Clock()
        box = {"name": "Inbox", "msgs": []}
        fake = FakeMail({("Exchange", 1): box}, clock, cost_per_msg=1.0)
        acc, returned, statuses, now = exchange({1: "Inbox"}), set(), [], NOW
        for run in range(3):
            box["msgs"] += [mk(f"{run}-{i}", now - timedelta(minutes=i)) for i in range(200)]
            res, _ = self.run_once(fake, acc, now, budget=5, returned=returned)
            statuses.append(res.health[0].status)
            now += timedelta(hours=1)
        self.assertEqual(statuses, ["partial", "partial", "error"])
        self.assertIn("still partial after 3 runs", res.health[0].error)
        res, _ = self.run_once(fake, acc, now, budget=100_000, returned=returned)
        self.assertEqual(res.health[0].status, "ok")
        self.assertEqual(ms.Checkpoints(self.cps_path).data["mail:Exchange:Inbox"]["partial_runs"], 0)

    def test_slow_gmail_new_mail_cannot_starve_backfill_and_backfill_in_progress_is_ok(self):
        """Live failure: the Gmail-fallback accounts' new mail took every run's whole budget,
        so no other mailbox ever backfilled, and every backfilling mailbox was escalated to
        an error after three runs."""
        clock = Clock()
        inbox = {"name": "Inbox", "msgs": [mk(f"x{i}", NOW - timedelta(minutes=15 * i)) for i in range(2800)]}
        all_mail = {"name": "All Mail", "msgs": []}
        fake = FakeMail({("Exchange", 1): inbox, ("Google", 3): all_mail}, clock,
                        account_cost={"Exchange": 0.05, "Google": 2.0})
        accs = [exchange({1: "Inbox"}),
                ms.Account("Google", "imap account", "me@gmail.com", "imap.gmail.com", [(3, "[Gmail]/All Mail")])]
        returned, now, los = set(), NOW, []
        for run in range(5):
            # Far more new Gmail than a run can read through Mail.app.
            all_mail["msgs"] += [mk(f"g{run}-{i}", now - timedelta(minutes=5 * i)) for i in range(300)]
            res, _ = self.run_once(fake, accs, now, budget=300, returned=returned)
            ex = next(h for h in res.health if h.account == "Exchange")
            los.append(ms.Checkpoints(self.cps_path).data["mail:Exchange:Inbox"]["lo"])
            self.assertEqual((ex.status, ex.error), ("ok", ""), f"run {run}")
            self.assertEqual(ex.target, (NOW - timedelta(days=30)).date().isoformat())
            now += timedelta(hours=1)
        self.assertEqual(los, sorted(los, reverse=True))
        self.assertEqual(len(set(los)), 5, "the fast account's backfill moved back on every run")
        self.assertGreater(los[-1][:10], ex.target, "still in progress, so the test covers runs 3-5")
        google = next(h for h in res.health if h.account == "Google")
        self.assertEqual(google.status, "error")  # its new mail never finished: a real problem, still loud
        self.assertIn("app password", google.error)

    def test_fast_backlog_and_slow_daily_mail_both_converge_property(self):
        """A fast account with a large backlog and a slow Gmail-fallback account with steady
        daily mail, randomized small budgets: the slow account's new mail is read on every
        run, the fast account's backfill moves back on every run until it reaches the target,
        no mailbox is reported failed meanwhile, and every message in the window of both
        accounts is returned exactly once."""
        rng = random.Random(20261003)
        for trial in range(10):
            clock = Clock()
            boxes = {"mail:Exchange:Inbox": {"name": "Inbox", "msgs": []}, "mail:Exchange:JOB": {"name": "JOB", "msgs": []},
                     "mail:Google:[Gmail]/All Mail": {"name": "All Mail", "msgs": []}}
            fake = FakeMail({("Exchange", 1): boxes["mail:Exchange:Inbox"], ("Exchange", 2): boxes["mail:Exchange:JOB"],
                             ("Google", 3): boxes["mail:Google:[Gmail]/All Mail"]}, clock,
                            account_cost={"Exchange": rng.choice([0.02, 0.05]), "Google": rng.choice([0.5, 1.0])})
            accs = [exchange({1: "Inbox", 2: "JOB"}),
                    ms.Account("Google", "imap account", "me@gmail.com", "imap.gmail.com", [(3, "[Gmail]/All Mail")])]
            fast_keys = ["mail:Exchange:Inbox", "mail:Exchange:JOB"]
            slow = boxes["mail:Google:[Gmail]/All Mail"]
            self.cps_path = Path(self.tmp.name) / f"mixed-{trial}.json"
            seq = iter(range(10**6))
            target = (NOW - timedelta(days=30)).isoformat()

            def arrive(box, days, per_day, now, seq=seq, trial=trial):
                new = [mk(f"{trial}-{next(seq)}", now - timedelta(minutes=rng.randint(0, int(days * 1440))))
                       for _ in range(int(days * per_day))]
                box["msgs"] += new
                return new

            for key in fast_keys:  # a backlog many runs deep
                arrive(boxes[key], 40, rng.choice([60, 100]), NOW)
            arrive(slow, 40, 8, NOW)
            returned: set[str] = set()
            now = NOW
            for run in range(40):
                fresh = arrive(slow, 1, 8, now) if run else []
                before = ms.Checkpoints(self.cps_path).data
                behind = [k for k in fast_keys if before.get(k, {}).get("lo", "9") > before.get(k, {}).get("target", "")]
                res, _ = self.run_once(fake, accs, now, budget=rng.choice([150, 250, 400]), returned=returned)
                after = ms.Checkpoints(self.cps_path).data
                self.assert_honest({k: b["msgs"] for k, b in boxes.items()}, returned)
                self.assertEqual([h for h in res.health if h.status == "error"], [], f"trial {trial} run {run}")
                self.assertTrue({ms.clean_mid(m[3]) for m in fresh} <= returned, f"trial {trial} run {run}: slow new mail starved")
                if run and behind:
                    self.assertTrue(any(after[k]["lo"] < before[k]["lo"] for k in behind),
                                    f"trial {trial} run {run}: fast backfill made no progress")
                now += timedelta(days=1)
            want = {ms.clean_mid(m[3]) for b in boxes.values() for m in b["msgs"] if m[0].isoformat() >= target}
            self.assertEqual(want - returned, set(), f"trial {trial}: not converged after 40 runs")
            self.assertTrue(all(after[k]["lo"] == after[k]["target"] for k in boxes))

    def test_scan_cut_short_starts_at_the_mailbox_it_stopped_in(self):
        clock = Clock()
        fake = FakeMail({("Exchange", 1): {"name": "Inbox", "msgs": [mk(f"a{i}", NOW - timedelta(minutes=i)) for i in range(10)]},
                         ("Exchange", 2): {"name": "Archive", "msgs": [mk(f"b{i}", NOW - timedelta(minutes=i)) for i in range(500)]},
                         ("Exchange", 3): {"name": "Other", "msgs": [mk(f"c{i}", NOW - timedelta(minutes=i)) for i in range(5)]}}, clock)
        acc, returned = exchange({1: "Inbox", 2: "Archive", 3: "Other"}), set()
        res, _ = self.run_once(fake, acc, NOW, budget=100, returned=returned)
        other = next(h for h in res.health if h.mailbox == "Other")
        self.assertEqual((other.status, other.error), ("partial", "not reached before the time budget ran out; read first next run"))
        self.run_once(fake, acc, NOW + timedelta(hours=1), budget=100_000, returned=returned)
        self.assertEqual(fake.scan_orders, [[1, 2, 3], [2, 3, 1]])
        self.assertEqual(len(returned), 515)

    def test_job_label_scanned_first_even_when_rotated(self):
        acc = exchange({1: "Inbox", 2: "Archive", 9: "JOB"})
        cps = ms.Checkpoints(self.cps_path)
        cps.stage("rotation:Exchange", {"start": 2})
        src = ms.AppleMailSource([acc], backfill_days=1, budget_s=1, runner=lambda *a: "")
        mine = [(i, p, None) for i, p in src.selected(acc)]
        self.assertEqual(src.scan_order(acc, mine, cps), [(9, "JOB"), (2, "Archive"), (1, "Inbox")])

    def test_failing_job_label_does_not_hide_its_message_from_all_mail(self):
        clock = Clock()
        shared = mk(1, NOW - timedelta(hours=1))
        fake = FakeMail({("Google", 25): {"name": "Job", "msgs": [shared]},
                         ("Google", 3): {"name": "All Mail", "msgs": [shared, mk(2, NOW - timedelta(hours=2))]}}, clock)
        fake.fail_content.add(("Google", 25))
        acc = ms.Account("Google", "imap account", "me@gmail.com", "imap.gmail.com", [(25, "Job"), (3, "[Gmail]/All Mail")])
        flt = sj.RunFilter({"me@gmail.com"}, {}, ms.SeenCache(Path(self.tmp.name) / "seen.json"))
        src = ms.AppleMailSource([acc], backfill_days=30, budget_s=1000, runner=fake, now=NOW, clock=clock)
        res = src.fetch(ms.Checkpoints(self.cps_path), flt.keep, flt.sunk)
        self.assertEqual(sorted(m["message_id"] for m in res.messages), ["m1@acme.test", "m2@acme.test"])
        self.assertEqual(next(h for h in res.health if h.mailbox == "Job").status, "error")

    def test_messages_deleted_between_chunks_do_not_push_one_past_the_cursor(self):
        for op, n, spacing in (("scan", 100, timedelta(minutes=20)), ("scanfrom", 600, timedelta(hours=1))):
            with self.subTest(op=op):
                clock = Clock()
                msgs = [mk(f"{op}{i}", NOW - spacing * i) for i in range(n)]
                fake = FakeMail({("Exchange", 1): {"name": "Inbox", "msgs": list(msgs)}}, clock)
                deleted = []

                def delete_newest_two(call, box, op=op, deleted=deleted):
                    if call == op and not deleted:
                        deleted += box[:2]
                        del box[:2]

                fake.after_chunk = delete_newest_two
                self.cps_path = Path(self.tmp.name) / f"del-{op}.json"
                returned: set[str] = set()
                self.run_once(fake, exchange({1: "Inbox"}), NOW, budget=100_000, returned=returned)
                self.assertEqual(len(deleted), 2)
                self.assertEqual({ms.clean_mid(m[3]) for m in msgs} - returned, set())

    def test_slow_accounts_take_turns_when_the_budget_fits_only_one(self):
        """Live failure: with several Gmail-fallback accounts and a small budget, the first
        one read its new mail every run and the others were never reached."""
        clock = Clock()
        boxes, accs = {}, []
        for k, name in enumerate(["G1", "G2", "G3"]):
            boxes[(name, 3)] = {"name": "All Mail", "msgs": [mk(1000 * k + i, NOW - timedelta(hours=i)) for i in range(40)]}
            accs.append(ms.Account(name, "imap account", f"{name.lower()}@gmail.com", "imap.gmail.com", [(3, "[Gmail]/All Mail")]))
        fake = FakeMail(boxes, clock, cost_per_msg=1.0)
        reached = {a.name: 0 for a in accs}
        returned: set[str] = set()
        now = NOW
        for run in range(6):
            cps = ms.Checkpoints(self.cps_path)
            seen = set(returned)

            def keep(m):
                if m["message_id"] in seen:
                    return False
                seen.add(m["message_id"])
                return True

            fake.now = now
            res = ms.AppleMailSource(accs, backfill_days=1, budget_s=70, runner=fake, now=now, clock=fake.clock).fetch(cps, keep)
            cps.commit()
            for m in res.messages:
                returned.add(m["message_id"])
                reached[m["account"]] += 1
            now += timedelta(hours=1)
        self.assertTrue(all(n > 0 for n in reached.values()), reached)

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
        cp = ms.Checkpoints(self.cps_path).data["mail:Exchange:Trading Challenge"]
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
            ms.US.join(["A", "iCloud", "iCloud account", "me@icloud.com", "p42-imap.mail.me.com"]),
            ms.US.join(["M", "1", "INBOX"]),
        ])
        accs = ms.enumerate_accounts(lambda op, args, t: raw)
        self.assertEqual([(a.name, a.server, a.gmail, a.imap_capable) for a in accs],
                         [("Exchange", "", False, False), ("Google", "imap.gmail.com", True, True),
                          ("iCloud", "p42-imap.mail.me.com", False, True)])
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

    def test_localized_all_mail_is_found_by_its_flag(self):
        boxes = gmail_boxes([self.msg(1, 1)])
        boxes["[Gmail]/Todos"] = boxes.pop("[Gmail]/All Mail")
        res = self.source(FakeImap(boxes)).fetch(self.cps, lambda m: True)
        self.assertEqual([h.status for h in res.health], ["ok", "ok"])
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


class OsaRunnerTest(unittest.TestCase):
    def test_mail_crash_is_recovered_with_one_relaunch_and_retry(self):
        from types import SimpleNamespace as NS
        calls = []
        replies = iter([NS(returncode=1, stdout="", stderr="execution error: Application isn\u2019t running. (-600)"),
                        NS(returncode=0, stdout="", stderr=""),            # open -g -a Mail
                        NS(returncode=1, stdout="", stderr="not yet"),     # Mail still starting
                        NS(returncode=0, stdout="9", stderr=""),           # Mail answers
                        NS(returncode=0, stdout="rows\n", stderr="")])    # retried call
        def run(cmd, **kw):
            calls.append(cmd[:3])
            return next(replies)
        r = ms.OsaRunner(run=run, sleep=lambda s: None)
        self.assertEqual(r("scan", ["Google", "x", 10, 25, 5], 60), "rows")
        self.assertEqual([c[0] for c in calls], ["osascript", "open", "osascript", "osascript", "osascript"])

    def test_other_errors_are_not_retried(self):
        from types import SimpleNamespace as NS
        calls = []
        def run(cmd, **kw):
            calls.append(cmd)
            return NS(returncode=1, stdout="", stderr="mailbox moved: expected Inbox, found X")
        with self.assertRaises(ms.MailError):
            ms.OsaRunner(run=run, sleep=lambda s: None)("scanfrom", ["Exchange", 1, "Inbox", 1, 2, 3, 25, 5], 60)
        self.assertEqual(len(calls), 1)


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

    def test_corrupt_state_is_moved_aside_and_reported(self):
        with tempfile.TemporaryDirectory() as d:
            for cls, name, text in ((ms.Checkpoints, "checkpoints.json", '{"mail:x": {"hi"'), (ms.SeenCache, "seen.json", "[]")):
                p = Path(d) / name
                p.write_text(text)
                state = cls(p)
                self.assertEqual(state.data, {})
                self.assertIn(f"moved to {name}.corrupt-", state.problem)
                self.assertFalse(p.exists())
                [aside] = list(Path(d).glob(f"{name}.corrupt-*"))
                self.assertEqual(aside.read_text(), text)
            self.assertEqual(ms.Checkpoints(Path(d) / "missing.json").problem, "")

    def test_dry_run_reports_corrupt_state_but_leaves_it_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "checkpoints.json"
            p.write_text("{truncated")
            state = ms.Checkpoints(p, dry_run=True)
            self.assertEqual(state.data, {})
            self.assertIn("left in place", state.problem)
            self.assertEqual(p.read_text(), "{truncated")
            self.assertEqual(list(Path(d).glob("*.corrupt*")), [])

    def test_a_second_corruption_never_overwrites_the_first_copy(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "seen.json"
            for text in ("[1]", "[2]"):
                p.write_text(text)
                ms.SeenCache(p)
            copies = sorted(x.read_text() for x in Path(d).glob("seen.json.corrupt-*"))
            self.assertEqual(copies, ["[1]", "[2]"])

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
