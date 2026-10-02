# Report: lab-23-temporal-streams

**What was done:**
- Implemented `stream_store.py`, demonstrating the Persistent Temporal Streams (PTS) model with time-based `get()`, `put()`, and garbage collection.
- Implemented `clock_sync.py`, contrasting feed-forward and feedback synchronization for a virtual clock with a baseline hardware clock simulating drift.
- Wrote `measure_clock.c` to test actual `clock_gettime(CLOCK_MONOTONIC)` overhead (leveraging vDSO), reporting a median around 14 ns per call.
- Authored `Makefile` complying with `all`, `run`, `test`, `clean`, and `fetch` targets.
- Authored `README.md` bringing the lab to `status: solid`, preserving original seed frontmatter while explaining PTS, feed-forward vs feedback sync, vDSO performance, experiments, and Q&A.
- Generated `.gitignore` and `expected-output.txt` by running tests inside the Lima VM.
- Committed all generated assets with a conventional commit.

**Checks run:**
- `make test` inside the target Ubuntu 24.04 arm64 Lima VM (completed successfully).
- Re-run `make run` indirectly via `capture` script to populate `expected-output.txt` natively in the VM.
- Vault style checks: manually verified no emojis, no em/en dashes, one sentence per line, and original frontmatter preservation.

**Unverified / Assumptions:**
- Assumed the ~14ns median latency measured on the host/VM setup was standard enough for the target VM; real results on other hardware may vary but the vDSO concept stands.
- Assumed "Virtualize Everything but Time" feed-forward mechanics simply required an offset+multiplier transformation applied lazily on read.
