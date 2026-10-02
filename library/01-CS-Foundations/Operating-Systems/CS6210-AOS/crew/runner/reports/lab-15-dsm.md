# Report: lab-15-dsm implementation

- **What was done:** 
  - Implemented `dsm.c`, a C11 user-level simulator for a page-based Distributed Shared Memory (DSM) system.
  - Used `mprotect()` and `SIGSEGV` to intercept write faults, generate twin pages, and implement a multiple-writer protocol that avoids false sharing.
  - Demonstrated Lazy Release Consistency (LRC) via `dsm_acquire()` and `dsm_release()` across simulated nodes (forked processes passing diffs over a `socketpair`).
  - Added a `Makefile` with `all`, `run`, `test`, and `clean` targets.
  - Populated `README.md` with goals, concepts (L07b), execution instructions, real measurements, explanations (including NUMA effects), experiments, and folded questions.
  - Captured `expected-output.txt` using the standard `run-in-vm.sh <lab> capture` pipeline inside the Lima `aos` VM.
  - Created `.gitignore` to prevent committing generated binaries.
  - Committed the changes using a conventional commit message.

- **Checks run:**
  - `make run` executed inside the `aos` VM successfully produced expected output demonstrating multiple-writer coherence and diff merging.
  - `make test` successfully verified execution and output correctness, printing `PASS` and exiting `0`.
  - Output captured and verified via `run-in-vm.sh lab-15-dsm capture`.
  - Manual review of `README.md` to ensure vault styling constraints (no emojis, single sentence per line, ascii punctuation) and honor-code boundaries were respected.

- **Unverified items:**
  - None. All requirements fulfilled.
