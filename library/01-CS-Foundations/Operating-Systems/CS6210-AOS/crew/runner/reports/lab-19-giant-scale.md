# lab-19-giant-scale Report

## What was done
1. **Implemented Simulator Scripts:** Created `server.py` and `client.py` using standard `asyncio` to model the nodes.
    - Servers enforce a strict processing capacity using an async token bucket rate limiter.
    - Client generates load matching node capacity and measures yield and harvest metrics under both replication and partitioning modes.
2. **Setup Automation:** Created a `Makefile` that orchestrates the entire test sequence. It spins up 2 background server instances, measures baseline performance, kills one node to simulate failure, and measures the degraded performance. It exits non-zero if the DQ metrics don't align with theory.
3. **VM Validation:** Executed `setup/run-in-vm.sh lab-19-giant-scale test` within the Lima VM environment to ensure the tests successfully pass. Captured actual outputs.
4. **Documentation:** Wrote a comprehensive `README.md` containing concepts, prerequisites, commands, expected output, and thought experiments. Explained round-robin DNS vs L4 balancing. Updated status to `solid`.
5. **Committed Changes:** `git add` and `git commit` to the worktree branch.

## Checks run
- `make test` executed natively to trace logic.
- `bash 01-CS-Foundations/Operating-Systems/AOS/labs/setup/run-in-vm.sh 01-CS-Foundations/Operating-Systems/AOS/labs/lab-19-giant-scale test` inside VM.
- Output from VM successfully captured to `expected-output.txt`.

## Unverified
None. The VM successfully ran the test with 100% baseline yield/harvest, followed by a correctly predicted drop in replicated yield and partitioned harvest.
