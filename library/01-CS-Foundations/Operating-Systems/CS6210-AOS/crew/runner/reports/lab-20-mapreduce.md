# lab-20-mapreduce Status Report

## What was done
- Implemented `pipeline.sh` to demonstrate MapReduce using `tr`, `sort`, and `uniq -c`.
- Implemented `mr_python.py` as a conceptual implementation of map and reduce using pure Python.
- Implemented `scheduler.py` to simulate a master scheduler with M=10 map tasks and R=5 reduce tasks, highlighting stragglers and the backup task mechanism.
- Created the standard lab `Makefile` with `run`, `test`, and `clean` targets.
- Ran tests inside the Lima VM using `run-in-vm.sh`.
- Captured actual simulator and script output in `expected-output.txt`.
- Added `.gitignore`.
- Updated `README.md` to `status: solid`, incorporating honor code compliance (no RPCs/real distributed MapReduce framework), run commands, explanations, experiments, and questions per L09b concepts.
- Committed the changes without `--no-verify`.

## Checks run
- Tested the scripts inside the Lima VM (`make test`).
- Verified exit code handling and output formatting.
- Generated `expected-output.txt` using the VM capture script.

## Unverified
- Real-world distributed cluster execution (simulated locally/in a single VM instead, per the project specs limitation to prevent honor code violations).
