# Crew brief: Part 5 (internet scale, real time, and security, Lessons 9-11) and the optional papers

Read `00-STANDARD.md` in this folder first; it holds the rules, sources, and quality bar.

## You own (and only these files)

- `AOS/Part-5-Internet-Scale-Real-Time-and-Security/L09a-Giant-Scale-Services.md` (10 concepts; sources: slides L09a; Brewer paper; Google cluster paper)
- `AOS/Part-5-Internet-Scale-Real-Time-and-Security/L09b-MapReduce.md` (9 concepts; sources: slides L09b; MapReduce paper)
- `AOS/Part-5-Internet-Scale-Real-Time-and-Security/L09c-Content-Delivery-Networks.md` (10 concepts; sources: slides L09c; Coral and Dynamo papers)
- `AOS/Part-5-Internet-Scale-Real-Time-and-Security/L10a-TS-Linux.md` (9 concepts; sources: syllabus Lesson 10; time-sensitive Linux paper)
- `AOS/Part-5-Internet-Scale-Real-Time-and-Security/L10b-Persistent-Temporal-Streams.md` (7 concepts; sources: syllabus Lesson 10; PTS paper; Yima)
- `AOS/Part-5-Internet-Scale-Real-Time-and-Security/L11a-Principles-of-Information-Security.md` (13 concepts; sources: syllabus Lesson 11; Saltzer and Schroeder)
- `AOS/Part-5-Internet-Scale-Real-Time-and-Security/L11b-Security-in-the-Andrew-System.md` (11 concepts; sources: syllabus Lesson 11; AFS security paper)
- `AOS/Papers/L09-MapReduce.md` - MapReduce: Simplified Data Processing on Large Clusters (OSDI 2004; required)
- `AOS/Papers/L09-Giant-Scale-Services.md` - Lessons from Giant-Scale Services (IEEE Internet Computing 2001; partial)
- `AOS/Papers/L09-Web-Search-for-a-Planet.md` - Web Search for a Planet: The Google Cluster Architecture (IEEE Micro 2003; partial)
- `AOS/Papers/L09-Coral.md` - Democratizing Content Publication with Coral (NSDI 2004; required)
- `AOS/Papers/L09-Dynamo.md` - Dynamo: Amazon's Highly Available Key-value Store (SOSP 2007; required)
- `AOS/Papers/L09-Web-Services-SOAP-WSDL-UDDI.md` - Unraveling the Web Services Web: An Introduction to SOAP, WSDL, and UDDI (IEEE Internet Computing 2002; self-study)
- `AOS/Papers/L09-Next-Step-in-Web-Services.md` - The Next Step in Web Services (CACM 2003; self-study)
- `AOS/Papers/L10-Time-Sensitive-Commodity-OS.md` - Supporting Time-Sensitive Applications on a Commodity OS (OSDI 2002; required)
- `AOS/Papers/L10-Virtualize-Everything-but-Time.md` - Virtualize Everything but Time (OSDI 2010; required)
- `AOS/Papers/L10-Persistent-Temporal-Streams.md` - Persistent Temporal Streams (Middleware 2009; required)
- `AOS/Papers/L10-Yima.md` - Yima: A Second-Generation Continuous Media Server (IEEE Computer 2002; required)
- `AOS/Papers/L11-Protection-Control-of-Information.md` - The Protection of Information in Computer Systems (Proceedings of the IEEE 1975; required)
- `AOS/Papers/L11-Andrew-Security.md` - Integrating Security in a Large Distributed System (TOCS 1989; required)
- `AOS/Papers/Optional-HYDRA-Protection.md` - Protection in the HYDRA Operating System (SOSP 1975; optional)
- `AOS/Papers/Optional-KSR-1-Scalability.md` - Scalability Study of the KSR-1 (Parallel Computing 1996; optional)
- `AOS/Papers/Optional-Multikernel.md` - The Multikernel: A New OS Architecture for Scalable Multicore Systems (SOSP 2009; optional)
- `AOS/Papers/Optional-Virtual-Power.md` - VirtualPower: Coordinated Power Management in Virtualized Enterprise Systems (SOSP 2007; optional)
- `AOS/Papers/Optional-MashupOS.md` - Protection and Communication Abstractions for Web Browsers in MashupOS (SOSP 2007; optional)
- `AOS/Papers/Optional-Illinois-Browser-OS.md` - Trust and Protection in the Illinois Browser Operating System (OSDI 2010; optional)
- `AOS/Papers/Optional-Cluster-Based-Network-Services.md` - Cluster-Based Scalable Network Services (SOSP 1997; optional)
- `AOS/Papers/Optional-Porcupine.md` - Manageability, Availability, and Performance in Porcupine: A Highly Scalable, Cluster-based Mail Service (SOSP 1999; optional)
- `AOS/Papers/Optional-LATE-MapReduce-Heterogeneous.md` - Improving MapReduce Performance in Heterogeneous Environments (OSDI 2008; optional)
- `AOS/Papers/Optional-Mach.md` - Mach: A New Kernel Foundation for UNIX Development (USENIX Summer 1986; optional)
- `AOS/Papers/Optional-Haystack.md` - Finding a Needle in Haystack: Facebook's Photo Storage (OSDI 2010; optional)
- `AOS/Practice/Practice-L09.md`
- `AOS/Practice/Practice-L10.md`
- `AOS/Practice/Practice-L11.md`
- `AOS/Cheatsheets/Part-5-Cheatsheet.md` (new) and a link to it from `AOS/Part-5-Internet-Scale-Real-Time-and-Security/README.md`

## Specific expectations

Give the DQ principle with worked numbers (replication versus partitioning under node loss, harvest and yield), MapReduce execution with failure and straggler handling (model only, honor code), Coral's sloppy DHT and distance-halving routing with a diagram, Dynamo quorums with an N, R, W example, TS-Linux timers with overshoot numbers, PTS channel API semantics, all eight Saltzer and Schroeder principles with modern examples, and the Andrew login and RPC handshake as a sequence diagram with nonces and keys. Write the 11 optional paper notes (marked optional, not tested) at the same bar but shorter.

## Done means

- Every concept row of your lessons and every paper row of your papers passes `python3 tools/check_aos_coverage.py --verbose`, except problems that only name a lab Makefile owned by the lab crew.
- All your notes are `status: solid`; links, style, and PII checks pass; tool tests pass.
- Report what you could not verify.
