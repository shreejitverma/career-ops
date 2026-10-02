# Practice L04 Generation Report

## What was done
- Extracted all required concept IDs (`L04[a-f]-*`) and paper IDs (`P-*`) for lesson L04 from `_coverage.csv`.
- Authored 24 original exam-style questions for the `Practice/Practice-L04.md` stub.
- Grouped questions logically by sub-lesson (L04a to L04f).
- Ensured strict compliance with the vault style:
  - No emojis or em/en dashes (used `-`).
  - One full sentence per physical line in prose.
  - Used ASCII punctuation.
  - Retained all frontmatter keys from the stub and updated `status` to `solid`.
- Folded answers using the `> [!question]-` admonition format to function as a self-test.
- Cited every required concept and paper ID exactly as specified (e.g., `(concepts: L04a-01, P-MCS-Scalable-Synchronization)`).

## Checks run
- Ran `python3 tools/check_aos_coverage.py --lesson L04 --verbose`.
- Confirmed there are no `"does not cite"` errors for `Practice/Practice-L04.md`.

## Unverified items
- The coverage checker reported 12 missing items regarding `labs/lab-05-spinlocks/Makefile` for the L04b section, but since editing lab files was outside the scope of this job (only `Practice/Practice-L04.md` was to be modified), no action was taken on those missing lab files.
- The Git commit was made locally, no push was performed as per instructions.
