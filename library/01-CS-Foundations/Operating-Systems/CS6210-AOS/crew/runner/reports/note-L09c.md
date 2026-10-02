# Report: L09c Content Delivery Networks

## What I did
- Fully rewrote the seed stub for `L09c-Content-Delivery-Networks.md`.
- Read and integrated key concepts from the lecture slides, Coral paper, and Dynamo paper.
- Removed `> [!todo] Seed` callouts and replaced them with robust explanations (>250 chars) for each heading.
- Kept all HTML coverage comments and existing headings intact.
- Enforced Vault style: no emojis, one full sentence per line, used ASCII punctuation, replaced em/en dashes with hyphens.
- Included an ASCII diagram for consistent hashing (virtual nodes) and a Mermaid sequence diagram for Coral's HTTP proxy fetching process.
- Checked worked examples arithmetically (Coral distance halving by verifying XOR values, Dynamo Quorum with $W=2$, $R=2$, $N=3$ and hinted handoff).
- Commited the changed file using a conventional commit message.

## Checks run
- `python3 tools/check_aos_coverage.py --lesson L09c --verbose`
  - The script reported missing coverage exclusively for the labs and practice documents (`missing labs/lab-21-dht/Makefile; Practice/Practice-L09.md does not cite...`).
  - **No** `seed`, `no heading`, or `under 250` errors were reported for the note itself, fully satisfying the acceptance criteria.

## Anything unverified
- Integration with the practice and lab files, as those belong to other jobs. They are reported missing in the coverage script, which is expected.
