# Report for L04f: Shared Memory Multiprocessor OS

- Replaced all `> [!todo] Seed` callouts with comprehensive content based on the provided slides and papers (Tornado, Corey, Cellular Disco).
- Added a TL;DR and measurable learning outcomes.
- Expanded each core concept heading to strictly over 250 characters, complete with definition callouts.
- Included a Mermaid sequence diagram for the step-by-step mechanism of Tornado's in-core page fault handler.
- Added a worked example with arithmetic calculating the overhead of resolving a clustered object reference miss in Tornado.
- Included a comparison table evaluating Tornado, Corey, Cellular Disco, and Traditional OS architectures.
- Added paper deep dives for all listed papers, integrating links to their respective paper notes.
- Included 'Modern descendants' (RCU, per-CPU structures, KVM/hypervisors) and 'Pitfalls and exam traps' warning callouts.
- Ran `python3 tools/check_aos_coverage.py --lesson L04f --verbose` to confirm no 'seed', 'no heading', or 'under 250' problems remain. (The checker reported missing lab/practice citations, which is expected per the supervisor's notes).
- Committed the file `01-CS-Foundations/Operating-Systems/AOS/Part-2-Parallel-Systems/L04f-Shared-Memory-Multiprocessor-OS.md` with a conventional commit message.
- Remained within honor code boundaries: no code implementations for vCPU schedulers, memory coordinators, barriers, RPC or MapReduce were provided.
