"""Behavior tests for sync_job_emails.py: python3 -m unittest discover -s command-center/03-Pipeline/tests"""

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
        by_domain = sj.match_tracker(msg("Hello", "Talent <talent@acmecap.com>"), self.trackers)
        by_name = sj.match_tracker(msg("Your Acme Capital application", "no-reply@greenhouse.io"), self.trackers)
        self.assertEqual(by_domain.company, "Acme Capital")
        self.assertEqual(by_name.company, "Acme Capital")
        self.assertIsNone(sj.match_tracker(msg("Hello", "someone@other.com"), self.trackers))

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

    def test_apple_mail_date_parsing(self):
        self.assertEqual(sj.parse_date("Friday, August 28, 2026 at 1:00:10 PM"), "2026-08-28")
        self.assertEqual(sj.parse_date("2026-09-20"), "2026-09-20")

    def test_shared_ats_domain_does_not_match_tracker_holding_it(self):
        other = self.root / "Active" / "Falcon" / "Falcon-Tracker.md"
        other.parent.mkdir(parents=True)
        other.write_text("---\ncompany: FalconX\nstage: applied\nrecruiter_email: no-reply@us.greenhouse-mail.io\n---\n")
        trackers = sj.load_trackers(self.root)
        by_name = sj.match_tracker(msg("Your Acme Capital application", "no-reply@us.greenhouse-mail.io"), trackers)
        self.assertEqual(by_name.company, "Acme Capital")
        self.assertIsNone(sj.match_tracker(msg("Your application", "no-reply@us.greenhouse-mail.io"), trackers))

    def test_name_match_respects_word_boundaries(self):
        (self.root / "Active" / "Talan").mkdir(parents=True)
        (self.root / "Active" / "Talan" / "Talan-Tracker.md").write_text("---\ncompany: Talan\nstage: applied\n---\n")
        trackers = sj.load_trackers(self.root)
        self.assertIsNone(sj.match_tracker(msg("Catalan conference", "x@y.com"), trackers))
        self.assertEqual(sj.match_tracker(msg("Talan interview", "x@y.com"), trackers).company, "Talan")
        self.assertEqual(sj.match_tracker(msg("Update", "careers@acmecapital.com"), trackers).company, "Acme Capital")

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

    def test_legacy_event_ids_load_and_dedupe(self):
        events_file = self.root / ".sync" / "events.jsonl"
        e = sj.to_event(msg("Phone screen with Acme Capital", "talent@acmecap.com"), self.trackers, self.root)
        legacy = sj.Event(**(e.__dict__ | {"id": "legacy000000", "date": "Sunday, September 20, 2026 at 9:00:00\u202fAM"}))
        events_file.parent.mkdir(parents=True)
        events_file.write_text(legacy.to_json() + "\n")
        loaded = sj.load_events(events_file)
        self.assertEqual(loaded["legacy000000"].date, "2026-09-20")
        self.assertEqual(sj.record([e], events_file), [])

    def test_excluded_newsletters(self):
        self.assertFalse(sj.is_job_related(msg("Weekly digest: jobs you may like", "alerts@x.com")))
        self.assertTrue(sj.is_job_related(msg("Anything", "x@y.com", mailbox="Rejections") | {"dedicated": True}))


if __name__ == "__main__":
    unittest.main()
