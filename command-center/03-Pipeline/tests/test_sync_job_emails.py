"""Behavior tests for sync_job_emails.py: python3 -m unittest discover -s command-center/03-Pipeline/tests"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sync_job_emails as sj  # noqa: E402

TRACKER = """---
company: Acme Capital
role: Quant Developer
stage: applied
recruiter_email: talent@acmecap.com
---

# Acme Capital tracker

## Notes

Hand-written notes.
"""


def norm_dir(company):
    return "".join(c for c in company if c.isalnum())


def msg(subject, sender, date="2026-09-20", snippet="", mailbox="INBOX"):
    return {"account": "Test", "mailbox": mailbox, "subject": subject, "sender": sender, "date": date, "snippet": snippet}


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "Active" / "Acme").mkdir(parents=True)
        self.tracker = self.root / "Active" / "Acme" / "Acme-Tracker.md"
        self.tracker.write_text(TRACKER)
        self.trackers = sj.load_trackers(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_classify_priority(self):
        self.assertEqual(sj.classify(msg("Your offer letter", "x@y.com")), "offer")
        self.assertEqual(sj.classify(msg("Update", "x@y.com", snippet="we regret to inform you")), "rejection")
        self.assertEqual(sj.classify(msg("HackerRank assessment for your interview", "x@y.com")), "assessment")
        self.assertEqual(sj.classify(msg("Superday invitation", "x@y.com")), "interview")
        self.assertEqual(sj.suggest_stage("interview", "Superday invitation"), "onsite")
        self.assertEqual(sj.suggest_stage("interview", "Phone screen"), "phone")

    def test_match_by_domain_and_name(self):
        by_domain, how_domain = sj.match_tracker(msg("Hello", "Talent <talent@acmecap.com>"), self.trackers)
        by_name, how_name = sj.match_tracker(msg("Your Acme Capital application", "no-reply@greenhouse.io"), self.trackers)
        self.assertEqual((by_domain.company, how_domain), ("Acme Capital", "domain"))
        self.assertEqual((by_name.company, how_name), ("Acme Capital", "name"))
        self.assertEqual(sj.match_tracker(msg("Hello", "someone@other.com"), self.trackers), (None, None))

    def test_noise_dropped_even_from_dedicated_mailboxes(self):
        noisy = [
            msg("[me/airflow] Run failed: Tests - main (b5d9259)", "notifications@github.com"),
            msg("TECH CONNECT: Hot Tech Jobs, Career Insights & More", "The Experis Team <knowledge@experis.com>"),
            msg("Senior Python Developer at X. 4 more python developer jobs in Delhi", "Indeed <donotreply@jobalert.indeed.com>"),
            msg("OMS Professional Branding Webinar TOMORROW", "gatech@csm.symplicity.com"),
            msg("Save 20% on GMAT Prep", "Manhattan Prep <info@manhattanprep.com>"),
            msg("Weekly Career Center Webinars and Events for OMS Students", "Graduate Career Development <gcd@gatech.edu>"),
        ]
        for m in noisy:
            m["dedicated"] = True
            self.assertFalse(sj.is_job_related(m), m["subject"])
        real = msg("Update on Your Application for Quantitative Analyst", "no-reply@us.greenhouse-mail.io",
                   snippet="Unfortunately, we will not be moving forward")
        real["dedicated"] = True
        self.assertTrue(sj.is_job_related(real))

    def test_review_hides_previously_recorded_noise(self):
        noise = sj.to_event(msg("Apply for an easier monthly payment", "Prodigy Finance <payments@notifications.prodigyfinance.com>",
                                snippet="assessment"), self.trackers, self.root)
        real = sj.to_event(msg("Thank you for your time and interest", "WellsFargoHR <wf@wellsfargo.com>",
                               snippet="we regret to inform you"), self.trackers, self.root)
        review = sj.render_review({noise.id: noise, real.id: real}, self.trackers, "2026-09-21", root=self.root)
        self.assertNotIn("monthly payment", review)
        untracked = review.split("## Possible untracked applications")[1].split("## Last")[0]
        self.assertIn("Thank you for your time and interest", untracked)

    def test_untracked_looks_back_further_than_activity(self):
        old = sj.to_event(msg("Application Update - Senior Quantitative Developer", "TIAA@myworkday.com", date="2026-08-01",
                              snippet="we regret to inform you"), self.trackers, self.root)
        review = sj.render_review({old.id: old}, self.trackers, "2026-09-29", root=self.root)
        untracked = review.split("## Possible untracked applications")[1].split("## Last")[0]
        self.assertIn("Senior Quantitative Developer", untracked)
        self.assertNotIn("Senior Quantitative Developer", review.split("## Last")[1])

    def test_ats_senders_and_tracker_names_are_job_mail_without_keywords(self):
        self.assertTrue(sj.is_job_related(msg("Quick question", "no-reply@myworkdayjobs.com")))
        self.assertTrue(sj.is_job_related(msg("Catching up", "Jane <jane@codesignal.com>")))
        # The tracker's recruiter domain is enough; the company's name alone is not (bank statements).
        self.assertTrue(sj.is_job_related(msg("Catching up", "Talent <talent@acmecap.com>"), self.trackers))
        self.assertFalse(sj.is_job_related(msg("Your Acme Capital statement is ready", "alerts@acme-bank.com"), self.trackers))
        self.assertTrue(sj.is_job_related(msg("Your application was sent to Acme", "LinkedIn <jobs-noreply@linkedin.com>")))
        self.assertFalse(sj.is_job_related(msg("Someone viewed your profile", "LinkedIn <notifications-noreply@linkedin.com>")))
        # Bulk mail still loses, even from a platform domain.
        self.assertFalse(sj.is_job_related(msg("Weekly digest", "digest@myworkdayjobs.com")))

    def test_body_words_never_exclude_a_message(self):
        recruiter = msg("Quant Developer role", "Dana <dana@talentbridge.test>",
                        snippet="Hi, in order to submit you to the client I need your right to represent by Friday.")
        self.assertTrue(sj.is_job_related(recruiter))
        self.assertFalse(sj.is_job_related(msg("Your order has shipped", "shop@store.test", snippet="interview")))

    def test_message_id_makes_one_event_across_sources(self):
        a = msg("Interview invitation", "talent@acmecap.com") | {"message_id": "<ABC@acmecap.com>", "account": "Google"}
        b = a | {"message_id": "abc@acmecap.com", "mailbox": "All Mail", "date": "Monday, September 21, 2026 at 9:00:00 AM"}
        self.assertEqual(sj.event_id(a), sj.event_id(b))
        events_file = self.root / ".sync" / "events.jsonl"
        fresh = sj.record([sj.to_event(a, self.trackers, self.root), sj.to_event(b, self.trackers, self.root)], events_file)
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0].message_id, "abc@acmecap.com")

    def test_legacy_event_absorbs_exactly_one_reread(self):
        events_file = self.root / ".sync" / "events.jsonl"
        legacy = sj.to_event(msg("Application update", "no-reply@acmecap.com", date="2026-09-21"), self.trackers, self.root)
        sj.record([legacy], events_file)
        first = msg("Application update", "Acme <no-reply@acmecap.com>", date="2026-09-21") | {"message_id": "one@acme"}
        second = first | {"message_id": "two@acme"}
        fresh = sj.record([sj.to_event(m, self.trackers, self.root) for m in (first, second)], events_file)
        # One of the two re-read messages is the one recorded before; the other is new.
        self.assertEqual(len(fresh), 1)

    def test_legacy_absorption_is_written_down_and_holds_across_runs(self):
        events_file = self.root / ".sync" / "events.jsonl"
        other = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com", date="2026-09-20"), self.trackers, self.root)
        legacy = sj.to_event(msg("Application update", "no-reply@acmecap.com", date="2026-09-21"), self.trackers, self.root)
        sj.record([other, legacy], events_file)
        raw_dated = {**json.loads(other.to_json()), "id": "legacy000000", "date": "Sunday, September 20, 2026 at 9:00:00\u202fAM"}
        with events_file.open("a") as f:
            f.write(json.dumps(raw_dated) + "\n")
        before = events_file.read_text().splitlines(keepends=True)
        a = msg("Application update", "Acme <no-reply@acmecap.com>", date="2026-09-21") | {"message_id": "a@acme"}
        b = a | {"message_id": "b@acme"}
        # Run 1: A is the message recorded before; its Message-ID is written onto that event.
        self.assertEqual(sj.record([sj.to_event(a, self.trackers, self.root)], events_file), [])
        after = events_file.read_text().splitlines(keepends=True)
        self.assertEqual([after[0], after[2]], [before[0], before[2]])
        self.assertEqual(json.loads(after[1]), json.loads(before[1]) | {"message_id": "a@acme"})
        self.assertEqual(sj.load_events(events_file)[legacy.id].message_id, "a@acme")
        # Run 2: B shares A's day, subject and sender but is a different message.
        fresh = sj.record([sj.to_event(b, self.trackers, self.root)], events_file)
        self.assertEqual([e.message_id for e in fresh], ["b@acme"])
        # A read again later is already handled, by record() and by the run's filter.
        self.assertEqual(sj.record([sj.to_event(a, self.trackers, self.root)], events_file), [])
        with tempfile.TemporaryDirectory() as d:
            import mail_sources as ms
            flt = sj.RunFilter(set(), sj.load_events(events_file), ms.SeenCache(Path(d) / "s.json"), self.trackers)
        self.assertFalse(flt.keep(a | {"dedicated": False}))

    def test_review_reports_sync_health(self):
        health = {"finished_at": "2026-09-30T09:10:00", "mailboxes": [
            {"account": "Exchange", "mailbox": "Inbox", "method": "mail", "status": "ok", "read": 10, "kept": 2, "error": ""},
            {"account": "Google", "mailbox": "[Gmail]/All Mail", "method": "mail (gmail fallback)", "status": "partial",
             "read": 50, "kept": 5, "error": "time budget reached; continues next run"},
            {"account": "iCloud", "mailbox": "INBOX", "method": "imap", "status": "error", "read": 0, "kept": 0,
             "error": "login failed: AUTHENTICATIONFAILED"},
        ]}
        review = sj.render_review({}, self.trackers, "2026-09-30", root=self.root, health=health)
        section = review.split("## Sync health")[1].split("## Needs attention")[0]
        self.assertIn("3 mailboxes in 3 accounts", section)
        self.assertIn("| iCloud | INBOX | login failed: AUTHENTICATIONFAILED |", section)
        self.assertIn("Google/[Gmail]/All Mail", section)
        self.assertIn("app password", section)
        self.assertNotIn("Every mailbox read completely", section)
        stale = sj.render_review({}, self.trackers, "2026-10-09", root=self.root, health=health)
        self.assertIn("more than two days old", stale)

    def test_review_lists_mailboxes_with_unavailable_bodies(self):
        health = {"finished_at": "2026-09-30T09:10:00", "mailboxes": [
            {"account": "Exchange", "mailbox": "Inbox", "method": "mail", "status": "ok", "read": 10, "kept": 4, "unavailable": 3,
             "error": "some message bodies were unavailable; classified from subject and sender"},
            {"account": "Exchange", "mailbox": "JOB", "method": "mail", "status": "ok", "read": 5, "kept": 1, "error": ""},
        ]}
        section = sj.render_review({}, self.trackers, "2026-09-30", root=self.root, health=health).split("## Sync health")[1]
        section = section.split("## Needs attention")[0]
        self.assertIn("- Exchange/Inbox: 3 message(s)", section)
        self.assertNotIn("Exchange/JOB", section)
        self.assertNotIn("Every mailbox read completely", section)

    def test_review_reports_backfill_in_progress_once_per_account_and_not_as_a_failure(self):
        health = {"finished_at": "2026-09-30T09:10:00", "mailboxes": [
            {"account": "Exchange", "mailbox": "Inbox", "method": "mail", "status": "ok", "read": 10, "kept": 2, "error": "",
             "covered_from": "2026-08-20", "covered_to": "2026-09-30", "target": "2026-04-03"},
            {"account": "Exchange", "mailbox": "JOB", "method": "mail", "status": "ok", "read": 5, "kept": 1, "error": "",
             "covered_from": "2026-07-01", "covered_to": "2026-09-30", "target": "2026-04-03"},
            {"account": "Exchange", "mailbox": "Junk", "method": "mail", "status": "ok", "read": 1, "kept": 0, "error": "",
             "covered_from": "2026-04-03", "covered_to": "2026-09-30", "target": "2026-04-03"},
            {"account": "Google", "mailbox": "INBOX", "method": "imap", "status": "ok", "read": 3, "kept": 0, "error": "",
             "covered_from": "2026-04-03", "covered_to": "2026-09-30"},
        ]}
        section = sj.render_review({}, self.trackers, "2026-09-30", root=self.root, health=health).split("## Sync health")[1]
        section = section.split("## Needs attention")[0]
        self.assertEqual([ln for ln in section.splitlines() if "backfill in progress" in ln],
                         ["- backfill in progress: Exchange covered back to 2026-08-20, target 2026-04-03"])
        self.assertNotIn("failed", section)
        self.assertNotIn("Every mailbox read completely", section)

    def test_recruiter_body_phrasing_is_a_recruiter_signal(self):
        cv = msg("Quick question about your CV", "Dana <dana@talentbridge.test>",
                 snippet="Hi, in order to submit you to our client for the C++ position I need a few details.")
        self.assertEqual(sj.classify(cv), "recruiter")
        for body in ("I am writing on behalf of my client, a trading firm.",
                     "We have a role with our client in Chicago.",
                     "I came across your resume and wanted to connect."):
            self.assertEqual(sj.classify(msg("Hello", "dana@talentbridge.test", snippet=body)), "recruiter", body)
        e = sj.to_event(cv, self.trackers, self.root)
        review = sj.render_review({e.id: e}, self.trackers, "2026-09-21", root=self.root)
        self.assertIn("Quick question about your CV", review.split("## Possible untracked applications")[1].split("## Last")[0])

    def test_review_lists_every_unmatched_other_job_email_from_the_last_14_days(self):
        recent = sj.to_event(msg("Following up", "Sam <sam@unknown-firm.test>", date="2026-09-20", mailbox="JOB"),
                             self.trackers, self.root)
        older = sj.to_event(msg("Earlier note", "Kim <kim@unknown-firm.test>", date="2026-09-01", mailbox="JOB"),
                            self.trackers, self.root)
        self.assertEqual((recent.signal, recent.tracker, older.signal), ("other", None, "other"))
        review = sj.render_review({recent.id: recent, older.id: older}, self.trackers, "2026-09-28", root=self.root)
        other = review.split("## Other job email (last 14 days)")[1]
        self.assertIn("| 2026-09-20 | Sam <sam@unknown-firm.test> | Following up |", other)
        self.assertNotIn("Earlier note", other)
        empty = sj.render_review({older.id: older}, self.trackers, "2026-09-28", root=self.root)
        self.assertEqual(empty.split("## Other job email (last 14 days)")[1].strip(), "None.")

    def test_fetch_routes_accounts_and_keep_rules(self):
        from types import SimpleNamespace
        from unittest import mock
        import mail_sources as ms
        accounts = [ms.Account("Google", "imap account", "me@gmail.com", "imap.gmail.com"),
                    ms.Account("Personal", "imap account", "p@gmail.com", "imap.gmail.com"),
                    ms.Account("Exchange", "account", "me@school.edu", "")]
        captured = {}

        class FakeSource:
            def __init__(self, accs, **kw):
                self.accs = accs

            def fetch(self, cps, keep, sunk):
                captured.setdefault(type(self).__name__, []).extend(a.name for a in self.accs)
                captured["keep"], captured["sunk"] = keep, sunk
                return ms.FetchResult(health=[ms.Health(a.name, "INBOX", "fake") for a in self.accs])

        Imap = type("ImapSource", (FakeSource,), {})
        Mail = type("AppleMailSource", (FakeSource,), {})
        accounts.append(ms.Account("iCloud", "iCloud account", "me@icloud.com", "p42-imap.mail.me.com"))
        args = SimpleNamespace(backfill_days=30, budget_minutes=1)
        known = {}
        with mock.patch.object(ms, "enumerate_accounts", return_value=accounts), \
             mock.patch.object(ms, "keychain_password", side_effect=lambda a: "pw" if a in ("me@gmail.com", "me@icloud.com") else None), \
             mock.patch.object(ms, "ImapSource", Imap), mock.patch.object(ms, "AppleMailSource", Mail), \
             mock.patch.object(ms, "OsaRunner", lambda: None):
            with tempfile.TemporaryDirectory() as d:
                sj.fetch_messages(args, known, ms.Checkpoints(Path(d) / "c.json"), ms.SeenCache(Path(d) / "s.json"), self.trackers)
        self.assertEqual(captured["ImapSource"], ["Google", "iCloud"])
        self.assertEqual(captured["AppleMailSource"], ["Personal", "Exchange"])
        keep, sunk = captured["keep"], captured["sunk"]
        base = {"account": "Google", "mailbox": "INBOX", "date": "2026-09-20", "snippet": "", "dedicated": False}
        self.assertFalse(keep(base | {"subject": "[me/x] Run failed", "sender": "notifications@github.com", "message_id": "a"}))
        self.assertFalse(keep(base | {"subject": "Your Uber receipt", "sender": "uber@uber.com", "message_id": "b"}))
        self.assertTrue(keep(base | {"subject": "Your order interview slot", "sender": "x@y.com", "message_id": "c", "dedicated": True}))
        hello = base | {"subject": "Hello", "sender": "friend@example.com", "message_id": "d"}
        self.assertTrue(keep(hello))
        self.assertTrue(keep(hello))  # read but not delivered (its mailbox failed): another mailbox may deliver it
        sunk(hello)
        self.assertFalse(keep(hello))  # delivered once per run
        self.assertFalse(keep(base | {"subject": "Re: Interview", "sender": "Me <p@gmail.com>", "message_id": "e"}))  # own address

    def test_body_signals_need_job_phrasing(self):
        news = msg("Amazon drones are overwhelming a Texas suburb", "The Paper <news@paper.test>",
                   snippet="In an interview, residents described the noise. A risk assessment followed.")
        self.assertEqual(sj.classify(news), "other")
        self.assertEqual(sj.classify(msg("Next steps", "t@acme.test", snippet="We would like to schedule an interview with you")), "interview")
        self.assertEqual(sj.classify(msg("Next steps", "t@acme.test", snippet="Please complete the online assessment by Friday")), "assessment")
        self.assertEqual(sj.classify(msg("Interview availability", "t@acme.test")), "interview")
        self.assertEqual(sj.classify(msg("Hello", "t@acme.test", snippet="There is a great opportunity in our town square")), "other")
        thread = msg("Re: SIG / Susquehanna International Group - Bala Cynwyd", "Recruiter <j@agency.test>",
                     snippet="Thanks for the call, I will share your profile with the team.")
        self.assertEqual(sj.classify(thread), "reply")
        review = sj.render_review({sj.to_event(thread, self.trackers, self.root).id: sj.to_event(thread, self.trackers, self.root)},
                                  self.trackers, "2026-09-21", root=self.root)
        self.assertIn("Re: SIG / Susquehanna", review.split("## Possible untracked applications")[1].split("## Last")[0])
        self.assertTrue(sj.is_noise("Arrested Mid-Interview", "WSJ <access@interactive.wsj.com>"))
        self.assertTrue(sj.is_noise("COPA Weekly Event Schedule", "COPA <copa@school.edu>"))

    def run_main(self, fetch, argv=("--notify",)):
        """main() against a temporary state directory, no trackers, and fetch_messages replaced."""
        import contextlib
        import io
        from unittest import mock
        state = self.root / ".sync"
        state.mkdir(exist_ok=True)
        notes = []
        with mock.patch.multiple(sj, EVENTS=state / "events.jsonl", CHECKPOINTS=state / "checkpoints.json",
                                 SEEN=state / "seen.json", HEALTH=state / "health.json",
                                 REVIEW=self.root / "_Inbox-Review.md", load_trackers=list,
                                 fetch_messages=fetch, notify=notes.append), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = sj.main([*argv, "--today", "2026-09-30"])
        return code, notes, state

    def test_a_run_that_cannot_read_mail_is_loud(self):
        def broken(*a, **k):
            raise RuntimeError("Mail automation is not allowed")

        code, notes, state = self.run_main(broken)
        self.assertEqual(code, 2)
        self.assertEqual(len(notes), 1)
        [row] = json.loads((state / "health.json").read_text())["mailboxes"]
        self.assertEqual((row["account"], row["status"]), ("all accounts", "error"))
        self.assertIn("Mail automation is not allowed", row["error"])
        review = (self.root / "_Inbox-Review.md").read_text()
        self.assertIn("Mail automation is not allowed", review.split("## Sync health")[1].split("## Needs attention")[0])

    def test_mail_reporting_no_accounts_or_mailboxes_is_loud(self):
        import mail_sources as ms
        from unittest import mock
        fetch = sj.fetch_messages
        no_accounts = ""
        no_mailboxes = ms.US.join(["A", "Exchange", "account", "me@school.edu", "missing value"])
        for answer, expected in ((no_accounts, "no accounts"), (no_mailboxes, "no mailboxes")):
            with self.subTest(expected), mock.patch.object(ms, "OsaRunner", lambda: lambda op, args, t: answer):
                code, notes, state = self.run_main(fetch)
                self.assertEqual(code, 2)
                self.assertEqual(len(notes), 1)
                [row] = json.loads((state / "health.json").read_text())["mailboxes"]
                self.assertEqual((row["account"], row["status"]), ("all accounts", "error"))
                self.assertIn(expected, row["error"])
                review = (self.root / "_Inbox-Review.md").read_text()
                self.assertNotIn("Every mailbox read completely", review)

    def test_corrupt_state_file_is_reported_as_an_error(self):
        import mail_sources as ms
        (self.root / ".sync").mkdir()
        (self.root / ".sync" / "checkpoints.json").write_text("{truncated")
        code, notes, state = self.run_main(lambda *a, **k: ms.FetchResult())
        self.assertEqual(code, 2)
        self.assertTrue((state / "checkpoints.json.corrupt").exists())
        rows = json.loads((state / "health.json").read_text())["mailboxes"]
        self.assertEqual([(r["mailbox"], r["status"]) for r in rows], [("checkpoints.json", "error")])
        self.assertEqual(len(notes), 1)

    def test_bodiless_message_is_not_marked_seen_unless_recorded(self):
        import mail_sources as ms
        base = {"account": "Exchange", "mailbox": "Inbox", "date": "2026-09-29", "snippet": "", "dedicated": False,
                "body_unavailable": True}
        unrecorded = base | {"subject": "Hello", "sender": "friend@example.com", "message_id": "x@friend"}
        recorded = base | {"subject": "Interview invitation", "sender": "talent@acmecap.com", "message_id": "y@acme"}
        whole = base | {"subject": "Lunch", "sender": "friend@example.com", "message_id": "z@friend", "body_unavailable": False}
        code, _, state = self.run_main(lambda *a, **k: ms.FetchResult(messages=[unrecorded, recorded, whole]), argv=())
        self.assertEqual(code, 0)
        seen = ms.SeenCache(state / "seen.json")
        self.assertEqual([seen.has(m) for m in ("x@friend", "y@acme", "z@friend")], [False, True, True])

    def test_record_is_idempotent(self):
        events_file = self.root / ".sync" / "events.jsonl"
        e = [sj.to_event(msg("Interview invitation from Acme Capital", "talent@acmecap.com"), self.trackers, self.root)]
        self.assertEqual(len(sj.record(e, events_file)), 1)
        self.assertEqual(len(sj.record(e, events_file)), 0)
        self.assertEqual(len(sj.load_events(events_file)), 1)

    def test_review_flags_stage_disagreement(self):
        e = sj.to_event(msg("Unfortunately, we will not be moving forward", "talent@acmecap.com"), self.trackers, self.root)
        review = sj.render_review({e.id: e}, self.trackers, "2026-09-21", root=self.root)
        attention = review.split("## Needs attention")[1].split("## Last")[0]
        self.assertIn("[[Acme-Tracker]]", attention)
        self.assertIn("rejected", attention)

    def test_timeline_appended_once_and_frontmatter_untouched(self):
        e = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com"), self.trackers, self.root)
        self.assertEqual(sj.apply_timeline([e], self.root), 1)
        self.assertEqual(sj.apply_timeline([e], self.root), 0)
        text = self.tracker.read_text()
        self.assertEqual(text.count(f"evt:{e.id}"), 1)
        self.assertTrue(text.startswith(TRACKER.split("# Acme")[0]))  # frontmatter byte-identical
        self.assertIn("Hand-written notes.", text)

    def test_timeline_inserts_into_existing_section(self):
        self.tracker.write_text(TRACKER.replace("## Notes", "## Timeline\n\n- 2026-09-01 applied: portal\n\n## Notes"))
        e = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com"), self.trackers, self.root)
        sj.apply_timeline([e], self.root)
        text = self.tracker.read_text()
        timeline = text.split("## Timeline")[1].split("## Notes")[0]
        self.assertIn("2026-09-01 applied", timeline)
        self.assertIn(f"evt:{e.id}", timeline)

    def test_dry_run_writes_nothing(self):
        e = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com"), self.trackers, self.root)
        before = self.tracker.read_text()
        self.assertEqual(sj.apply_timeline([e], self.root, dry_run=True), 1)
        self.assertEqual(self.tracker.read_text(), before)
        events_file = self.root / ".sync" / "events.jsonl"
        sj.record([e], events_file, dry_run=True)
        self.assertFalse(events_file.exists())

    def test_review_lists_untracked_companies(self):
        e = sj.to_event(msg("Interview invitation", "careers@othercorp.com"), self.trackers, self.root)
        review = sj.render_review({e.id: e}, self.trackers, "2026-09-21", root=self.root)
        self.assertIn("careers@othercorp.com", review.split("## Possible untracked applications")[1].split("## Last")[0])

    def test_alias_matches_short_company_name(self):
        self.tracker.write_text(TRACKER.replace("company: Acme Capital", "company: Acme Capital Investments\naliases: [Acme Capital, AcmeCap]"))
        trackers = sj.load_trackers(self.root)
        t, how = sj.match_tracker(msg("Follow Up to Your AcmeCap Application", "no-reply@greenhouse.io"), trackers)
        self.assertEqual((t.company, how), ("Acme Capital Investments", "name"))

    def test_block_form_aliases_match(self):
        self.tracker.write_text(TRACKER.replace(
            "company: Acme Capital", "company: Acme Capital Investments\naliases:\n  - Acme Capital\n  - \"AcmeCap\""))
        trackers = sj.load_trackers(self.root)
        t, how = sj.match_tracker(msg("Follow Up to Your AcmeCap Application", "no-reply@greenhouse.io"), trackers)
        self.assertEqual((t.company, how, t.aliases), ("Acme Capital Investments", "name", ["Acme Capital", "AcmeCap"]))

    def test_apple_mail_date_parsing(self):
        self.assertEqual(sj.parse_date("Friday, August 28, 2026 at 1:00:10 PM"), "2026-08-28")
        self.assertEqual(sj.parse_date("2026-09-20"), "2026-09-20")

    def test_shared_ats_domain_does_not_match_tracker_holding_it(self):
        other = self.root / "Active" / "Falcon" / "Falcon-Tracker.md"
        other.parent.mkdir(parents=True)
        other.write_text("---\ncompany: FalconX\nstage: applied\nrecruiter_email: no-reply@us.greenhouse-mail.io\n---\n")
        trackers = sj.load_trackers(self.root)
        by_name, _ = sj.match_tracker(msg("Your Acme Capital application", "no-reply@us.greenhouse-mail.io"), trackers)
        self.assertEqual(by_name.company, "Acme Capital")
        self.assertEqual(sj.match_tracker(msg("Your application", "no-reply@us.greenhouse-mail.io"), trackers), (None, None))

    def test_name_match_respects_word_boundaries(self):
        (self.root / "Active" / "Talan").mkdir(parents=True)
        (self.root / "Active" / "Talan" / "Talan-Tracker.md").write_text("---\ncompany: Talan\nstage: applied\n---\n")
        trackers = sj.load_trackers(self.root)
        self.assertEqual(sj.match_tracker(msg("Catalan conference", "x@y.com"), trackers), (None, None))
        self.assertEqual(sj.match_tracker(msg("Talan interview", "x@y.com"), trackers)[0].company, "Talan")
        self.assertEqual(sj.match_tracker(msg("Update", "careers@acmecapital.com"), trackers)[0].company, "Acme Capital")

    def test_name_match_ignores_punctuation_for_long_names(self):
        for company, subject in (("ATT-Labs", "Interview at AT&T Labs"), ("D. E. Shaw", "D.E. Shaw phone screen")):
            d = self.root / "Active" / norm_dir(company)
            d.mkdir(parents=True)
            (d / f"{norm_dir(company)}-Tracker.md").write_text(f"---\ncompany: {company}\nstage: applied\n---\n")
            t, how = sj.match_tracker(msg(subject, "x@y.com"), sj.load_trackers(self.root))
            self.assertEqual((t.company, how), (company, "name"))
        (self.root / "Active" / "HRT").mkdir(parents=True)
        (self.root / "Active" / "HRT" / "HRT-Tracker.md").write_text("---\ncompany: HRT\nstage: applied\n---\n")
        self.assertEqual(sj.match_tracker(msg("Thrtle update", "x@y.com"), sj.load_trackers(self.root)), (None, None))

    def test_agency_domain_match_is_reviewed_but_not_appended(self):
        e = sj.to_event(msg("Interview: C++ Developer at Citadel", "talent@acmecap.com"), self.trackers, self.root)
        self.assertEqual(e.match, "domain")
        before = self.tracker.read_text()
        self.assertEqual(sj.apply_timeline([e], self.root), 0)
        self.assertEqual(self.tracker.read_text(), before)
        review = sj.render_review({e.id: e}, self.trackers, "2026-09-21", root=self.root)
        self.assertIn("[[Acme-Tracker]] (domain match, check)", review)

    def test_same_day_same_subject_messages_are_both_recorded(self):
        events_file = self.root / ".sync" / "events.jsonl"
        first = msg("Re: Interview Confirmation - Acme Capital", "talent@acmecap.com",
                    date="Monday, September 21, 2026 at 9:00:00\u202fAM")
        second = first | {"date": "Monday, September 21, 2026 at 3:00:00\u202fPM"}
        events = [sj.to_event(m, self.trackers, self.root) for m in (first, second)]
        self.assertEqual(len(sj.record(events, events_file)), 2)
        self.assertEqual(sj.apply_timeline(list(sj.load_events(events_file).values()), self.root), 2)

    def test_apple_mail_date_with_narrow_no_break_space(self):
        self.assertEqual(sj.parse_date("Monday, September 21, 2026 at 8:00:45\u202fPM"), "2026-09-21")
        self.assertEqual(sj.parse_date("Monday, September 21, 2026 at 8:00:45\u00a0PM"), "2026-09-21")

    def test_review_ignores_unparsed_dates(self):
        e = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com", date="sometime"), self.trackers, self.root)
        review = sj.render_review({e.id: e}, self.trackers, "2026-09-21", root=self.root)
        self.assertNotIn("Phone screen", review)

    def test_moved_tracker_is_followed_and_missing_is_skipped(self):
        e = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com"), self.trackers, self.root)
        moved = self.root / "Archive" / "Acme" / "Acme-Tracker.md"
        moved.parent.mkdir(parents=True)
        self.tracker.rename(moved)
        self.assertEqual(sj.apply_timeline([e], self.root), 1)
        self.assertIn(f"evt:{e.id}", moved.read_text())
        review = sj.render_review({e.id: e}, sj.load_trackers(self.root), "2026-09-21", root=self.root)
        self.assertIn("[[Acme-Tracker]]", review.split("## Needs attention")[1].split("## Possible")[0])
        moved.unlink()
        self.assertEqual(sj.apply_timeline([e], self.root), 0)

    def test_same_message_in_two_mailboxes_is_one_event(self):
        events_file = self.root / ".sync" / "events.jsonl"
        a = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com", mailbox="Work"), self.trackers, self.root)
        b = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com", mailbox="INBOX"), self.trackers, self.root)
        self.assertEqual(a.id, b.id)
        self.assertEqual(len(sj.record([a, b], events_file)), 1)

    def test_recorded_events_with_raw_dates_load_as_iso(self):
        events_file = self.root / ".sync" / "events.jsonl"
        e = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com"), self.trackers, self.root)
        old = {k: v for k, v in e.__dict__.items() if k != "match"}
        old |= {"id": "legacy000000", "date": "Sunday, September 20, 2026 at 9:00:00\u202fAM"}
        events_file.parent.mkdir(parents=True)
        events_file.write_text(json.dumps(old) + "\n")
        self.assertEqual(sj.load_events(events_file)["legacy000000"].date, "2026-09-20")

    def test_excluded_newsletters(self):
        self.assertFalse(sj.is_job_related(msg("Weekly digest: jobs you may like", "alerts@x.com")))
        self.assertTrue(sj.is_job_related(msg("Anything", "x@y.com", mailbox="Rejections") | {"dedicated": True}))


if __name__ == "__main__":
    unittest.main()
