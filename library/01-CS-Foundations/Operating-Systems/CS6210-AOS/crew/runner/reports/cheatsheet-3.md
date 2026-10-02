# Cheatsheet 3 Generation Report

## What I did
- Read and analyzed the notes for CS 6210 AOS Part 3 (Distributed Systems, Objects, and Middleware), focusing on:
  - Lamport Clocks and Total Ordering
  - Mutual Exclusion Algorithms (Lamport, Ricart-Agrawala)
  - Latency Limits (RPC constraints, Firefly optimizations)
  - Network Protocol Composition (x-Kernel, Active Networks, Ensemble)
  - Object-Oriented Distributed Systems (Spring OS, Java RMI, EJB)
- Generated the markdown cheatsheet at `01-CS-Foundations/Operating-Systems/AOS/Cheatsheets/Part-3-Cheatsheet.md` following the specific frontmatter and styling rules.
- Ensured strict adherence to the one-sentence-per-line rule, converted em/en dashes to standard hyphens, and avoided emojis completely.
- Committed the new file with a conventional commit message.
- Adhered strictly to the negative constraints by skipping the README edits specified in the generic Part Writer template, recognizing the supervisor script handles the integration for this job.

## Checks run
- `python3` script to check for invalid dashes (`—` or `–`). Result: Passed.
- Git status check to ensure no other untracked or modified files were accidentally added to the commit.
- Verified style rules (no emojis, ASCII punctuation, frontmatter conformity, one physical line per sentence in prose).

## Unverified
- The links added to the README were skipped as per the hard instructions to only edit the `Part-3-Cheatsheet.md` file. The supervisor will need to insert the link into the `Cheatsheets/README.md` and the `Part-3-Distributed-Systems/README.md` files.
