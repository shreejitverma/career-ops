# Lab 17 (Recoverable Memory) Report

## What I Did
- Implemented a simple, user-space Lightweight Recoverable Virtual Memory (LRVM) library in C (`src/rvm.h`, `src/rvm.c`).
- Developed a test suite (`src/test_rvm.c`) covering `begin_transaction`, `set_range` (undo log creation), `end_transaction` (redo logging and `fsync`), `abort_transaction`, log truncation, and crash recovery (using a child process that forks and crashes with `kill -9`).
- Added an `fio` benchmark (`fio-fsync.sh`) to measure standard `fsync` storage latencies, providing a concrete motivation for Rio Vista's zero-copy persistence approach.
- Created `Makefile` and `.gitignore` per specifications.
- Expanded `README.md` to solid status with concept links (L08a, L08b), setup prerequisites, a detailed "How it works" section, experiments to try, and theoretical questions with folded answers.

## Checks Run
- `make test` inside the Lima `aos` VM completed successfully (`PASS: all tests completed successfully`).
- Validated warning-free compilation with `gcc -Wall -Wextra -O2 -pthread -std=gnu11`.
- Captured actual output via the `run-in-vm.sh capture` script into `expected-output.txt`.

## Unverified
- The `fio` benchmark produces realistic host-dependent latencies, but numbers will naturally fluctuate based on host SSD and nested VM block device caching configurations.
