# lab-10-clocks-and-mutex Status Report

## What was done
- Built a C11 discrete-event-style simulator `clocks.c` demonstrating logical Lamport clocks, Vector clocks, and physical clock drift.
- Built a C11 `pthreads` based Lamport mutual exclusion simulator `mutex.c` with multiple threads communicating via simulated message queues, validating the $3(N-1)$ message complexity rule.
- Added a `Makefile` with `all`, `run`, `test`, and `clean` targets. The `test` target successfully runs both binaries and asserts expected outcomes.
- Captured output using `run-in-vm.sh` from within the nested VM, generating `expected-output.txt`.
- Fully documented `README.md` keeping the seed frontmatter but updating status to `solid`, noting goals, run instructions, experiments (such as predicting logical vs physical clock discrepancies, extending node count), and questions with answers.
- Added `.gitignore` to prevent compilation artifacts from being tracked.

## Checks run
- `make test` locally to verify outputs strings match criteria.
- `make clean && ../setup/run-in-vm.sh . test` within the VM to verify environment-specific test success.
- `make clean && ../setup/run-in-vm.sh . capture` within the VM to produce real `expected-output.txt` on arm64 Ubuntu Linux 24.04.

## Unverified items
- None. Fully validated and compliant with honor code limits (Lamport mutex/clocks are distinct from the specific project specs).
