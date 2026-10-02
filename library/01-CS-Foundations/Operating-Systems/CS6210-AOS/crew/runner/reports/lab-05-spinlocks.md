# Lab 05 Spinlocks Report

- **Status**: solid
- **Implementation**: Implemented TAS, TTAS, Exponential Backoff, Ticket, Anderson Array, and MCS locks using C11 atomics (`stdatomic.h`). All locks use `cpu_relax()` to reduce bus traffic and power consumption during spinning.
- **Tests**: `make test` runs a correctness check ensuring that the final counter equals `iterations * num_threads` (10,000 per thread across 8 threads).
- **Benchmark**: `make run` runs 1-8 threads doing 10,000 lock/unlocks per thread and reports the elapsed time using `clock_gettime`.
- **Output capture**: Captured using `run-in-vm.sh labs/lab-05-spinlocks capture` in the Lima VM.
- **README**: Authored goal, prerequisites, run commands, "What you should see", "How it works", 4 experiments to try (with predictions), and 4 folded questions (with answers).

Checks passed: `make test` ran successfully inside the Lima VM. Unverified: No actual physical multi-socket NUMA measurements were performed as the VM exposes a single NUMA node.
