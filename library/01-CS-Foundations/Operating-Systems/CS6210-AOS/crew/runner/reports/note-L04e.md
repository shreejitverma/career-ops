# L04e Scheduling Update Report

## Actions Taken
- Read the existing L04e stub and the provided source text files (slides, cache affinity paper, and CMP paper).
- Replaced all `> [!todo] Seed` callouts with comprehensive content while strictly preserving all original headings and coverage comments.
- Authored the TL;DR, learning outcomes, and motivation sections to set up the problem of cache affinity.
- Expanded each core concept (e.g., FCFS, Fixed processor, Last processor, Minimum Intervening, Limited Queue, Implementation issues, Performance metrics, Load balancing, Cache-aware scheduling, and Modern descendants). Each concept contains well over 250 characters of explanatory text, with sentences split correctly to exactly one per physical line.
- Included `> [!note]` and `> [!warning]` callouts appropriately to define terms like Cache Affinity and detail pitfalls.
- Created a `sequenceDiagram` in Mermaid outlining the steps involved in Balance-Set scheduling for CMP architectures.
- Added worked examples with verified arithmetic for both Affinity Index calculation and Balance-Set Cache math, showing how thread grouping avoids L2 cache thrashing.
- Constructed a markdown comparison table summarizing the strengths, weaknesses, and best use cases of the various scheduling policies discussed.
- Drafted single-paragraph summaries for all 7 papers in the deep dive section.
- Added modern descendants covering Linux CFS, EEVDF, Scheduling Domains, eBPF, and unikernels.
- Committed changes using a conventional commit message.

## Checks Run
- Formatted file checking: Verified no emojis, no em/en dashes, and ensured only ASCII punctuation is used.
- Line breaking checking: Ensured one full sentence per physical line.
- Checked content via `python3 tools/check_aos_coverage.py --lesson L04e --verbose`. Output confirmed that there are no 'seed', 'no heading', or 'under 250' issues in the L04e note (the tool reported missing rows only for lab and practice notes, which are expected and outside the scope of this job).
- Verified git commit contained only `01-CS-Foundations/Operating-Systems/AOS/Part-2-Parallel-Systems/L04e-Scheduling.md`.

## Unverified/Notes
- The "Using Processor-Cache Affinity Information in Shared Memory Multiprocessor Scheduling.txt" paper file provided was empty/blank (13 bytes of whitespace). I synthesized the Minimum Intervening policy and cache affinity mathematics using the provided slides instead, which provided sufficient detail.
