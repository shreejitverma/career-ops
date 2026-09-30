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
        stale = sj.render_review({}, self.trackers, "2026-10-09", root=self.root, health=health)
        self.assertIn("more than two days old", stale)

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

            def fetch(self, cps, keep):
                captured.setdefault(type(self).__name__, []).extend(a.name for a in self.accs)
                captured["keep"] = keep
                return ms.FetchResult()

        Imap = type("ImapSource", (FakeSource,), {})
        Mail = type("AppleMailSource", (FakeSource,), {})
        args = SimpleNamespace(account=None, source="all", backfill_days=30, budget_minutes=1)
        known = {}
        with mock.patch.object(ms, "enumerate_accounts", return_value=accounts), \
             mock.patch.object(ms, "keychain_password", side_effect=lambda a: "pw" if a == "me@gmail.com" else None), \
             mock.patch.object(ms, "ImapSource", Imap), mock.patch.object(ms, "AppleMailSource", Mail), \
             mock.patch.object(ms, "OsaRunner", lambda: None):
            with tempfile.TemporaryDirectory() as d:
                sj.fetch_messages(args, known, ms.Checkpoints(Path(d) / "c.json"), ms.SeenCache(Path(d) / "s.json"), self.trackers)
        self.assertEqual(captured["ImapSource"], ["Google"])
        self.assertEqual(captured["AppleMailSource"], ["Personal", "Exchange"])
        keep = captured["keep"]
        base = {"account": "Google", "mailbox": "INBOX", "date": "2026-09-20", "snippet": "", "dedicated": False}
        self.assertFalse(keep(base | {"subject": "[me/x] Run failed", "sender": "notifications@github.com", "message_id": "a"}))
        self.assertFalse(keep(base | {"subject": "Your Uber receipt", "sender": "uber@uber.com", "message_id": "b"}))
        self.assertTrue(keep(base | {"subject": "Your order interview slot", "sender": "x@y.com", "message_id": "c", "dedicated": True}))
        self.assertTrue(keep(base | {"subject": "Hello", "sender": "friend@example.com", "message_id": "d"}))
        self.assertFalse(keep(base | {"subject": "Hello", "sender": "friend@example.com", "message_id": "d"}))  # once per run
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
