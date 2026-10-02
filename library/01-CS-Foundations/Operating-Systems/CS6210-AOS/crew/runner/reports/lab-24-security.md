# lab-24-security Report

## What I did
- Authored the `lab-24-security` lab.
- Created `caps_namespaces.sh` to demonstrate `capsh --print` and isolating mounts with `unshare -U -m -r`.
- Wrote `seccomp_filter.c` utilizing raw BPF macros to restrict the `getuid()` syscall, handling it by killing the process (SIGSYS).
- Implemented `andrew_handshake.py` demonstrating the Andrew Secure RPC protocol with nonces and a replay attack test.
- Developed the `Makefile` to securely build and verify these files, correctly intercepting the SIGSYS termination for seccomp to ensure `make test` completes cleanly.
- Updated the `README.md` to `status: solid`, populating the explanation, experiments, and questions.
- Captured `expected-output.txt` from within the Lima VM.
- Added a `.gitignore`.
- Committed the changes on `aos/writer-part-0-1`.

## Checks run
- Verified `make test` passes successfully within the Lima VM via `../setup/run-in-vm.sh . test`.
- Regenerated `expected-output.txt` using `../setup/run-in-vm.sh . capture`.

## Unverified
- All experiments and components were verified within the VM environment. No unverified assumptions remain.
