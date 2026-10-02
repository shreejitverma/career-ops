# lab-06-barriers Report

## What I Did
- Created `Makefile`, `measure_threads.c`, and `measure_mpi.c` to test actual execution times of `pthread_barrier_wait`, `#pragma omp barrier`, and `MPI_Barrier`.
- Built `simulator.py` to calculate theoretical rounds, messages, and critical path length for Counting, Tree, MCS Tree, Tournament, and Dissemination barriers for N=2..64.
- Created `.gitignore` to prevent binaries and intermediate files from being tracked.
- Executed tests inside the provided Lima VM `aos` using the `run-in-vm.sh` script to capture real test execution into `expected-output.txt`.
- Refactored `README.md` to `status: solid`, incorporating the lab goal, required concepts, honor code guard (no project implementation), prerequisites, run instructions, and an explanation of the underlying theory. Included theoretical experiments and review questions.
- Committed changes safely to `aos/writer-part-0-1`.

## Checks Run
- Ran `01-CS-Foundations/Operating-Systems/AOS/labs/setup/run-in-vm.sh 01-CS-Foundations/Operating-Systems/AOS/labs/lab-06-barriers test` and received `PASS`.
- Ran `01-CS-Foundations/Operating-Systems/AOS/labs/setup/run-in-vm.sh 01-CS-Foundations/Operating-Systems/AOS/labs/lab-06-barriers capture` successfully.

## Unverified
- The `simulator.py` plot generation requires `matplotlib` and `pandas`. They were not present in the VM by default, so it simply logs "matplotlib/pandas not found. Plot not generated.", which is safe and functional but implies the user won't get a plot without installing them.
