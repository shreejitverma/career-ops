# Crew brief: Part 2 (parallel systems, Lesson 4)

Read `00-STANDARD.md` in this folder first; it holds the rules, sources, and quality bar.

## You own (and only these files)

- `AOS/Part-2-Parallel-Systems/L04a-Shared-Memory-Machines.md` (11 concepts; sources: slides L04a)
- `AOS/Part-2-Parallel-Systems/L04b-Synchronization.md` (12 concepts; sources: slides L04b; Mellor-Crummey and Scott)
- `AOS/Part-2-Parallel-Systems/L04c-Barrier-Synchronization.md` (7 concepts; sources: slides L04c; Mellor-Crummey and Scott)
- `AOS/Part-2-Parallel-Systems/L04d-Lightweight-RPC.md` (6 concepts; sources: slides L04d; LRPC paper)
- `AOS/Part-2-Parallel-Systems/L04e-Scheduling.md` (11 concepts; sources: slides L04e; cache affinity and Fedorova papers)
- `AOS/Part-2-Parallel-Systems/L04f-Shared-Memory-Multiprocessor-OS.md` (15 concepts; sources: slides L04f; Tornado, Corey, Cellular Disco papers)
- `AOS/Papers/L04-MCS-Scalable-Synchronization.md` - Algorithms for Scalable Synchronization on Shared-Memory Multiprocessors (TOCS 1991; required)
- `AOS/Papers/L04-LRPC.md` - Lightweight Remote Procedure Call (TOCS 1990; required)
- `AOS/Papers/L04-Cache-Affinity-Scheduling.md` - Using Processor-Cache Affinity Information in Shared Memory Multiprocessor Scheduling (IEEE TPDS 1993; partial)
- `AOS/Papers/L04-Multithreaded-Chip-Multiprocessors.md` - Performance of Multithreaded Chip Multiprocessors and Implications for Operating System Design (USENIX ATC 2005; required)
- `AOS/Papers/L04-Tornado.md` - Tornado: Maximizing Locality and Concurrency in a Shared Memory Multiprocessor Operating System (OSDI 1999; required)
- `AOS/Papers/L04-Corey.md` - Corey: An Operating System for Many Cores (OSDI 2008; partial)
- `AOS/Papers/L04-Cellular-Disco.md` - Cellular Disco: Resource Management Using Virtual Clusters on Shared-Memory Multiprocessors (SOSP 1999; partial)
- `AOS/Practice/Practice-L04.md`
- `AOS/Cheatsheets/Part-2-Cheatsheet.md` (new) and a link to it from `AOS/Part-2-Parallel-Systems/README.md`

## Specific expectations

This Part is the heaviest on Test 1. For every lock and barrier algorithm give: pseudocode in the style of the MCS paper (cited), a step trace for 3-4 processors, bus or network transactions per acquisition or episode, space, and fairness. Barrier algorithms are explained, traced, and compared only (honor code: no C, OpenMP, or MPI implementations anywhere). Cover the scheduling policies with a numeric example of cache affinity, Fedorova's multithreaded-chip results, and Tornado clustered objects with a diagram of the object translation path. Also write Cheatsheets/Comparison-Locks-and-Barriers.md.

## Done means

- Every concept row of your lessons and every paper row of your papers passes `python3 tools/check_aos_coverage.py --verbose`, except problems that only name a lab Makefile owned by the lab crew.
- All your notes are `status: solid`; links, style, and PII checks pass; tool tests pass.
- Report what you could not verify.
