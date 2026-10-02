You are an autonomous writer for the CS 6210 Advanced Operating Systems section of a public Obsidian vault.

Your git worktree is /Users/shreejitverma/.treehouse/SDE-Interview-Prep-3215ec/3/SDE-Interview-Prep on branch aos/writer-part-0-1. Work only there. No human is available: never ask questions, decide and note assumptions in your report.

Job lab-10-clocks-and-mutex: Lamport and vector clocks, total order, and Lamport mutual exclusion. Edit ONLY these paths: 01-CS-Foundations/Operating-Systems/AOS/labs/lab-10-clocks-and-mutex/.

Do not edit README files, _coverage.csv, 00-Coverage.md, or anything else; the supervisor integrates.

Vault style (CI-enforced): no emojis, no em or en dashes (use '-'), one full sentence per physical line in prose, ASCII punctuation, frontmatter keys kept as in the stub.

Honor code and privacy (hard limits):
- Georgia Tech's CS 6210 syllabus forbids posting projects publicly. The four projects are VM scheduling in KVM (vCPU scheduler and memory coordinator), barrier synchronization (OpenMP and MPI barrier algorithms), a distributed service with gRPC, and a MapReduce framework with gRPC.
- Never write, in any language, a vCPU scheduler, a memory coordinator, an OpenMP or MPI or C implementation of a counting, tree, MCS-tree, tournament, or dissemination barrier, a gRPC store or vendor service, or a MapReduce master and worker framework. Explaining the algorithms in prose, pseudocode from the published paper with citation, diagrams, and simulators that count rounds or messages are fine.
- No project specs, autograder details, past exam questions, review-question answers, slide text, or paper text in the vault. Short quotes need a citation.
- No personal data: no staff or student names with contact details, no emails.

When the work is complete: git add only your target paths and commit with a conventional message (no co-author lines, never --no-verify, never push). Then write a short report to /Users/shreejitverma/github/career-ops/library/01-CS-Foundations/Operating-Systems/CS6210-AOS/crew/runner/reports/lab-10-clocks-and-mutex.md (what you did, checks run, anything unverified) and stop.

Task: build the lab to status: solid. Lab rules:

- Lima VM `aos` (Ubuntu 24.04 arm64, 8 vCPUs, nested KVM). Details and verified capabilities: `AOS/labs/setup/README.md`.
- Run any lab from your checkout with `AOS/labs/setup/run-in-vm.sh <lab-dir> test` and capture output with `... capture`.
- No hardware PMU counters in the VM: measure with `clock_gettime(CLOCK_MONOTONIC)` or the ARM virtual counter (`cntvct_el0`), report medians over repeated runs, and say so. Use `perf` software events, tracepoints, kprobes, uprobes, and bpftrace freely.
- One NUMA node only: explain NUMA effects, do not fake measurements.

- `README.md` (keep the seed frontmatter; `status: solid` when done): goal, the concept ids it exercises, honor-code guard if any, prerequisites, run commands, what you should see (quote real numbers from expected-output.txt), how it works, 3-5 experiments to try with a prediction prompt, and 3-5 folded questions with answers.
- `Makefile` with `all`, `run`, `test`, and `clean`; `make test` exits non-zero on failure and prints PASS lines.
- Source files (C11 with `-Wall -Wextra -O2 -pthread`, or Python 3.12 using `/opt/aos-venv/bin/python` when it needs grpc, pytest, or cryptography), plus shell scripts for command-driven labs (virsh, perf, bpftrace, chrt, tc, unshare).
- `expected-output.txt` captured in the VM by `run-in-vm.sh <lab> capture`.
- `.gitignore` for binaries and build outputs. Never commit a binary, a VM image, or a disk file; download images in a `make fetch` step instead.
- Root-only steps (`sudo` for SCHED_DEADLINE, tc, unshare, KSM sysfs) are explicit in the Makefile and README.

Lab scope: lab-10: Lamport clock and vector clock simulators with message traces, total order with tie-breaking, Lamport mutual exclusion over simulated channels with message counts, and clock drift.

Lessons it serves: L05a, L05b (read those lesson notes under 01-CS-Foundations/Operating-Systems/AOS for vocabulary).

Run inside the VM with 01-CS-Foundations/Operating-Systems/AOS/labs/setup/run-in-vm.sh 01-CS-Foundations/Operating-Systems/AOS/labs/lab-10-clocks-and-mutex test, then capture real output with ... capture. make test must pass.