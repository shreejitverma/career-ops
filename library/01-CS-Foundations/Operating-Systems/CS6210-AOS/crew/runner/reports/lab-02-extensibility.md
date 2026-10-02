# lab-02-extensibility Report

## What was done
- Implemented `userfaultfd_demo.c`, a C program demonstrating safe application-level page fault handling as an analogy to Exokernel principles.
- Implemented `trace_exec.sh`, a `bpftrace` script that attaches to the `sys_enter_execve` tracepoint to demonstrate modern safe in-kernel extensibility as an analogy to SPIN principles.
- Created `Makefile` with `all`, `run`, `test`, and `clean` targets.
- Updated `README.md` to `status: solid`, adding an explanation of how the code demonstrates the lessons, execution instructions, experiments, and folded questions.
- Captured actual output via `make run` inside the nested KVM environment into `expected-output.txt`.
- Added a `.gitignore` to keep binaries out of the repository.
- Committed the changes using a conventional commit.

## Checks run
- Built and ran `userfaultfd_demo.c` to verify that `userfaultfd` properly handles and maps anonymous memory page faults using the `UFFDIO_COPY` ioctl.
- Verified that `bpftrace` executes successfully on the provided Ubuntu VM, properly attaching to tracepoints.
- Executed `run-in-vm.sh lab-02-extensibility test` successfully.
- Executed `run-in-vm.sh lab-02-extensibility capture` to save the output.

## Unverified
- The `userfaultfd_demo.c` requires root privileges on the VM since `vm.unprivileged_userfaultfd` wasn't explicitly enabled or verified for non-root users. The `Makefile` leverages `sudo` for execution to ensure tests pass without user intervention.
- The experiments listed in the README were designed conceptually based on the working examples; they were not run manually by the agent.
