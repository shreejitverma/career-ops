# L05d Active Networks - Job Report

## What I did
- Replaced all `> [!todo] Seed` callouts in `01-CS-Foundations/Operating-Systems/AOS/Part-3-Distributed-Systems/L05d-Active-Networks.md`.
- Wrote detailed content for the TL;DR, Learning outcomes, Motivation and the problem, Core concepts, and other sections.
- Kept the headings and coverage comments verbatim.
- Maintained the vault style: strictly one full sentence per physical line, no emojis, no em/en dashes, and ASCII punctuation.
- Included a sequence diagram using Mermaid to illustrate the ANTS capsule code demand-loading process.
- Added a worked arithmetic example on ANTS capsule code distribution overhead based on a 16 KB code size limit over a 10 Mbps link.
- Created a comparison table for Traditional IP Routing vs. ANTS vs. the x-kernel architecture.
- Added one paragraph per paper deep dive for the 6 listed papers, linking to their respective paper notes.
- Included pitfalls and exam traps.
- Committed the changes with a conventional commit message.

## Checks run
- Ran `python3 tools/check_aos_coverage.py --lesson L05d --verbose` to verify no seeds or missing headings were detected for the target file.
- Verified physical line lengths (one sentence per line) across the file.
- Validated the git commit succeeded against the pre-commit hooks (private_data_violations: 0).

## Unverified
- The `tools/check_aos_coverage.py` script reported missing lab coverage and missing citations in `Practice-L05.md`, which is expected since lab and practice problems belong to other jobs as per instructions.
