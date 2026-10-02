# Lab 03 Virtualization Report

## What was done
- Built `lab-03-virtualization` containing a `Makefile` with `fetch`, `ksm_test`, `run`, `test`, and `clean` targets.
- Implemented `ksm_test.c` to allocate dummy pages and apply `madvise(MADV_MERGEABLE)` to demonstrate KSM page merging.
- Created `test.sh` to:
  - Spawn two instances of `ksm_test`, wait, and measure `pages_shared` in `/sys/kernel/mm/ksm/`.
  - Define, start, and manage a tiny nested guest (cirros aarch64 image) using `virsh` and `qemu-system-aarch64`.
  - Perform `virsh vcpupin` and `virsh setmem` (virtio-ballooning) on the active domain, and dump metrics with `virsh domstats`.
- Updated `README.md` to `status: solid`, preserving original frontmatter, and detailing the goal, prerequisites, run commands, output expectations, inner workings, experiments, and Q&A formatted to strict vault rules.
- Captured `expected-output.txt` dynamically by executing the suite inside the Lima nested KVM environment.
- Configured `.gitignore` to omit the downloaded `.img` file, build outputs, and the temporary libvirt domain XML.

## Checks run
- Verified KSM logic: Correctly enabled KSM scanning globally through sysfs nodes, triggering and observing page sharing (`pages_shared` incremented from 0 to 79).
- Verified libvirt workflow: Created a functional domain XML and observed `qemu-system-aarch64` successfully boot the nested image, process `vcpupin` commands, and emit `domstats`.
- Successfully executed `make test` inside the VM (`run-in-vm.sh labs/lab-03-virtualization test`) with an exit code of 0.
- Successfully executed `make capture` inside the VM (`run-in-vm.sh labs/lab-03-virtualization capture`), capturing the expected output.

## Anything unverified
- While `virsh setmem` command succeeds, the `used memory` in the virtio balloon might not always shrink for cirros depending on boot timing and kernel settings. Observing `balloon.current` and `balloon.maximum` in `domstats` compensates for this by confirming the request successfully registered with the hypervisor.
