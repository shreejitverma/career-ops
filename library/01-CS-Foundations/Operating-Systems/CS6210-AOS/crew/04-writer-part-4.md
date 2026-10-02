# Crew brief: Part 4 (distributed subsystems, failures, and recovery, Lessons 7-8)

Read `00-STANDARD.md` in this folder first; it holds the rules, sources, and quality bar.

## You own (and only these files)

- `AOS/Part-4-Distributed-Subsystems-and-Recovery/L07a-Global-Memory-Systems.md` (13 concepts; sources: slides L07a; GMS paper)
- `AOS/Part-4-Distributed-Subsystems-and-Recovery/L07b-Distributed-Shared-Memory.md` (12 concepts; sources: slides L07b; TreadMarks paper)
- `AOS/Part-4-Distributed-Subsystems-and-Recovery/L07c-Distributed-File-Systems.md` (13 concepts; sources: slides L07c; xFS and Coda papers)
- `AOS/Part-4-Distributed-Subsystems-and-Recovery/L08a-Lightweight-Recoverable-Virtual-Memory.md` (9 concepts; sources: syllabus Lesson 8; LRVM paper)
- `AOS/Part-4-Distributed-Subsystems-and-Recovery/L08b-RioVista.md` (6 concepts; sources: syllabus Lesson 8; Rio Vista paper)
- `AOS/Part-4-Distributed-Subsystems-and-Recovery/L08c-Quicksilver.md` (10 concepts; sources: syllabus Lesson 8; Quicksilver paper; System R; OS transactions)
- `AOS/Papers/L07-GMS.md` - Implementing Global Memory Management in a Workstation Cluster (SOSP 1995; required)
- `AOS/Papers/L07-TreadMarks.md` - TreadMarks: Shared Memory Computing on Networks of Workstations (IEEE Computer 1996; required)
- `AOS/Papers/L07-xFS-Serverless-NFS.md` - Serverless Network File Systems (TOCS 1996; required)
- `AOS/Papers/L07-Coda.md` - Coda: A Highly Available File System for a Distributed Workstation Environment (IEEE Trans. Computers 1990; partial)
- `AOS/Papers/L08-LRVM.md` - Lightweight Recoverable Virtual Memory (SOSP 1993; required)
- `AOS/Papers/L08-Rio-Vista.md` - Free Transactions with Rio Vista (SOSP 1997; required)
- `AOS/Papers/L08-Quicksilver.md` - Recovery Management in QuickSilver (TOCS 1988; required)
- `AOS/Papers/L08-System-R-Recovery-Manager.md` - The Recovery Manager of the System R Database Manager (ACM Computing Surveys 1981; self-study)
- `AOS/Papers/L08-OS-Transactions.md` - Operating System Transactions (SOSP 2009; partial)
- `AOS/Papers/L08-Percolator.md` - Large-scale Incremental Processing Using Distributed Transactions and Notifications (OSDI 2010; partial)
- `AOS/Practice/Practice-L07.md`
- `AOS/Practice/Practice-L08.md`
- `AOS/Cheatsheets/Part-4-Cheatsheet.md` (new) and a link to it from `AOS/Part-4-Distributed-Subsystems-and-Recovery/README.md`

## Specific expectations

Cover all four GMS page-fault cases with a state table, the epoch and min-weight age management math, TreadMarks lazy release consistency with twins and diffs drawn step by step, xFS data structures and a client read and write path, LRVM primitives with the undo record and redo log lifecycle and truncation, RioVista's elimination of the redo log, and Quicksilver transaction trees and commit with the shadow graph. No L08 slides exist locally: build L08 from the LRVM, Rio Vista, Quicksilver, System R, TxOS, and Percolator papers and the syllabus.

## Done means

- Every concept row of your lessons and every paper row of your papers passes `python3 tools/check_aos_coverage.py --verbose`, except problems that only name a lab Makefile owned by the lab crew.
- All your notes are `status: solid`; links, style, and PII checks pass; tool tests pass.
- Report what you could not verify.
