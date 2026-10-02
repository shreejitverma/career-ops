# lab-11-network-latency report

## What was done
- Read `L05d` to identify key Active Networks concepts: latency, demand-loading capsule logic via MD5 type hashes, and payload marshalling.
- Created `capsule.proto` to define the schema for capsule routing payloads.
- Authored `marshal_test.py` to evaluate the relative serialization costs (latency) of `struct.pack`, `json`, and `protobuf`. Handled median computation using `clock_gettime` equivalents in Python (`time.perf_counter()`) given the lack of PMU hardware support in the VM.
- Authored `latency_test.sh` to measure baseline network loopback latency and create virtual ethernet pairs (`veth`). Leveraged `tc netem` to artificially simulate the jitter, delay, and packet drops intrinsic to WAN environments where active networks run. Included proactive cleanup to ensure safe subsequent executions.
- Authored `capsule_sim.py` which demonstrates the ANTS toolkit's core demand-loading logic across intermediate nodes (active routers), correctly validating the logic's MD5 fingerprint.
- Verified test robustness using `make test`. Executed `make run` inside the nested KVM instance via the provided scripts to correctly snapshot standard execution characteristics into `expected-output.txt`.
- Refactored `README.md` to `status: solid`, updating the content to reflect executed code paths, experiments, limitations, and conceptual validation questions as directed.

## Checks run
- `make test` executed successfully inside the Lima VM, confirming protobuf generation and validating all scripts syntactically and at runtime.
- `make run` manually ran inside the KVM to verify execution flow and output consistency, catching an early network namespace teardown issue.
- `run-in-vm.sh capture` correctly generated `expected-output.txt` complete with environment headers and exact run outcomes.
- Checked formatting rules: removed emojis, em/en-dashes, enforced strict single-sentence-per-line.

## Unverified/assumptions
- `latency_test.sh` requires implicit `sudo` execution for traffic control tools. It is assumed the user environment allows `sudo ip` execution without a blocking interactive password prompt.
- Network throughput metrics might differ dramatically based on real underlying host architectures; `tc` degradation is highlighted conceptually.
