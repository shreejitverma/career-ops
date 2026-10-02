# Report: L02c The Exokernel Approach

## What I did
- Expanded all seed concepts for L02c (The Exokernel Approach) to reach "solid" status.
- Added a Mermaid sequence diagram illustrating the page fault handling mechanism via upcalls.
- Added a worked example with arithmetic comparing a software TLB context switch vs a traditional hardware TLB flush context switch.
- Formatted the text strictly to vault guidelines: one full sentence per physical line, ASCII characters, no emojis, no em/en dashes.
- Maintained all existing coverage tags and YAML frontmatter verbatim.
- Summarized the four associated papers.
- Compared monolithic, microkernel, exokernel, and SPIN architectures in a table.
- Added exam traps and pitfall warnings.

## Checks run
- `python3 tools/check_aos_coverage.py --lesson L02c --verbose`: The output showed 0 "seed", "no heading", or "under 250" problems. The script noted missing lab citations and practice citations, which are expected to be handled in a separate job per the prompt instructions.
- Confirmed no em-dashes or en-dashes (`grep -nE '—|–' ...`).
- Confirmed no emojis.
- Ran `git commit` to commit the single modified file successfully (passed the CI hooks).

## Unverified
- The Practice and Lab documents are yet to be populated, so their coverage checks still report missing lines (expected behavior).
