#!/usr/bin/env python3
"""Normalize application tracker frontmatter to the schema in _Application-Schema.md.

Only top-level keys are touched; nested blocks (for example a stakeholders list)
are copied byte for byte. Values that are already canonical are left alone, so
the script is idempotent.

- renames: date_applied -> applied, next_deadline -> next_action_date,
  salary_range -> comp_band, referral -> source
- stage: mapped onto the canonical stages, using the free-text `status` field to
  tell a phone screen from an onsite loop when the old stage just says "Interview"
- priority: P1/P2/P3 -> high/medium/low; confidence: High/Medium/Low -> 4/3/2
- track: free text -> list of canonical tracks; other words go to `focus`;
  a missing track is inferred from the role and reported
- adds empty `referrer:` and `links: []` when missing

Usage:
    normalize_trackers.py            # dry run: print every change
    normalize_trackers.py --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
TRACKER_DIRS = ("Active", "Archive")
RENAMES = {"date_applied": "applied", "next_deadline": "next_action_date", "salary_range": "comp_band", "referral": "source"}
STAGES = ["sourced", "applied", "recruiter", "OA", "phone", "onsite", "offer", "rejected", "withdrawn", "ghosted"]
STAGE_MAP = {
    "rejected": "rejected", "applied": "applied", "technical-assessment": "OA", "recruiter-screen": "recruiter",
    "final round": "onsite", "offer": "offer", "withdrawn": "withdrawn", "ghosted": "ghosted",
    "oa": "OA", "phone": "phone", "onsite": "onsite", "recruiter": "recruiter", "sourced": "sourced",
}
ONSITE_STATUS = re.compile(r"onsite|on-site|loop|final|superday", re.I)
PRIORITY_MAP = {"p0": "high", "p1": "high", "p2": "medium", "p3": "low", "high": "high", "medium": "medium", "low": "low"}
CONFIDENCE_MAP = {"very high": "5", "high": "4", "medium": "3", "low": "2", "very low": "1"}
TRACK_WORDS = {
    "quant-dev": "quant-dev", "quant dev": "quant-dev", "quant-research": "quant-research", "quant research": "quant-research",
    "low-latency": "low-latency", "low latency": "low-latency", "ai-engineer": "ai-eng", "ai engineer": "ai-eng",
    "sde": "sde", "distributed systems": "sde", "software": "sde",
}
ROLE_HINTS = [
    (re.compile(r"quant(itative)?[ -]?research|researcher|\bqr\b", re.I), "quant-research"),
    (re.compile(r"quant(itative)?[ -]?dev|strats|\bfrtb\b|risk", re.I), "quant-dev"),
    (re.compile(r"c\+\+|cpp|low[ -]latency|market data|hft|fpga", re.I), "low-latency"),
    (re.compile(r"\b(ai|ml|llm|machine learning)\b", re.I), "ai-eng"),
    (re.compile(r"software|engineer|developer|distributed", re.I), "sde"),
]


def split(text: str) -> tuple[list[str], str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    return text[4:end].split("\n"), text[end + 1:]


def top_level(lines: list[str]) -> list[tuple[str | None, list[str]]]:
    """Group frontmatter into (key, lines) blocks; nested lines stay with their key."""
    blocks: list[tuple[str | None, list[str]]] = []
    for line in lines:
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", line)
        if m:
            blocks.append((m.group(1), [line]))
        elif blocks:
            blocks[-1][1].append(line)
        else:
            blocks.append((None, [line]))
    return blocks


def scalar(block: list[str]) -> str:
    return block[0].split(":", 1)[1].strip().strip('"').strip("'")


def quote(v: str) -> str:
    return f'"{v}"' if re.search(r"[:#\[\]{}&*!|>'\"%@`]", v) or v != v.strip() else v


def normalize(text: str) -> tuple[str, list[str]]:
    parsed = split(text)
    if parsed is None:
        return text, []
    fm, body = parsed
    blocks = top_level(fm)
    keys = {k: b for k, b in blocks if k}
    notes: list[str] = []
    out: list[tuple[str | None, list[str]]] = []
    status = scalar(keys["status"]) if "status" in keys else ""
    for key, block in blocks:
        if key in RENAMES and RENAMES[key] not in keys:
            new = RENAMES[key]
            block = [block[0].replace(key, new, 1), *block[1:]]
            notes.append(f"rename {key} -> {new}")
            key = new
        if key == "stage":
            old = scalar(block)
            new = STAGE_MAP.get(old.lower())
            if new is None and old.lower() == "interview":
                new = "onsite" if ONSITE_STATUS.search(status) else "phone"
                notes.append(f"stage Interview -> {new} (from status: {status or 'none'})")
            if new and new != old:
                if old.lower() != "interview":
                    notes.append(f"stage {old} -> {new}")
                block = [f"stage: {new}"]
            elif new is None:
                notes.append(f"stage {old!r} left as is: not recognized")
        elif key == "priority":
            old = scalar(block)
            new = PRIORITY_MAP.get(old.lower())
            if new and new != old:
                block = [f"priority: {new}"]
                notes.append(f"priority {old} -> {new}")
        elif key == "confidence":
            old = scalar(block)
            new = CONFIDENCE_MAP.get(old.lower())
            if new:
                block = [f"confidence: {new}"]
                notes.append(f"confidence {old} -> {new}")
        elif key == "track" and len(block) == 1 and not block[0].rstrip().endswith("]"):
            old = scalar(block)
            parts = [p.strip() for p in re.split(r"/|,", old) if p.strip()]
            tracks = [TRACK_WORDS[p.lower()] for p in parts if p.lower() in TRACK_WORDS]
            focus = [p for p in parts if p.lower() not in TRACK_WORDS]
            if tracks:
                block = [f"track: [{', '.join(dict.fromkeys(tracks))}]"]
                notes.append(f"track {old!r} -> [{', '.join(dict.fromkeys(tracks))}]")
                if focus and "focus" not in keys:
                    out.append((key, block))
                    key, block = "focus", [f"focus: {quote(', '.join(focus))}"]
        out.append((key, block))
    present = {k for k, _ in out if k}
    if "track" not in present:
        role = scalar(keys["role"]) if "role" in keys else ""
        guess = next((t for rx, t in ROLE_HINTS if rx.search(role)), None)
        if guess:
            out.append(("track", [f"track: [{guess}]"]))
            notes.append(f"track inferred from role {role!r}: {guess} (check)")
    for key, line in (("referrer", "referrer:"), ("links", "links: []")):
        if key not in present:
            out.append((key, [line]))
            notes.append(f"add {key}")
    new_text = "---\n" + "\n".join(line for _, b in out for line in b) + "\n" + body
    return new_text, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=PIPELINE)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    changed = 0
    for d in TRACKER_DIRS:
        for p in sorted((args.root / d).rglob("*.md")):
            text = p.read_text()
            if "\nstage:" not in text.split("\n---\n", 1)[0] + "\n":
                continue
            new, notes = normalize(text)
            if new != text:
                changed += 1
                print(f"{p.relative_to(args.root)}")
                for n in notes:
                    print(f"    {n}")
                if args.apply:
                    p.write_text(new)
    print(f"trackers_changed: {changed}{'' if args.apply else ' (dry run; pass --apply to write)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
