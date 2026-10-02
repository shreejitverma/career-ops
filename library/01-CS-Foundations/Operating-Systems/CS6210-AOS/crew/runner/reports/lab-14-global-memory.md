# Lab 14 Report

**What I did:**
- Fixed a broken link to `L07a-Global-Memory-Systems.md` in `README.md` by adjusting the relative path to go up two directories.
- Addressed style violations in `README.md` by ensuring there is exactly one sentence per physical line (e.g., splitting explanations in How It Works, Experiments, and Questions).
- Added a note to `README.md` explaining that the measurements are made on a single NUMA node VM, and how multi-socket real hardware with local/remote NUMA affects these costs.
- Re-ran the simulation using `run-in-vm.sh lab-14-global-memory capture`, updating `expected-output.txt`.
- Adjusted the output and referenced numbers in the `README.md` to reflect the newly captured values (~9x slower remote fetch).
- Committed the changes using a conventional commit message.

**Checks run:**
- `tools/audit_vault.py --check links`: Passed, 0 broken links.
- `tools/audit_vault.py --check style`: Passed, 0 style violations.
- `make test` via `run-in-vm.sh lab-14-global-memory test`: Passed.

**Anything unverified:**
- Nothing. All requirements and constraints have been verified against the latest edits.
