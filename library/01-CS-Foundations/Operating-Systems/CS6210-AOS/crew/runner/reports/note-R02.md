# Note R02 Generation Report

## What was done

- Replaced every `> [!todo] Seed` callout in `01-CS-Foundations/Operating-Systems/AOS/Part-0-Refresher/R02-Architecture-Storage-and-Networking.md`.
- Kept the five concept headings and the `<!-- coverage: R02-0N -->` comments verbatim, and set `status: solid`.
- Wrote the TL;DR, measurable learning outcomes, and the motivation from the prerequisite list (SMP versus NUMA, inodes, block devices, the path from an application to a NIC) and diagnostic item 7 (Linux protocol layers, including why ports exist).
- Each concept has a definition callout, the reason the mechanism exists, and a table or ASCII figure.
- Mechanisms include a pathname walk, a buffered write, a TCP send sequence diagram, a page-cache state diagram, and a path-walk flowchart.
- Worked examples check NUMA latency and bandwidth, classic indirect-block counts for a 5 MiB file, an ext-family inode-table location, TCP segment and frame bytes, and the NAPI interrupt budget at 10 Gbit/s.
- Comparison table covers floor plans, inode maps, I/O styles, and receive paths.
- No paper is assigned to this lesson, so the paper section points at later notes (L04a, L03c, L05c, L07c, Dynamo, L09a) instead of inventing one.
- Modern descendants stay on this lesson's path: ccNUMA and `numa_balancing`, EEVDF inside NUMA sched domains, qspinlock, CXL, blk-mq, io_uring, virtio, EPT/NPT, KSM, XDP/eBPF, RCU walks, unikernels, seL4, and Raft-era and Dynamo-style stores.
- Committed only this path on `aos/writer-part-0-1` as `639102e1`, message `docs(aos): write the R02 architecture, storage, and networking note`.
- Did not push.

## Checks run

- `python3 tools/check_aos_coverage.py --lesson R02 --verbose`.
- The note produced no `seed`, `no heading`, or `under 250` problems.
- The five remaining rows are `missing labs/lab-00-refresher/Makefile` and `Practice/Practice-R.md does not cite R02-0N`, which belong to other jobs.
- Python scan of the note: no non-ASCII characters, no em dash or en dash, no leftover seed callout, and all five coverage comments present.
- Worked-example integers were recomputed in Python before they were written (inode blocks, inode 20000 placement, 4270 frame bytes, 625/21 core-seconds, 1953125 pages).
- Further-reading URLs were checked with HTTP HEAD and returned 200, including the NUMA policy page, VFS, ext4 inodes, blk-mq, NAPI, scaling, segmentation offloads, eBPF, AF_XDP, virtio kernel doc, virtio 1.3 spec, CXL, RCU, `io_uring_setup(2)`, `numa_balancing` in the kernel sysctl page, and `sched-eevdf.html`.

## Assumptions

- R02 has an empty `papers` list, so there is no paper deep dive to write.
- The 80 ns / 160 ns / 40 GB/s / 16 GB/s / 10 GB/s NUMA figures are worked inputs so the ratios come out exact.
- They are not a measurement of a named CPU.
- The inode-table example uses the usual ext4 relationship (4 KiB blocks, 256-byte inodes, 32768 blocks per group, one inode per 16384 bytes) as stated inputs.
- A particular volume formatted with other `mke2fs` settings will land inode 20000 in a different group.

## Unverified

- Mermaid and callouts were not opened in Obsidian.
- Lab Makefile and Practice R citations were left untouched on purpose.
- EEVDF is described as the current fair class, with the replacement starting in Linux 6.6, matching `docs.kernel.org/scheduler/sched-eevdf.html` and the RHEL 10 kernel notes.
- That kernel page also says the 6.6 change began as an option.
- The note does not claim a specific later version removed the last CFS tunable.
