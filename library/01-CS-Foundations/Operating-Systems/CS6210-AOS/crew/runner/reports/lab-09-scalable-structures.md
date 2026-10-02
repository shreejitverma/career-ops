# lab-09-scalable-structures completion report

**What was done:**
- Implemented `scalable_counters.c` to benchmark a `pthread_mutex_t` locked counter, an `_Atomic` counter, and a per-thread padded counter, demonstrating how avoiding inter-processor coherence traffic drastically improves performance.
- Implemented `false_sharing.c` with an array of unpadded atomic counters vs. a cache-line padded array, visually showcasing the cost of MESI invalidations when hardware incorrectly believes a cache line is contested.
- Implemented `read_mostly.c` comparing a standard `pthread_rwlock_t` to a simplified epoch-based RCU-like reader-writer structure, demonstrating faster reads without writer lock contention.
- Created the corresponding `Makefile` with `all`, `run`, `test`, and `clean` targets. Modified CFLAGS to include `-D_GNU_SOURCE` to support POSIX features in C11.
- Updated `README.md` to a `status: solid`, incorporating theoretical goals matching `L04f`, predictions and experiment guides, runtime commands, and output data.
- Built and ran the full suite inside the `Lima VM aos` using the provided test and capture scripts, capturing the authentic expected outputs.
- Tracked necessary files and `.gitignore` properly.
- Committed changes conventionally.

**Checks run:**
- Compilation check via `make` inside and outside the VM.
- Full testing via `run-in-vm.sh lab-09-scalable-structures test`.
- Output capture via `run-in-vm.sh lab-09-scalable-structures capture`.
- `git commit` hooks completed securely with no violations.

**Unverified:**
- No hardware PMU counters were tested directly (e.g. `perf stat -e cache-misses`), as they are typically unavailable inside nested KVM virtualization by default, though an experiment is suggested for users running on bare-metal.
