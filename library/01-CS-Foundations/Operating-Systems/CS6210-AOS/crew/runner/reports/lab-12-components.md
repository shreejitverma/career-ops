# lab-12-components Report

## What I did
- Identified that `README.md` contained em-dashes (`—`) which caused the style audit to fail.
- Fixed the em-dashes by replacing them with plain hyphens.
- Verified one-sentence-per-physical-line in prose.
- Executed `make test` for the lab inside the Lima VM, which passed successfully.
- Ran the `capture` command to record the benchmark output and overwrite `expected-output.txt`.
- Updated the inline numbers in `README.md` to match the generated benchmark outputs in `expected-output.txt`.
- Committed the fixes with a conventional commit message.

## Checks run
- `tools/audit_vault.py --out - --check style` (Passed, 0 emdash_files)
- `tools/audit_vault.py --out - --check links` (Passed)
- `01-CS-Foundations/Operating-Systems/AOS/labs/setup/run-in-vm.sh 01-CS-Foundations/Operating-Systems/AOS/labs/lab-12-components test` (Passed)

## Anything unverified
- None. All required checks passed and lab execution succeeded.
