# Crew brief: completeness review, technical review, and ship

Run after all writer and lab crews have landed on `vault/cs6210-aos`. Read `00-STANDARD.md` first.

1. **Completeness audit (fresh context).** Walk every slide-notes text file, every paper, the syllabus, the prerequisites list, and every section's "Review Questions" (topics only), and list any concept, mechanism, number, or diagram the notes miss. Add missing material to the right note (new concepts go under an existing heading or, if truly new, tell the captain so the matrix can grow).
2. **Technical review (fresh context).** Check algorithms, traces, arithmetic in worked examples, modern-descendant facts, and every lab's code for correctness (C: UB, races, memory ordering; Python: error handling). Run every lab's `make test` in the VM.
3. **Integrate.** `python3 tools/check_aos_coverage.py --sync-status --write-report` must show 418 of 418 covered, then run `python3 tools/build_mocs.py` (dry run, then `--apply` only if it touches AOS entry notes; the rest of the vault has pre-existing MOC drift that belongs to another change).
4. **Checks.** Links, style, PII, `python3 -m unittest discover tools/tests`, and the no-binaries check.
5. **Ship.** Through `no-mistakes` only (never a bare `git push`). Note for the captain: `vault/cs6210-aos` is stacked on the local `vault/agentic-harness-and-interview-prep`, which has diverged from its remote (the remote has three no-mistakes commits the local lacks); reconcile that branch first or rebase AOS onto main.
6. Report: files, coverage totals, lab results, unverified claims, and the PR link; then `tasks-axi done vault-cs6210-aos --pr <url>`.
