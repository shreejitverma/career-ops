"""Behavior tests for normalize_trackers.py."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import normalize_trackers as nt  # noqa: E402

OLD = """---
company: "DRW"
role: "FICC Desk Tools Developer"
stage: "Interview"
status: "Interview Loop Completed / Awaiting Feedback"
track: "Quant-Dev / Market Data"
priority: "P1"
confidence: "Medium"
date_applied: 2026-07-20
next_deadline: 2026-09-25
salary_range: "$220,000 - $280,000"
stakeholders:
  - name: "A Person"
    role: "Recruiter"
tags:
  - active-pipeline
---

# DRW
"""


class NormalizeTest(unittest.TestCase):
    def setUp(self):
        self.new, self.notes = nt.normalize(OLD)
        self.fm = self.new.split("\n---\n", 1)[0]

    def test_canonical_values(self):
        for line in ("stage: onsite", "priority: high", "confidence: 3", "track: [quant-dev]", 'focus: Market Data',
                     "applied: 2026-07-20", "next_action_date: 2026-09-25", 'comp_band: "$220,000 - $280,000"',
                     "referrer:", "links: []"):
            self.assertIn(line + "\n", self.fm + "\n")

    def test_nested_blocks_preserved(self):
        self.assertIn('stakeholders:\n  - name: "A Person"\n    role: "Recruiter"\ntags:\n  - active-pipeline', self.new)
        self.assertTrue(self.new.endswith("\n# DRW\n"))

    def test_idempotent(self):
        again, notes = nt.normalize(self.new)
        self.assertEqual(again, self.new)
        self.assertEqual(notes, [])

    def test_phone_when_status_is_not_a_loop(self):
        new, _ = nt.normalize(OLD.replace("Interview Loop Completed / Awaiting Feedback", "Interview Scheduled"))
        self.assertIn("stage: phone\n", new)

    def test_unknown_stage_left_alone(self):
        new, notes = nt.normalize(OLD.replace('stage: "Interview"', "stage: mystery"))
        self.assertIn("stage: mystery\n", new)
        self.assertTrue(any("not recognized" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
