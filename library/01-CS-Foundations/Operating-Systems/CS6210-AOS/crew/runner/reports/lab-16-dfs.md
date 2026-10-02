# lab-16-dfs Report

## What I Did
- Wrote `raid5.py` to demonstrate RAID-5 parity computation and disk reconstruction from surviving disks.
- Wrote `lfs.py` to simulate a log-structured store with an append-only log, in-memory index mapping, and a `clean` command for garbage collection.
- Wrote `fuse_cache.c` (using `libfuse3`) to implement a write-back cache FUSE filesystem, which defers data flushes to the backing store until `release` or `flush` is called (e.g., when the client file descriptor closes). Python's `fusepy` was considered but `libfuse.so.2` wasn't available natively on the Ubuntu 24.04 VM, so standard C FUSE 3 was used.
- Created a `Makefile` to compile the C FUSE code, execute `raid5.py`, run `lfs.py`, and test the write-back FUSE cache with real filesystem commands (`cat`, `python3` file handles, and `fusermount3`).
- Verified expected outputs using the VM (`run-in-vm.sh`) and captured the output.
- Updated `README.md` to solid status, preserving seed frontmatter. Added L07c explanations, commands, what to see, experiments, and questions.

## Checks Run
- Successfully ran `labs/setup/run-in-vm.sh labs/lab-16-dfs test` in the Lima VM with exit code 0.
- Successfully ran `labs/setup/run-in-vm.sh labs/lab-16-dfs capture` to generate `expected-output.txt`.
- Validated `README.md` frontmatter and formatting per vault rules (no emojis, single-sentence per line, no dashes but '-').
- Verified no git ignore violations or honor code violations (this covers paper concepts safely).

## Unverified
- High-scale performance metrics were not measured due to Lima VM constraints (no PMU counters), relying on basic runtime measurement in Python and simplified C FUSE demonstration.
