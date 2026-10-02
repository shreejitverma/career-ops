"""Build the AOS job queue (jobs.json) with exact sources per job, Test 1 material first."""
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from aos_spec import LABS, LESSONS, PAPERS, PARTS  # noqa: E402

LIB = os.path.expanduser("~/github/career-ops/library/01-CS-Foundations/Operating-Systems/CS6210-AOS")
T = LIB + "/text"
AOS = "01-CS-Foundations/Operating-Systems/AOS"
OUT = sys.argv[1]
DONE_NOTES = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else set()

PAPER_TEXT = {  # slug -> glob under text/papers
    "SPIN": "notes-fork/OS structure/Extensibility*",
    "Exokernel": "papers-fork/*/01_OsStructures/02_Exokernel.txt",
    "On-Microkernel-Construction": "notes-fork/OS structure/On Micro-Kernel*",
    "Improved-Address-Space-Switching": "notes-fork/OS structure/Improved Address*",
    "Xen": "notes-fork/OS structure/Xen and*",
    "VMware-ESX-Memory": "notes-fork/OS structure/Memory Resource*",
    "MCS-Scalable-Synchronization": "notes-fork/Synchronization*/Algorithms for Scalable*",
    "LRPC": "notes-fork/Synchronization*/Lightweight Remote*",
    "Cache-Affinity-Scheduling": "notes-fork/Synchronization*/Using Processor-Cache*",
    "Multithreaded-Chip-Multiprocessors": "notes-fork/Synchronization*/Performance of Multithreaded*",
    "Tornado": "notes-fork/Synchronization*/Maximizing Locality*",
    "Corey": "notes-fork/Synchronization*/Corey*",
    "Cellular-Disco": "notes-fork/Synchronization*/Cellular Disco*",
    "Time-Clocks-Ordering": "notes-fork/Communication*/Time, Clocks*",
    "Limits-Low-Latency": "notes-fork/Communication*/Limits to Low*",
    "x-Kernel": "notes-fork/Communication*/The x-Kernel*",
    "Active-Networks-ANTS": "notes-fork/Communication*/Active Networks*",
    "Ensemble-Systems-from-Components": "notes-fork/Communication*/Building Reliable*",
    "Firefly-RPC": "notes-fork/Communication*/Performance of the Firefly*",
    "Spring-Overview": "notes-fork/Distributed Objects*/An Overview of the Spring*",
    "Subcontract": "notes-fork/Distributed Objects*/Subcontract*",
    "Java-Distributed-Object-Model": "notes-fork/Distributed Objects*/A Distributed Object Model*",
    "EJB-Performance": "notes-fork/Distributed Objects*/Performance and Scalability*",
    "GMS": "notes-fork/Distributed Shared*/Implementing Global*",
    "TreadMarks": "notes-fork/Distributed Shared*/TreadMarks*",
    "xFS-Serverless-NFS": "notes-fork/Distributed Shared*/Serverless*",
    "Coda": "notes-fork/Distributed Shared*/Coda*",
    "LRVM": "notes-fork/Failures*/Lightweight Recoverable*",
    "Rio-Vista": "notes-fork/Failures*/Free Transactions*",
    "Quicksilver": "notes-fork/Failures*/Recovery Management*",
    "System-R-Recovery-Manager": "papers-fork/*/01_FailuresConsistencyAndRecovery/04_SystemRDatabase.txt",
    "OS-Transactions": "notes-fork/Failures*/Operating System Transactions*",
    "Percolator": "notes-fork/Failures*/Large-scale Incremental*",
    "MapReduce": "notes-fork/System Support*/MapReduce*",
    "Giant-Scale-Services": "notes-fork/System Support*/Lessons from Giant*",
    "Web-Search-for-a-Planet": "notes-fork/System Support*/Web Search*",
    "Coral": "notes-fork/System Support*/Democratizing*",
    "Dynamo": "notes-fork/System Support*/Dynamo*",
    "Web-Services-SOAP-WSDL-UDDI": "notes-fork/System Support*/Unraveling*",
    "Next-Step-in-Web-Services": "notes-fork/System Support*/The Next Step*",
    "Time-Sensitive-Commodity-OS": "notes-fork/Real-Time*/Supporting Time*",
    "Virtualize-Everything-but-Time": "notes-fork/Real-Time*/Virtualize*",
    "Persistent-Temporal-Streams": "notes-fork/Real-Time*/Persistent*",
    "Yima": "notes-fork/Real-Time*/Yima*",
    "Protection-Control-of-Information": "notes-fork/Security/Protection and the Control*",
    "Andrew-Security": "notes-fork/Security/Integrating Security*",
    "HYDRA-Protection": "notes-fork/Additional*/Protection in the HYDRA*",
    "KSR-1-Scalability": "notes-fork/Additional*/Scalability Study*",
    "Multikernel": "notes-fork/Additional*/The Multikernel*",
    "Virtual-Power": "notes-fork/Additional*/Virtual Power*",
    "MashupOS": "notes-fork/Additional*/Protection and Communication*",
    "Illinois-Browser-OS": "notes-fork/Additional*/Trust and Protection*",
    "Cluster-Based-Network-Services": "notes-fork/Additional*/Cluster-based*",
    "Porcupine": "notes-fork/Additional*/Manageability*",
    "LATE-MapReduce-Heterogeneous": "notes-fork/Additional*/Improving MapReduce*",
    "Mach": "notes-fork/Additional*/Mach_*",
    "Haystack": "notes-fork/Additional*/Finding a Needle*",
}
SUB_PAPERS = {
    "L02b": ["SPIN"], "L02c": ["Exokernel"], "L02d": ["On-Microkernel-Construction", "Improved-Address-Space-Switching"],
    "L03a": ["Xen"], "L03b": ["VMware-ESX-Memory", "Xen"], "L03c": ["Xen"],
    "L04b": ["MCS-Scalable-Synchronization"], "L04c": ["MCS-Scalable-Synchronization"], "L04d": ["LRPC"],
    "L04e": ["Cache-Affinity-Scheduling", "Multithreaded-Chip-Multiprocessors"],
    "L04f": ["Tornado", "Corey", "Cellular-Disco"],
    "L05a": ["Time-Clocks-Ordering"], "L05b": ["Time-Clocks-Ordering"], "L05c": ["Limits-Low-Latency", "Firefly-RPC"],
    "L05d": ["Active-Networks-ANTS", "x-Kernel"], "L05e": ["Ensemble-Systems-from-Components"],
    "L06a": ["Spring-Overview", "Subcontract"], "L06b": ["Java-Distributed-Object-Model"], "L06c": ["EJB-Performance"],
    "L07a": ["GMS"], "L07b": ["TreadMarks"], "L07c": ["xFS-Serverless-NFS", "Coda"],
    "L08a": ["LRVM"], "L08b": ["Rio-Vista"], "L08c": ["Quicksilver", "System-R-Recovery-Manager", "OS-Transactions", "Percolator"],
    "L09a": ["Giant-Scale-Services", "Web-Search-for-a-Planet"], "L09b": ["MapReduce"], "L09c": ["Coral", "Dynamo"],
    "L10a": ["Time-Sensitive-Commodity-OS", "Virtualize-Everything-but-Time"], "L10b": ["Persistent-Temporal-Streams", "Yima"],
    "L11a": ["Protection-Control-of-Information"], "L11b": ["Andrew-Security"],
}


def ptext(slug):
    hits = sorted(glob.glob(f"{T}/papers/{PAPER_TEXT[slug]}"))
    assert hits, slug
    return hits[0]


def slide(sub):
    hits = glob.glob(f"{T}/slides/{sub}.*.txt")
    return hits[0] if hits else None


def pnote(lesson, slug):
    return f"{AOS}/Papers/{'Optional' if lesson == 'optional' else lesson}-{slug}.md"


jobs = []
OFFICIAL = [f"{LIB}/official/prereqs-concepts.txt", f"{LIB}/official/diagnostic-test.txt", f"{LIB}/official/syllabus-2026-3.txt"]
for part, stem, title, source, lab, concepts in LESSONS:
    sub = stem.split("-")[0]
    note = f"{AOS}/{PARTS[part]}/{stem}.md"
    if note in DONE_NOTES:
        continue
    src = [s for s in [slide(sub)] if s] + [ptext(p) for p in SUB_PAPERS.get(sub, [])]
    if sub.startswith("R") or sub == "L01":
        src += OFFICIAL[:2] if sub.startswith("R") else OFFICIAL[2:]
    jobs.append({"id": f"note-{sub}", "kind": "lesson", "part": part, "targets": [note], "sources": src,
                 "check": sub, "deps": [], "title": title})
by_lesson = {}
for lesson, slug, title, venue, reading, url in PAPERS:
    by_lesson.setdefault(lesson, []).append((slug, title, reading))
for lesson, items in by_lesson.items():
    targets = [pnote(lesson, s) for s, t, r in items if pnote(lesson, s) not in DONE_NOTES]
    if not targets:
        continue
    srcs = [ptext(s) for s, t, r in items if pnote(lesson, s) in targets]
    # split big groups so one job stays small
    for i in range(0, len(targets), 3):
        jobs.append({"id": f"papers-{lesson}-{i // 3 + 1}", "kind": "papers",
                     "part": next((p for p, s, *_ in LESSONS if s.startswith(lesson)), "5"),
                     "targets": targets[i:i + 3], "sources": srcs[i:i + 3], "check": None, "deps": [],
                     "title": f"paper notes {lesson} group {i // 3 + 1}"})
nums = sorted({("R" if s.startswith("R") else s[:3]) for p, s, *_ in LESSONS})
for n in nums:
    notes = [j["id"] for j in jobs if j["kind"] == "lesson" and (j["check"].startswith(n) if n != "R" else j["check"].startswith("R"))]
    paps = [j["id"] for j in jobs if j["kind"] == "papers" and j["id"].startswith(f"papers-{n}-")]
    part = "0" if n == "R" else next(p for p, s, *_ in LESSONS if s.startswith(n))
    jobs.append({"id": f"practice-{n}", "kind": "practice", "part": part, "targets": [f"{AOS}/Practice/Practice-{n}.md"],
                 "sources": [], "check": n, "deps": notes + paps, "title": f"practice set {n}"})
for lab, (title, guard) in LABS.items():
    subs = [s.split("-")[0] for p, s, t, src, l, c in LESSONS if l == lab]
    part = next(p for p, s, t, src, l, c in LESSONS if l == lab)
    jobs.append({"id": lab, "kind": "lab", "part": part, "targets": [f"{AOS}/labs/{lab}/"], "sources": [],
                 "check": None, "deps": [], "title": title, "lessons": subs, "guard": guard})
for part in "012345":
    deps = [j["id"] for j in jobs if j["part"] == part and j["kind"] in ("lesson", "practice")]
    jobs.append({"id": f"cheatsheet-{part}", "kind": "cheatsheet", "part": part,
                 "targets": [f"{AOS}/Cheatsheets/Part-{part}-Cheatsheet.md"], "sources": [], "check": None,
                 "deps": deps, "title": f"Part {part} cheat sheet"})
jobs.append({"id": "cheatsheet-locks-barriers", "kind": "cheatsheet", "part": "2",
             "targets": [f"{AOS}/Cheatsheets/Comparison-Locks-and-Barriers.md"], "sources": [], "check": None,
             "deps": ["note-L04b", "note-L04c"], "title": "locks and barriers comparison"})
# Priority: Test 1 parts (0, 1, 2) first; within a part: lessons, papers, labs, practice, cheat sheets.
KORD = {"lesson": 0, "papers": 1, "lab": 2, "practice": 3, "cheatsheet": 4}
for j in jobs:
    j["prio"] = (0 if j["part"] in "012" else 1, int(j["part"]), KORD[j["kind"]], j["id"])
    j["state"] = "pending"
    j["attempts"] = []
jobs.sort(key=lambda j: j["prio"])
for j in jobs:
    j["prio"] = list(j["prio"])
json.dump(jobs, open(OUT, "w"), indent=1)
from collections import Counter
print(len(jobs), "jobs", Counter(j["kind"] for j in jobs), "| first 12:", [j["id"] for j in jobs[:12]])
