#!/usr/bin/env python3
"""Quota-aware job runner for the CS 6210 AOS vault build-out.

Usage:
    runner.py run            # start lanes; runs until the queue is done or STOP exists
    runner.py status         # job counts, running jobs, provider availability
    touch STOP               # lanes finish their current job and exit

Each lane owns one treehouse worktree and branch. A lane takes the highest-priority runnable job
(dependencies done), picks the first available provider from its preference list (quota-axi
floors), runs the agent headless with a job-specific prompt, verifies the result, commits leftovers,
and merges the lane branch into vault/cs6210-aos and then into the Obsidian vault checkout.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CREW = HERE.parent
JOBS = HERE / "jobs.json"
LOGS = HERE / "logs"
REPORTS = HERE / "reports"
STOP = HERE / "STOP"
VAULT = Path.home() / "github/SDE-Interview-Prep"
POOL = Path.home() / ".treehouse/SDE-Interview-Prep-3215ec"
INTEGRATION = POOL / "1/SDE-Interview-Prep"
AOS = "01-CS-Foundations/Operating-Systems/AOS"
LANES = [  # (name, slot, provider preference)
    ("lane-a", 3, ["grok", "claude", "gemini"]),
    ("lane-b", 4, ["gemini", "claude", "grok"]),
]
FLOORS = {"grok": 6, "gemini": 15, "claude": 35}
CLAUDE_RESET = dt.datetime(2026, 10, 4, 2, 0, tzinfo=dt.timezone.utc)
TIMEOUTS = {"lesson": 3600, "papers": 3600, "practice": 2700, "lab": 5400, "cheatsheet": 1800}
lock = threading.Lock()
cooldown: dict[str, float] = {}


def log(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOGS / "runner.log", "a") as f:
        f.write(line + "\n")


def sh(cmd, cwd=None, timeout=None, check=False):
    r = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"{cmd}: {r.stderr.strip()[-400:]}")
    return r


def load():
    return json.loads(JOBS.read_text())


def save(jobs):
    tmp = JOBS.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, indent=1))
    tmp.replace(JOBS)


# ---------- quota ----------
def quota() -> dict:
    """Parse only the quota[...] table of quota-axi: (provider, scope) -> (percent, runway)."""
    out = sh("quota-axi", timeout=120).stdout
    rows, inside = {}, False
    for line in out.splitlines():
        if not line.startswith(" "):
            inside = line.startswith("quota[")
            continue
        m = re.match(r"\s+(\w+),(\"[^\"]+\"|[^,]+),(\d+|unknown),([^,]+),([^,]+),", line)
        if inside and m and m.group(1) in ("claude", "grok", "agy"):
            rows[(m.group(1), m.group(2).strip('"'))] = (m.group(3), m.group(5))
    return rows


def available(provider: str, q: dict) -> bool:
    if cooldown.get(provider, 0) > time.time():
        return False
    key = {"grok": ("grok", "all_products"), "gemini": ("agy", "gemini"), "claude": ("claude", "all_models")}[provider]
    pct, runway = q.get(key, ("unknown", "unknown"))
    if runway == "exhausted_now":
        return False
    if provider == "claude" and dt.datetime.now(dt.timezone.utc) < CLAUDE_RESET:
        return False
    if pct == "unknown":
        return provider == "gemini"
    return int(pct) >= FLOORS[provider]


# ---------- prompts ----------
def lab_idea(lab: str) -> str:
    for brief in ("06-labs-a.md", "07-labs-b.md"):
        for line in (CREW / brief).read_text().splitlines():
            if line.startswith(f"- {lab[:6]}:"):
                return line[2:]
    return ""


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def prompt(job, lane_wt: Path, branch: str, failures: str) -> str:
    std = (CREW / "00-STANDARD.md").read_text()
    common = section(std, "Honor code and privacy (hard rules)")
    out = [
        f"You are an autonomous writer for the CS 6210 Advanced Operating Systems section of a public Obsidian vault.",
        f"Your git worktree is {lane_wt} on branch {branch}. Work only there. No human is available: never ask questions, decide and note assumptions in your report.",
        f"Job {job['id']}: {job['title']}. Edit ONLY these paths: {', '.join(job['targets'])}.",
        "Do not edit README files, _coverage.csv, 00-Coverage.md, or anything else; the supervisor integrates.",
        "Vault style (CI-enforced): no emojis, no em or en dashes (use '-'), one full sentence per physical line in prose, ASCII punctuation, frontmatter keys kept as in the stub.",
        "Honor code and privacy (hard limits):\n" + common,
        f"When the work is complete: git add only your target paths and commit with a conventional message (no co-author lines, never --no-verify, never push). "
        f"Then write a short report to {REPORTS}/{job['id']}.md (what you did, checks run, anything unverified) and stop.",
    ]
    if job["kind"] == "lesson":
        out += ["Task: bring the lesson note to status: solid per this bar:", section(std, "Lesson note bar (status: solid)"),
                "Read the existing stub first: every concept heading and coverage comment is already there; keep them verbatim and replace every seed callout.",
                "Read these sources (only these, plus your own knowledge; never copy text verbatim):\n" + "\n".join(job["sources"]),
                f"Verify with: python3 tools/check_aos_coverage.py --lesson {job['check']} --verbose (your note must produce no 'seed', 'no heading', or 'under 250' problems; lab and practice problems belong to other jobs)."]
    elif job["kind"] == "papers":
        out += ["Task: bring each paper note to status: solid per this bar:", section(std, "Paper note bar (status: solid)"),
                "Source text for each paper, in the same order as the targets (if a text is empty or garbled, rely on your knowledge of the paper and say so in the note):\n" + "\n".join(job["sources"]),
                "Keep the stub frontmatter keys; fill authors; keep the Related links."]
    elif job["kind"] == "practice":
        out += ["Task: write the practice set per this bar:", section(std, "Practice bar"),
                f"Cite every concept id of lesson {job['check']} and every non-optional paper id (P-<slug>) of lesson {job['check']} at least once; the ids are in {AOS}/_coverage.csv (read it, do not edit it).",
                f"Read the lesson notes and paper notes for {job['check']} under {AOS} first so the questions match them.",
                f"Verify with: python3 tools/check_aos_coverage.py --lesson {job['check']} --verbose (no 'does not cite' problems)."]
    elif job["kind"] == "lab":
        lab = Path(job["targets"][0]).name
        brief = (CREW / "06-labs-a.md").read_text()
        out += ["Task: build the lab to status: solid. Lab rules:", section(brief, "Environment"), section(brief, "Every lab must have"),
                f"Lab scope: {lab_idea(lab)}", f"Lessons it serves: {', '.join(job['lessons'])} (read those lesson notes under {AOS} for vocabulary).",
                (f"Honor-code guard for this lab: {job['guard']}." if job["guard"] else ""),
                f"Run inside the VM with {AOS}/labs/setup/run-in-vm.sh {AOS}/labs/{lab} test, then capture real output with ... capture. make test must pass."]
    elif job["kind"] == "cheatsheet":
        out += ["Task: write the cheat sheet per this bar:", section(std, "Cheat sheets"),
                f"Build it from the notes under {AOS} for this Part (and the lock and barrier notes for the comparison sheet). Frontmatter: type: playbook, track: [sde, distinguished], level:, status: solid, last_reviewed:, sources: [], course: cs6210, tags: [cs6210, cs6210/cheatsheet]."]
    if failures:
        out += ["A previous attempt at this job failed verification with these problems; fix them:\n" + failures]
    return "\n\n".join(x for x in out if x)


def command(provider: str, prompt_file: Path, wt: Path):
    if provider == "grok":
        return [str(Path.home() / ".grok/bin/grok"), "--prompt-file", str(prompt_file), "-m", "grok-4.7",
                "--reasoning-effort", "high", "--always-approve", "--max-turns", "600", "--output-format", "streaming-json"]
    if provider == "gemini":
        return ["agy", "-p", prompt_file.read_text(), "--model", "gemini-3.1-pro-high", "--dangerously-skip-permissions",
                "--output-format", "stream-json"]
    return ["claude", "-p", prompt_file.read_text(), "--model", "claude-opus-5-5", "--permission-mode", "bypassPermissions",
            "--output-format", "stream-json", "--verbose"]


QUOTA_ERR = re.compile(r"quota|rate.?limit|RESOURCE_EXHAUSTED|insufficient credits|out of credits|usage limit|429", re.I)


# ---------- verification ----------
def verify(job, wt: Path) -> list[str]:
    problems = []
    for t in job["targets"]:
        p = wt / t
        if not p.exists():
            problems.append(f"missing {t}")
            continue
        if p.is_file() and p.suffix == ".md":
            head = p.read_text(errors="ignore").split("\n---", 1)[0]
            if re.search(r"^status:\s*seed\s*$", head, re.M):
                problems.append(f"{t} is still status: seed")
    if job["kind"] in ("lesson", "practice"):
        r = sh([sys.executable, "tools/check_aos_coverage.py", "--lesson", job["check"], "--verbose", "--summary"], cwd=wt)
        if job["kind"] == "lesson":
            ids, bad = (job["check"] + "-",), ("seed", "no heading", "under 250")
        else:
            ids, bad = (job["check"], "P-"), ("does not cite", "missing practice")
        for line in r.stdout.splitlines():
            rid, _, rest = line.partition(": ")
            if rest and rid.startswith(ids):
                problems += [f"{rid}: {x}" for x in rest.split("; ") if any(b in x for b in bad)]
    if job["kind"] == "papers":
        for t in job["targets"]:
            text = (wt / t).read_text(errors="ignore") if (wt / t).exists() else ""
            if "[!todo] Seed" in text:
                problems.append(f"{t} still has seed sections")
    if job["kind"] == "lab":
        lab = wt / job["targets"][0]
        for name in ("README.md", "Makefile", "expected-output.txt"):
            if not (lab / name).exists():
                problems.append(f"lab missing {name}")
        if not problems:
            r = sh([str(wt / AOS / "labs/setup/run-in-vm.sh"), str(lab), "test"], cwd=wt, timeout=1800)
            if r.returncode:
                problems.append("make test failed in the VM: " + (r.stdout + r.stderr).strip()[-600:])
        tracked = sh(["git", "ls-files", str(lab.relative_to(wt))], cwd=wt).stdout.split()
        bins = [f for f in tracked if not re.search(r"\.(md|c|h|py|sh|java|proto|txt|ya?ml|csv|bt|json|cfg|conf)$|Makefile|\.gitignore$", f)]
        if bins:
            problems.append(f"non-source files tracked: {bins[:5]}")
    if job["kind"] == "cheatsheet":
        t = wt / job["targets"][0]
        if t.exists() and len(t.read_text(errors="ignore")) < 2500:
            problems.append("cheat sheet under 2500 characters")
    for check in (["--check", "links"], ["--check", "style"]):
        r = sh([sys.executable, "tools/audit_vault.py", "--out", "-", *check], cwd=wt)
        for key in ("broken_links", "table_breaking_links", "emoji_files", "emdash_files"):
            m = re.search(rf"^{key}: (\d+)", r.stdout, re.M)
            if m and int(m.group(1)):
                problems.append(f"{key}={m.group(1)} (run tools/audit_vault.py --out - {' '.join(check)})")
    r = sh([sys.executable, "tools/audit_pii.py", "--check"], cwd=wt)
    if r.returncode:
        problems.append("audit_pii failed: " + r.stdout.strip()[-300:])
    return problems


def integrate(job, wt: Path, branch: str) -> None:
    with lock:
        sh(["git", "merge", "--no-ff", "-q", "-m", f"Merge {branch}: {job['id']}", branch], cwd=INTEGRATION, check=True)
        refresh_indexes()
        st = sh(["git", "status", "--porcelain"], cwd=VAULT).stdout
        dirty = [l for l in st.splitlines() if ".obsidian/" not in l]
        if not dirty:
            r = sh(["git", "merge", "--no-ff", "-q", "-m", f"Merge branch 'vault/cs6210-aos': {job['id']}", "vault/cs6210-aos"], cwd=VAULT)
            if r.returncode:
                sh(["git", "merge", "--abort"], cwd=VAULT)
                log(f"vault merge skipped for {job['id']}: {r.stderr.strip()[-200:]}")
        else:
            log(f"vault checkout has non-obsidian changes; vault merge deferred ({len(dirty)} files)")


def refresh_indexes() -> None:
    """Link finished cheat sheets from Cheatsheets/README.md, then sync coverage status and the report."""
    cs = INTEGRATION / AOS / "Cheatsheets"
    readme = cs / "README.md"
    text = readme.read_text()
    names = {"0": "Part 0 - Refresher", "1": "Part 1 - OS Structure and Virtualization", "2": "Part 2 - Parallel Systems",
             "3": "Part 3 - Distributed Systems", "4": "Part 4 - Distributed Subsystems and Recovery",
             "5": "Part 5 - Internet Scale, Real Time, and Security"}
    for n, label in names.items():
        if (cs / f"Part-{n}-Cheatsheet.md").exists():
            text = text.replace(f"- {label} (planned)", f"- [{label}](Part-{n}-Cheatsheet.md)")
    if (cs / "Comparison-Locks-and-Barriers.md").exists():
        text = text.replace("plus the locks and barriers comparison (planned)",
                            "plus the [locks and barriers comparison](Comparison-Locks-and-Barriers.md)")
    readme.write_text(text)
    sh([sys.executable, "tools/check_aos_coverage.py", "--summary", "--sync-status", "--write-report"], cwd=INTEGRATION)
    sh(["git", "add", "-A", AOS], cwd=INTEGRATION)
    if sh(["git", "diff", "--cached", "--quiet"], cwd=INTEGRATION).returncode:
        sh(["git", "commit", "-q", "-m", "chore(aos): sync coverage status and indexes"], cwd=INTEGRATION)


# ---------- lanes ----------
def next_job(jobs):
    done = {j["id"] for j in jobs if j["state"] == "done"}
    for j in jobs:  # already sorted by priority
        if j["state"] == "pending" and all(d in done for d in j["deps"]):
            return j
    return None


def lane(name: str, slot: int, prefs: list[str]) -> None:
    wt = POOL / str(slot) / "SDE-Interview-Prep"
    branch = sh(["git", "branch", "--show-current"], cwd=wt).stdout.strip()
    while not STOP.exists():
        q = quota()
        provider = next((p for p in prefs if available(p, q)), None)
        with lock:
            jobs = load()
            job = next_job(jobs) if provider else None
            if job:
                job["state"] = "running"
                job["attempts"].append({"lane": name, "provider": provider, "start": time.time()})
                save(jobs)
        if not provider:
            log(f"{name}: no provider available; sleeping 30 min")
            time.sleep(1800)
            continue
        if not job:
            if all(j["state"] in ("done", "failed") for j in load()):
                log(f"{name}: queue finished")
                return
            time.sleep(300)
            continue
        log(f"{name}: start {job['id']} on {provider}")
        sh(["git", "merge", "-q", "--no-edit", "vault/cs6210-aos"], cwd=wt)
        failures = job.get("last_failures", "")
        pf = LOGS / f"{job['id']}.prompt.md"
        pf.write_text(prompt(job, wt, branch, failures))
        logf = LOGS / f"{job['id']}.{provider}.{len(job['attempts'])}.log"
        try:
            with open(logf, "w") as lf:
                rc = subprocess.run(command(provider, pf, wt), cwd=wt, stdout=lf, stderr=subprocess.STDOUT,
                                    timeout=TIMEOUTS[job["kind"]]).returncode
        except subprocess.TimeoutExpired:
            rc = -9
        tail = logf.read_text(errors="ignore")[-4000:]
        if rc not in (0, -9) and QUOTA_ERR.search(tail):
            cooldown[provider] = time.time() + 3 * 3600
            log(f"{name}: {provider} looks out of quota (rc={rc}); cooling down 3 h and requeueing {job['id']}")
            with lock:
                jobs = load()
                j = next(x for x in jobs if x["id"] == job["id"])
                j["state"] = "pending"
                j["attempts"].pop()
                save(jobs)
            continue
        # commit leftovers inside the job's targets only
        sh(["git", "add", "--", *job["targets"]], cwd=wt)
        if sh(["git", "diff", "--cached", "--quiet"], cwd=wt).returncode:
            sh(["git", "commit", "-q", "-m", f"docs(aos): {job['id']} (runner commit of job output)"], cwd=wt)
        sh(["git", "checkout", "--", "."], cwd=wt)  # drop stray edits outside targets
        sh(["git", "clean", "-fdq", "--", AOS], cwd=wt)
        problems = verify(job, wt)
        with lock:
            jobs = load()
            j = next(x for x in jobs if x["id"] == job["id"])
            j["attempts"][-1].update({"end": time.time(), "rc": rc, "problems": problems[:20]})
            if not problems:
                j["state"] = "done"
            else:
                j["last_failures"] = "\n".join(problems[:20])
                j["state"] = "pending" if len(j["attempts"]) < 3 else "failed"
            save(jobs)
        if not problems:
            try:
                integrate(job, wt, branch)
                log(f"{name}: done {job['id']} on {provider}")
            except Exception as e:  # keep the lane alive; the job's commits stay on the lane branch
                log(f"{name}: integrate failed for {job['id']}: {e}")
        else:
            log(f"{name}: {job['id']} failed verification on {provider} ({len(problems)} problems): {problems[0][:160]}")
            if len(problems) and provider in prefs and len(prefs) > 1:
                prefs.append(prefs.pop(prefs.index(provider)))  # try another provider first next time


def status() -> None:
    jobs = load()
    from collections import Counter
    print("jobs:", dict(Counter(j["state"] for j in jobs)))
    for j in jobs:
        if j["state"] in ("running", "failed"):
            a = j["attempts"][-1] if j["attempts"] else {}
            print(f"  {j['state']:8} {j['id']:28} {a.get('provider', '')} {a.get('lane', '')}")
    q = quota()
    print("providers:", {p: available(p, q) for p in ("grok", "gemini", "claude")})
    print("next:", [j["id"] for j in jobs if j["state"] == "pending"][:8])


def main() -> None:
    LOGS.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    if sys.argv[1:] == ["status"]:
        return status()
    if sys.argv[1:] != ["run"]:
        sys.exit(__doc__)
    jobs = load()
    for j in jobs:  # a crashed runner leaves jobs marked running
        if j["state"] == "running":
            j["state"] = "pending"
    save(jobs)
    threads = [threading.Thread(target=lane, args=(n, s, list(p)), daemon=False) for n, s, p in LANES]
    for t in threads:
        t.start()
        time.sleep(20)
    for t in threads:
        t.join()
    log("runner exit")


if __name__ == "__main__":
    main()
