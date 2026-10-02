# Crew brief: Part 0 refresher and Part 1 (OS structure and virtualization)

Read `00-STANDARD.md` in this folder first; it holds the rules, sources, and quality bar.

## You own (and only these files)

- `AOS/Part-0-Refresher/R01-Virtual-Memory-and-Caches.md` (14 concepts; sources: official/prereqs-concepts; diagnostic test)
- `AOS/Part-0-Refresher/R02-Architecture-Storage-and-Networking.md` (5 concepts; sources: official/prereqs-concepts; diagnostic test)
- `AOS/Part-0-Refresher/R03-Concurrency-and-the-Kernel.md` (12 concepts; sources: official/prereqs-concepts; diagnostic test)
- `AOS/Part-1-OS-Structure-and-Virtualization/L01-Introduction-to-AOS.md` (6 concepts; sources: syllabus Lesson 1; OS refresher videos)
- `AOS/Part-1-OS-Structure-and-Virtualization/L02a-OS-Structure-Overview.md` (6 concepts; sources: slides L02a)
- `AOS/Part-1-OS-Structure-and-Virtualization/L02b-SPIN-Approach.md` (10 concepts; sources: slides L02b; SPIN paper)
- `AOS/Part-1-OS-Structure-and-Virtualization/L02c-Exokernel-Approach.md` (11 concepts; sources: slides L02c; Exokernel paper)
- `AOS/Part-1-OS-Structure-and-Virtualization/L02d-L3-Microkernel-Approach.md` (12 concepts; sources: slides L02d; Liedtke papers)
- `AOS/Part-1-OS-Structure-and-Virtualization/L03a-Introduction-to-Virtualization.md` (7 concepts; sources: slides L03a)
- `AOS/Part-1-OS-Structure-and-Virtualization/L03b-Memory-Virtualization.md` (12 concepts; sources: slides L03b; Xen and ESX papers)
- `AOS/Part-1-OS-Structure-and-Virtualization/L03c-CPU-and-Device-Virtualization.md` (9 concepts; sources: slides L03c; Xen paper)
- `AOS/Papers/L02-SPIN.md` - Extensibility, Safety and Performance in the SPIN Operating System (SOSP 1995; required)
- `AOS/Papers/L02-Exokernel.md` - Exokernel: An Operating System Architecture for Application-Level Resource Management (SOSP 1995; required)
- `AOS/Papers/L02-On-Microkernel-Construction.md` - On Micro-Kernel Construction (SOSP 1995; required)
- `AOS/Papers/L02-Improved-Address-Space-Switching.md` - Improved Address-Space Switching on Pentium Processors by Transparently Multiplexing User Address Spaces (GMD TR 933, 1995; self-study)
- `AOS/Papers/L03-Xen.md` - Xen and the Art of Virtualization (SOSP 2003; required)
- `AOS/Papers/L03-VMware-ESX-Memory.md` - Memory Resource Management in VMware ESX Server (OSDI 2002; required)
- `AOS/Practice/Practice-R.md`
- `AOS/Practice/Practice-L01.md`
- `AOS/Practice/Practice-L02.md`
- `AOS/Practice/Practice-L03.md`
- `AOS/Cheatsheets/Part-0-Cheatsheet.md` (new) and a link to it from `AOS/Part-0-Refresher/README.md`
- `AOS/Cheatsheets/Part-1-Cheatsheet.md` (new) and a link to it from `AOS/Part-1-OS-Structure-and-Virtualization/README.md`

## Specific expectations

The refresher notes must answer every diagnostic-test question in the official folder in your own words (VIPT cache walk, segmentation versus paging, page-fault path, working set terms, page coloring, context-switch costs, network stack layers) and include the pthreads producer-consumer idea in prose (lab-00 holds the code). For L02 give real border-crossing numbers from the papers (Mach versus L3 IPC costs, SPIN and Exokernel microbenchmarks) with citations. For L03 cover shadow page tables, nested paging, ballooning, content-based sharing, and the idle memory tax with a worked example.

## Done means

- Every concept row of your lessons and every paper row of your papers passes `python3 tools/check_aos_coverage.py --verbose`, except problems that only name a lab Makefile owned by the lab crew.
- All your notes are `status: solid`; links, style, and PII checks pass; tool tests pass.
- Report what you could not verify.
