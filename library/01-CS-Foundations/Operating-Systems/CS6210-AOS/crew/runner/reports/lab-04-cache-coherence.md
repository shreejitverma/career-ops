# lab-04-cache-coherence Report

## What was done
- Created `.gitignore` to exclude binaries, objects, and the captured output file.
- Developed `false_sharing.c` which launches 4 threads measuring the completion time for unpadded (subject to false sharing) and padded (avoiding false sharing) counters, successfully demonstrating the overhead of coherence traffic.
- Developed `ping_pong.c` which implements a tight spin-loop on a volatile flag between two threads, calculating one-way coherence transfer latency.
- Developed `litmus.c` which runs 500,000 iterations each of Store Buffering (SB) and Message Passing (MP) litmus tests, utilizing C11 `<stdatomic.h>`. Tested both relaxed memory orderings and stricter versions (`seq_cst` or `release`/`acquire`), successfully observing weak behavior counts on ARM.
- Created `Makefile` with `all`, `run`, `test`, and `clean` targets. `make test` exits non-zero on failure and prints PASS lines.
- Captured output using `run-in-vm.sh labs/lab-04-cache-coherence capture` on the `aos` VM.
- Updated `README.md` to `status: solid`, preserving original frontmatter, and populated it with goals, prerequisites, VM run instructions, expected output matching the capture, conceptual explanations, 4 experiments with predictions, and 3 folded questions with answers.

## Checks run
- `make test` passes locally within the `aos` Lima VM.
- Outputs indicate expected architectural behaviors (unpadded counters are slower, relaxed atomics on ARM exhibit weak behaviors while strict atomics do not).
- Formatting conforms to the vault style guidelines (no emojis, no em/en dashes, one full sentence per physical line in prose).

## Unverified
- The `expected-output.txt` is not committed per the `.gitignore` setup, but the README.md shows the actual results captured from the VM. No further testing on other architectures like x86_64 was done since the target environment is specifically `Lima VM aos (Ubuntu 24.04 arm64)`.
