# lab-18-transactions Report

## What I did
- Created `wal_shadow.c` to benchmark Write-Ahead Logging vs Shadow Paging commit latencies using `clock_gettime`. It models the single sync required for WAL vs the two syncs required for Shadow Paging.
- Created `quicksilver_2pc.py`, a Python simulator implementing Quicksilver's hierarchical transaction tree. It models normal commits, node crashes during the voting phase leading to an abort, and a coordinator crash and recovery right after the global commit record is logged.
- Wrote `Makefile` to compile the C binary and execute both simulation tools. 
- Captured `expected-output.txt` by running `make run` in the Lima VM.
- Authored the `README.md` to explain the mechanics of WAL vs shadow paging and Quicksilver 2PC, structured with 3 experiment prompts and 4 review questions.
- Added `.gitignore` to prevent generated artifacts from being committed.
- Validated all tests via `run-in-vm.sh labs/lab-18-transactions test` running successfully with `PASS` output.
- Committed changes locally using the conventional commit format `feat(aos): build lab-18-transactions`.

## Checks run
- [x] VM capability constraints followed (used `clock_gettime`, explained rather than faked NUMA)
- [x] Compilation warnings squashed (added checks for `write` and `pwrite` return values)
- [x] Code tests passed (`make test` completes with 0 exit code in VM)
- [x] Honor code respected (no projects or autograder details shared)
- [x] Vault style guidelines met (1 sentence per line, ascii dashes used, no emojis)

## Unverified/Follow-up
None. The code reliably simulates the concepts taught in L08c Quicksilver and System R Recovery papers and successfully captures consistent latency timings to validate the theory in the VM.
