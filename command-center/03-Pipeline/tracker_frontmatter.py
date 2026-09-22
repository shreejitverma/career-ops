"""Minimal YAML frontmatter reader shared by the pipeline scripts (stdlib only).

Reads top-level `key: value` scalars. List properties are read by `read_list`,
which accepts both the inline form (`aliases: [A, B]`) and the block form that
Obsidian's Properties panel writes (`aliases:` followed by indented `- A` lines).
"""

from __future__ import annotations

import re

KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")
ITEM = re.compile(r"^\s+-\s+(.*)$")


def _lines(text: str) -> list[str]:
    if not text.startswith("---\n"):
        return []
    return text[4:text.find("\n---", 4)].splitlines()


def _unquote(s: str) -> str:
    return s.strip().strip('"').strip("'")


def read_frontmatter(text: str) -> dict[str, str]:
    fm = {}
    for line in _lines(text):
        m = KEY.match(line)
        if m:
            fm[m.group(1)] = _unquote(m.group(2))
    return fm


def read_list(text: str, key: str) -> list[str]:
    lines = _lines(text)
    for i, line in enumerate(lines):
        m = KEY.match(line)
        if not m or m.group(1) != key:
            continue
        inline = m.group(2).strip()
        if inline:
            return [v for v in (_unquote(x) for x in inline.strip("[]").split(",")) if v]
        items = []
        for nxt in lines[i + 1:]:
            item = ITEM.match(nxt)
            if not item:
                break
            if _unquote(item.group(1)):
                items.append(_unquote(item.group(1)))
        return items
    return []
