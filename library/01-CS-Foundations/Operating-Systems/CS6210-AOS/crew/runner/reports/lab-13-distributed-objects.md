# lab-13-distributed-objects Report

## What I did
- Created the Python Subcontract example demonstrating pluggable invocation with `SingletonSubcontract` and `ReplicatedSubcontract` (L06b).
- Implemented a Java RMI client-server application using a `Hello` interface, with a local `rmiregistry` (L06a).
- Created a generic gRPC greeter service with Protocol Buffers (`greeter.proto`) and both synchronous and asynchronous Python clients (L06c).
- Authored a `Makefile` supporting `all`, `run`, `test`, and `clean` commands. The test suite automatically verifies output and gracefully kills background daemon processes (`rmiregistry`, `java Server`, `greeter_server.py`).
- Added a `.gitignore` to prevent compiled Java `.class` files, Python `.pyc` and protobuf stubs from being committed.
- Updated `README.md` to status `solid`. Added prereqs, how it works, expected execution outputs with real numbers (using medians of 10 runs over `CLOCK_MONOTONIC`), three experiments with prediction prompts, and three folded Q&A elements.
- Cleaned the output directory and committed changes to git.

## Checks run
- `run-in-vm.sh lab-13-distributed-objects test`: Successfully executed all tests inside the `aos` Lima VM.
- `run-in-vm.sh lab-13-distributed-objects capture`: Captured `expected-output.txt`.
- `run-in-vm.sh lab-13-distributed-objects clean`: Successfully cleaned up all `.class` files, `.pyc` caches, and python protobuf generated code.

## Anything unverified
- None. Execution inside the `aos` VM was robust and reliably terminated lingering Java RMI/Python gRPC background processes.
