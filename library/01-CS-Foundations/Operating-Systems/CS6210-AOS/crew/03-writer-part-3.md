# Crew brief: Part 3 (distributed systems, objects, and middleware, Lessons 5-6)

Read `00-STANDARD.md` in this folder first; it holds the rules, sources, and quality bar.

## You own (and only these files)

- `AOS/Part-3-Distributed-Systems/L05a-Distributed-Systems-Definitions.md` (5 concepts; sources: slides L05a; Lamport paper)
- `AOS/Part-3-Distributed-Systems/L05b-Lamport-Clocks.md` (9 concepts; sources: slides L05b; Lamport paper)
- `AOS/Part-3-Distributed-Systems/L05c-Latency-Limits.md` (7 concepts; sources: slides L05c; Thekkath and Levy; Firefly RPC)
- `AOS/Part-3-Distributed-Systems/L05d-Active-Networks.md` (10 concepts; sources: slides L05d; Wetherall paper; x-kernel)
- `AOS/Part-3-Distributed-Systems/L05e-Systems-from-Components.md` (7 concepts; sources: slides L05e; Ensemble paper)
- `AOS/Part-3-Distributed-Systems/L06a-Spring-Operating-System.md` (10 concepts; sources: slides L06a; Spring and Subcontract papers)
- `AOS/Part-3-Distributed-Systems/L06b-Java-RMI.md` (8 concepts; sources: slides L06b; Java distributed object model paper)
- `AOS/Part-3-Distributed-Systems/L06c-Enterprise-Java-Beans.md` (7 concepts; sources: slides L06c; EJB performance paper)
- `AOS/Papers/L05-Time-Clocks-Ordering.md` - Time, Clocks, and the Ordering of Events in a Distributed System (CACM 1978; required)
- `AOS/Papers/L05-Limits-Low-Latency.md` - Limits to Low-Latency Communication on High-Speed Networks (TOCS 1993; required)
- `AOS/Papers/L05-x-Kernel.md` - The x-Kernel: An Architecture for Implementing Network Protocols (IEEE TSE 1991; required)
- `AOS/Papers/L05-Active-Networks-ANTS.md` - Active Networks: Vision and Reality: Lessons from a Capsule-based System (SOSP 1999; required)
- `AOS/Papers/L05-Ensemble-Systems-from-Components.md` - Building Reliable, High-Performance Communication Systems from Components (SOSP 1999; required)
- `AOS/Papers/L05-Firefly-RPC.md` - Performance of the Firefly RPC (SOSP 1989; partial)
- `AOS/Papers/L06-Spring-Overview.md` - An Overview of the Spring System (Compcon 1994; required)
- `AOS/Papers/L06-Subcontract.md` - Subcontract: A Flexible Base for Distributed Programming (SOSP 1993; required)
- `AOS/Papers/L06-Java-Distributed-Object-Model.md` - A Distributed Object Model for the Java System (USENIX COOTS 1996; required)
- `AOS/Papers/L06-EJB-Performance.md` - Performance and Scalability of EJB Applications (OOPSLA 2002; required)
- `AOS/Practice/Practice-L05.md`
- `AOS/Practice/Practice-L06.md`
- `AOS/Cheatsheets/Part-3-Cheatsheet.md` (new) and a link to it from `AOS/Part-3-Distributed-Systems/README.md`

## Specific expectations

Include a fully worked Lamport mutual exclusion trace with message counts (3(N-1) and the optimizations), the physical clock conditions with numbers, an RPC latency budget table from Thekkath and Levy, the ANTS capsule flow as a sequence diagram, the Ensemble design cycle (IOA, OCaml, NuPrl), Spring doors and subcontract as diagrams, Java RMI layers, and the three EJB design alternatives with their trade-offs.

## Done means

- Every concept row of your lessons and every paper row of your papers passes `python3 tools/check_aos_coverage.py --verbose`, except problems that only name a lab Makefile owned by the lab crew.
- All your notes are `status: solid`; links, style, and PII checks pass; tool tests pass.
- Report what you could not verify.
