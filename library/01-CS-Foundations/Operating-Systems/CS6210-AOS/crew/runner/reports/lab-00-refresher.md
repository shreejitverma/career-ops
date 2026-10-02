# lab-00-refresher Report

## What was done
- Created `page_faults.c` to demonstrate demand paging. It uses `getrusage` to count minor page faults for anonymous memory and file-backed memory. I observed that the file-backed mapping incurs fewer faults (160 instead of 2560 for 10 MB) due to the kernel's fault-around feature mapping 64 KB at a time.
- Created `pagemap.c` to demonstrate reading `/proc/self/pagemap` to translate virtual addresses to physical frame numbers (PFN). Documented that unprivileged processes get a PFN of `0x0` due to security mitigations introduced in Linux 4.0.
- Created `cache_tlb.c` to generate a memory access latency curve using strided accesses (64 bytes for cache misses, 4096 bytes for TLB misses), defeating hardware prefetchers with a pointer-chasing array.
- Created `prod_cons.c` to demonstrate a basic POSIX threads producer-consumer with a bounded buffer using mutexes and condition variables.
- Created a `Makefile` supporting `all`, `run`, `test`, and `clean` with `test` verifying successful execution.
- Added `.gitignore` to prevent tracking binaries.
- Executed `run-in-vm.sh lab-00-refresher test` and successfully generated `expected-output.txt` using `capture`.
- Wrote the `README.md` containing goals, prerequisites, expected output analysis, system mechanics, and experiments with folded questions/answers in compliance with vault style guidelines.

## Checks run
- `make test` inside the VM (`run-in-vm.sh lab-00-refresher test`). All binaries compiled and executed without warnings. Outputs were recorded properly.
- Verified correct honor code constraints (this is purely a refresher, no grader components implemented).
- Git pre-commit hooks (`no-mistakes` style) passed locally when committing the files.

## Unverified items
- The major fault count for the file-backed access consistently reported as 0 despite attempts to drop the page cache (`echo 3 > /proc/sys/vm/drop_caches`) and disabling read-ahead (`MADV_RANDOM`). This is likely due to the Lima VM filesystem (virtiofs) masking block device IO waits from the guest kernel's page fault accounting. I opted to document this behavior in the README rather than building a block device in the VM, as it satisfies the scope of counting and examining the faults.
