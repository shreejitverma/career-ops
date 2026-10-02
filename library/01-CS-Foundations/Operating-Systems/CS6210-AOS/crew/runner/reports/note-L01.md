# Report: note-L01

**What I did:**
- Replaced all `> [!todo] Seed` callouts in `L01-Introduction-to-AOS.md` with comprehensive lesson content based on syllabus guidelines.
- Updated frontmatter to `status: solid`.
- Formatted content strictly following Vault style constraints (no emojis, ASCII punctuation, one full sentence per physical line, no em/en dashes).
- Added specific numerical examples for context switch and system call overheads, checking the arithmetic.
- Created a Mermaid diagram illustrating the transition mechanism during a system call trap.
- Fleshed out the comparison table and added modern descendants and pitfall callouts.
- Committed the changes using a conventional commit message.

**Checks run:**
- Verified all prose for the one-sentence-per-line rule.
- Ran `python3 tools/check_aos_coverage.py --lesson L01 --verbose`. 

**Unverified / Outstanding:**
- The coverage script reported missing components for `lab-01-syscall-and-context-switch/Makefile` and `Practice-L01.md`. As instructed, these were not edited and belong to other jobs. The target note itself triggered no "seed", "no heading", or "under 250" character errors.
