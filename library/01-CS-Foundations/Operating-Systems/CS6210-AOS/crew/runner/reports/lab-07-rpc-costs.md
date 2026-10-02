# Report: lab-07-rpc-costs

- **What I did**: Built the lab-07-rpc-costs in C11. Created `ipc_bench.c` for pipe/unix/shm ping-pong, `sendfile_bench.c` for sendfile versus read/write, a `test.sh` script (which uses `strace -c -f`), and a `Makefile`. I ran the lab inside the VM with the `run-in-vm.sh` script to capture real RTTs and syscall profiling. I documented the setup, experiments, and questions in `README.md`.
- **Checks run**: `make clean all` and `make test` executed successfully in the VM. Output was captured via `... capture` into `expected-output.txt`. Git commit passed pre-commit hooks.
- **Unverified**: The results for `sendfile` show it takes longer than `read/write` in this VM, likely due to virtiofs implementation quirks. I documented this explicitly rather than trying to spoof the numbers, per instruction. Everything else verified correctly.
