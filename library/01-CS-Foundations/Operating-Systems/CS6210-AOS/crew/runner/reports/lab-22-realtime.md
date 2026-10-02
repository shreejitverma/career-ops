# Lab 22 (Realtime) Writer Report

- **Actions taken**:
  - Implemented `timers.c` to measure latency for one-shot (`clock_nanosleep` with `TIMER_ABSTIME`) and periodic (`timerfd`) timers. Supported `SCHED_OTHER`, `SCHED_FIFO`, and `SCHED_DEADLINE`.
  - Implemented `run-cyclictest.sh` to run `rt-tests` `cyclictest` and `timers.c` under an idle state and then with a synthetic workload (`stress-ng`).
  - Added `test.sh` and `Makefile` conforming to the lab contract.
  - Ran `run-in-vm.sh lab-22-realtime test` and `capture` to verify behavior and generate `expected-output.txt` natively on the VM.
  - Wrote `README.md` defining goals, explaining the concepts, incorporating the real metrics gathered from the VM, proposing experiments, and providing folded Q&A for the lesson context.
  - Formatted `README.md` with vault style guidelines: one sentence per physical line, no emojis, en/em dashes converted to hyphens (-).

- **Checks Run**:
  - VM capability check implicitly verified: `cyclictest`, `stress-ng` are available. `SCHED_DEADLINE` and `SCHED_FIFO` are functional.
  - `make test` inside VM passes.
  - Re-read frontmatter tags and structure.

- **Unverified items**:
  - `cyclictest` may display `WARN: open /dev/cpu_dma_latency: Permission denied` when invoked without `sudo`, which is normal and acceptable behavior for testing `SCHED_OTHER` baselines but might look confusing to a user scanning stdout.
