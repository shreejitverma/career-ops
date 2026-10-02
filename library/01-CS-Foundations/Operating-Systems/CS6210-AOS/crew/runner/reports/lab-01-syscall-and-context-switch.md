# Report: lab-01-syscall-and-context-switch

## What I Did
- Created C programs to measure syscall costs (`SYS_getpid` vs glibc `getpid()`) and context switch costs (thread vs process using a pipe ping-pong).
- Wrote a `Makefile` that handles compiling, running, and cleaning up the executables. It also runs `perf bench sched pipe` automatically.
- Fixed a pipe buffering duplication bug that occurred because `fork()` duplicated the parent's un-flushed `stdout` buffer.
- Captured `expected-output.txt` from within the VM using `make run`. The thread switch and process switch times were slightly over 30 to 50 microseconds due to nested virtualization overhead. `perf bench sched pipe` was measured effectively as well.
- Updated `README.md` to `status: solid`, incorporating the exact measured numbers, the experimental setups (with prediction prompts), and folding answers relating to Mach/L3 and the mechanics of ASID transitions on ARM64 versus standard x86 mechanisms.
- Committed the changes using a conventional commit message.

## Checks Run
- Successfully compiled the C programs with `-Wall -Wextra -O2 -pthread`.
- Ran the `run-in-vm.sh labs/lab-01-syscall-and-context-switch test` command ensuring `make test` exited zero.
- Captured output using `run-in-vm.sh labs/lab-01-syscall-and-context-switch capture`.
- `expected-output.txt` was validated and found matching to the new numbers.

## Unverified
- The benchmark was only tested inside the nested Lima VM environment. Bare-metal benchmarks were extrapolated but not explicitly run due to VM constraints.
