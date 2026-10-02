# lab-08-scheduling

## What I did
- Built the `lab-08-scheduling` directory to `status: solid`.
- Wrote `affinity_workload.c` to generate memory-intensive workload to test cache affinity behavior.
- Wrote `test.sh` to exercise `taskset` (CPU pinning), `perf sched record/latency` (scheduler delays), `chrt` (FIFO vs RR policies), and `cgroups v2` (`cpu.weight`).
- Wrote `sched_simulator.py` to simulate FCFS, Fixed, Last Processor, and Minimum Intervening policies, tracking cache-affinity migrations based on the Squillante/Lazowska model.
- Solved a TTY/SIGPIPE hang with `sudo perf sched` during automated capture by redirecting `stdin` from `/dev/null`.
- Wrote the `Makefile` and `.gitignore`.
- Updated `README.md` with goals, expected outputs, explanation of mechanisms, experiments, and Q&A.
- Successfully captured output into `expected-output.txt` using the VM harness.
- Committed the files matching vault style guidelines.

## Checks run
- `make test` inside the VM exits with `0` and successfully outputs metrics for all tools.
- Simulator generates positive non-zero migrations.
- `run-in-vm.sh lab-dir capture` succeeds.
- Git commit passed CI formatting and honor code validations.

## Anything unverified
- None. All components were verified end-to-end within the provided Lima VM environment.
