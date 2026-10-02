# Crew brief: labs lab-00-refresher to lab-12-components

Read `00-STANDARD.md` in this folder first.

## Environment

- Lima VM `aos` (Ubuntu 24.04 arm64, 8 vCPUs, nested KVM). Details and verified capabilities: `AOS/labs/setup/README.md`.
- Run any lab from your checkout with `AOS/labs/setup/run-in-vm.sh <lab-dir> test` and capture output with `... capture`.
- No hardware PMU counters in the VM: measure with `clock_gettime(CLOCK_MONOTONIC)` or the ARM virtual counter (`cntvct_el0`), report medians over repeated runs, and say so. Use `perf` software events, tracepoints, kprobes, uprobes, and bpftrace freely.
- One NUMA node only: explain NUMA effects, do not fake measurements.

## Every lab must have

- `README.md` (keep the seed frontmatter; `status: solid` when done): goal, the concept ids it exercises, honor-code guard if any, prerequisites, run commands, what you should see (quote real numbers from expected-output.txt), how it works, 3-5 experiments to try with a prediction prompt, and 3-5 folded questions with answers.
- `Makefile` with `all`, `run`, `test`, and `clean`; `make test` exits non-zero on failure and prints PASS lines.
- Source files (C11 with `-Wall -Wextra -O2 -pthread`, or Python 3.12 using `/opt/aos-venv/bin/python` when it needs grpc, pytest, or cryptography), plus shell scripts for command-driven labs (virsh, perf, bpftrace, chrt, tc, unshare).
- `expected-output.txt` captured in the VM by `run-in-vm.sh <lab> capture`.
- `.gitignore` for binaries and build outputs. Never commit a binary, a VM image, or a disk file; download images in a `make fetch` step instead.
- Root-only steps (`sudo` for SCHED_DEADLINE, tc, unshare, KSM sysfs) are explicit in the Makefile and README.

## Your labs

- `AOS/labs/lab-00-refresher/` - Refresher: page faults, TLB, caches, and a pthreads producer-consumer. Lessons: R01, R02, R03.
- `AOS/labs/lab-01-syscall-and-context-switch/` - Border crossings: syscall, context switch, and address space switch costs. Lessons: L01, L02a, L02d.
- `AOS/labs/lab-02-extensibility/` - Safe extensibility today: bpftrace and eBPF, plus application-level paging with userfaultfd. Lessons: L02b, L02c.
- `AOS/labs/lab-03-virtualization/` - KVM and libvirt by hand: lifecycle, vCPU pinning, ballooning, and KSM page sharing. Lessons: L03a, L03b, L03c. Guard: observe and operate only; never write a vCPU scheduler or memory coordinator (Project 1).
- `AOS/labs/lab-04-cache-coherence/` - Coherence traffic, false sharing, and memory-ordering litmus tests. Lessons: L04a.
- `AOS/labs/lab-05-spinlocks/` - Spinlock zoo: TAS, TTAS, backoff, ticket, Anderson, and MCS in C11. Lessons: L04b.
- `AOS/labs/lab-06-barriers/` - Barrier algorithms: library barrier costs and a round and message simulator. Lessons: L04c. Guard: no C, OpenMP, or MPI implementation of any barrier algorithm (Project 2).
- `AOS/labs/lab-07-rpc-costs/` - Where RPC time goes: copies, crossings, and zero-copy on one machine. Lessons: L04d, L05c. Guard: no gRPC store or vendor service (Project 3).
- `AOS/labs/lab-08-scheduling/` - Affinity scheduling: taskset, perf sched, chrt, cgroups, and a policy simulator. Lessons: L04e.
- `AOS/labs/lab-09-scalable-structures/` - Scalable kernel-style structures: per-CPU counters, read-mostly data, and false sharing. Lessons: L04f.
- `AOS/labs/lab-10-clocks-and-mutex/` - Lamport and vector clocks, total order, and Lamport mutual exclusion. Lessons: L05a, L05b.
- `AOS/labs/lab-11-network-latency/` - Network latency budgets: ping, iperf3, tc netem, and capsule routing. Lessons: L05d.
- `AOS/labs/lab-12-components/` - Micro-protocol stacks from components and common-path optimization. Lessons: L05e.

## Lab ideas that are in scope (pick and extend; keep each lab to what runs in under 2 minutes)

- lab-00: count minor and major faults with getrusage around mmap touches, read /proc/self/pagemap, a strided-access cache and TLB timing curve, page-coloring discussion, a pthreads producer-consumer with a bounded buffer and condition variables (the diagnostic test's example).
- lab-01: getpid and empty-syscall loop timing, pipe ping-pong context-switch cost, `perf bench sched pipe`, thread versus process switch, cross-address-space versus same-address-space handoff; relate to Mach and L3 numbers.
- lab-02: bpftrace one-liners and a small eBPF program as a verified in-kernel extension (SPIN analogy), and userfaultfd application-level page fault handling (Exokernel analogy).
- lab-03: boot a tiny nested guest with qemu -accel kvm, define it in libvirt, `virsh vcpupin`, `virsh setmem` with virtio-balloon, `virsh domstats` readings, and KSM merging two processes' identical pages via madvise(MADV_MERGEABLE) while watching /sys/kernel/mm/ksm. Observe only.
- lab-04: false sharing timing (padded versus unpadded counters), coherence ping-pong latency between two threads, and store-buffering and message-passing litmus tests with C11 atomics (relaxed versus seq_cst; ARM shows weak behavior).
- lab-05: TAS, TTAS, TTAS with exponential backoff, ticket, Anderson array, and MCS locks in C11 atomics with a scaling benchmark over 1-8 threads and a correctness test (counter equals expected).
- lab-06: time pthread_barrier_wait, `#pragma omp barrier`, and MPI_Barrier as black boxes; plus a Python simulator that computes rounds, messages, and critical-path length for counting, tree, MCS tree, tournament, and dissemination barriers for N = 2..64 and plots them. No barrier implementations.
- lab-07: same-machine RPC paths compared: pipe, UNIX socket, and shared memory with a futex handoff; count copies and syscalls with `strace -c`; `sendfile` versus read and write.
- lab-08: cache-affinity effect with taskset pinning versus migration, `perf sched latency`, `chrt` policies, cgroup v2 cpu.weight shares, and a Python simulator of FCFS, fixed, last processor, and minimum intervening policies.
- lab-09: per-CPU counters versus a shared atomic versus a locked counter, a read-mostly structure with an RCU-like copy-update and grace period (userspace, liburcu optional), and false sharing in a kernel-like structure.
- lab-10: Lamport clock and vector clock simulators with message traces, total order with tie-breaking, Lamport mutual exclusion over simulated channels with message counts, and clock drift.
- lab-11: ping and iperf3 over the loopback and a veth pair, `tc netem` delay and loss injection, marshaling cost (struct.pack versus JSON versus protobuf), and a capsule-routing simulator.
- lab-12: a layered micro-protocol stack in Python (fragmentation, ordering, checksum layers) and a common-path bypass optimization measured.
- lab-13: Java RMI hello with a registry and a remote object, a subcontract-style pluggable invocation layer in Python (singleton versus replicated), and a generic gRPC greeter with sync and async stubs. No store or vendor service.
- lab-14: a global LRU simulator with epochs and min-weight selection over N nodes, and local versus remote page fetch cost over a socket.
- lab-15: page-based user-level DSM in C with mprotect and SIGSEGV, twins and diffs for multiple writers, and a lazy release consistency trace.
- lab-16: RAID-5 parity compute and reconstruct, a log-structured append store with cleaning, and a FUSE file system (fusepy or libfuse) with a write-back cache.
- lab-17: an LRVM-style recoverable segment in C (mmap, set_range undo copies, redo log append, fsync, truncation) with `kill -9` crash injection and recovery tests, plus `fio` fsync latency to motivate RioVista.
- lab-18: two-phase commit with a coordinator log and crash and recovery cases, write-ahead logging versus shadow paging, and a transaction-tree example in the Quicksilver style.
- lab-19: a Python service with replicas versus partitions under node failure and load, measuring yield and harvest (DQ), plus round-robin DNS versus a layer 4 balancer discussion.
- lab-20: word count as a Unix pipeline (map: tr, shuffle: sort, reduce: uniq -c), the same in plain Python functions, and a master-scheduling simulator with failures and backup tasks. No RPC workers, master service, or file sharding framework.
- lab-21: consistent hashing with virtual nodes and load balance stats, Chord-style key-based routing, a Coral sloppy DHT spill simulation showing tree-saturation relief, and Dynamo N, R, W quorums with vector clocks.
- lab-22: cyclictest latency histograms idle and under stress-ng, SCHED_OTHER versus SCHED_FIFO versus SCHED_DEADLINE (sudo), and periodic versus one-shot timer overshoot in C.
- lab-23: a time-indexed stream store in Python (put and get by timestamp, time-range queries, persistence, garbage collection) and a feed-forward versus feedback clock-sync simulation (Virtualize Everything but Time).
- lab-24: capabilities with capsh and getcap, user and mount namespaces with unshare, a seccomp filter in C that kills a forbidden syscall, and an Andrew-style handshake in Python with nonces, session keys, and a replay-attack test.

## Done means

- `make test` passes in the VM for every lab you own; `expected-output.txt` is real; every lab README is `status: solid`.
- Your lab rows pass `python3 tools/check_aos_coverage.py --verbose` (lesson-note problems owned by writers aside).
- Links, style, and PII checks pass; tool tests pass; no binaries tracked (`git ls-files AOS/labs | grep -vE '\.(md|c|h|py|sh|java|proto|txt|yaml|yml|csv|bt|gitignore)$|Makefile'` prints nothing).
