"""Behavior tests for pipeline_views.py."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pipeline_views as pv  # noqa: E402


def tracker(company, stage, reached="", source="LinkedIn", track="[quant-dev]", reason=""):
    return (f"---\ncompany: {company}\nstage: {stage}\nreached: {reached}\nsource: {source}\n"
            f"track: {track}\nrejection_reason: {reason}\n---\n\n# {company}\n")


class ViewsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for i, args in enumerate([("A", "onsite"), ("B", "rejected", "phone", "Referral", "[sde]", "bar"),
                                  ("C", "applied"), ("D", "ghosted", "", "Referral")]):
            d = self.root / ("Archive" if args[1] in pv.TERMINAL else "Active") / args[0]
            d.mkdir(parents=True)
            (d / f"{args[0]}-Tracker.md").write_text(tracker(*args))
        self.apps = pv.load(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, text, first_cell):
        return next(l for l in text.splitlines() if l.startswith(f"| {first_cell} |"))

    def test_funnel_uses_furthest_stage(self):
        text = pv.stats(self.apps)
        self.assertIn("| phone | 2 |", text)   # A (onsite) and B (rejected after phone)
        self.assertIn("| onsite | 1 |", text)
        self.assertIn("| applied | 4 |", text)

    def test_response_rate_counts_rejections_not_silence(self):
        text = pv.stats(self.apps).split("## Response rate by source")[1]
        self.assertEqual(self.row(text, "Referral"), "| Referral | 2 | 1 | 50% |")  # B rejected, D ghosted

    def test_withdrawn_without_reply_is_not_a_response(self):
        d = self.root / "Archive" / "E"
        d.mkdir(parents=True)
        (d / "E-Tracker.md").write_text(tracker("E", "withdrawn", "", "Direct"))
        text = pv.stats(pv.load(self.root)).split("## Response rate by source")[1]
        self.assertEqual(self.row(text, "Direct"), "| Direct | 1 | 0 | 0% |")

    def test_rejection_reasons_listed(self):
        text = pv.stats(self.apps).split("## Rejection reasons")[1]
        self.assertIn("| [[B-Tracker]] | phone | bar |", text)

    def test_board_has_every_stage_and_card(self):
        text = pv.board(self.apps)
        for s in pv.STAGES:
            self.assertIn(f"## {s}\n", text)
        self.assertIn("## onsite\n\n- [ ] [[A-Tracker]]", text)
        self.assertIn("kanban-plugin: board", text)


if __name__ == "__main__":
    unittest.main()
