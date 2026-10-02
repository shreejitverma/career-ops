# Lab 21 DHT Report

## What was done
1. Created `consistent_hashing.py` to simulate the effect of virtual nodes on load balancing.
2. Created `chord_routing.py` to simulate $O(\log N)$ key-based routing using finger tables.
3. Created `coral_sloppy.py` to simulate Coral's tree-saturation relief via capacity-bounded insertion.
4. Created `dynamo_quorums.py` to simulate N, R, W partial quorums and vector clock sibling conflict resolution.
5. Created a `Makefile` implementing `all`, `run`, `test`, `clean`, and `fetch` targets.
6. Ran the test suite inside the `aos` Lima VM and captured real measurements into `expected-output.txt`.
7. Authored `README.md` following the playbook template and honor code limits. It includes setup instructions, expected behavior with quoted numbers, an explanation of the scripts, 3 experiments with predictions, and 3 folded questions with answers. The frontmatter `status` was bumped to `solid`.
8. Included a `.gitignore` to avoid checking in unwanted files like `__pycache__`.

## Checks run
- `make test` executed successfully inside the Lima VM using Python 3.12 (`/opt/aos-venv/bin/python`), returning exit code 0.
- Output from `make test` was captured manually via the provided test VM shell script to `expected-output.txt`.
- Code changes were reviewed to ensure no emojis, em/en dashes, and adherence to one sentence per line formatting.
- Ensured honor code was maintained: no sensitive algorithms or data were implemented, only simulated measurements.
- Git commit hook passed successfully indicating no private data violations.

## Anything unverified
- All constraints verified locally in the VM. Nothing remains unverified.
