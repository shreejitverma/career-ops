# Report: papers-optional-2

**What was done:**
- Read the source texts for Virtual Power, MashupOS, and Illinois Browser OS (IBOS).
- Updated `01-CS-Foundations/Operating-Systems/AOS/Papers/Optional-Virtual-Power.md` with structured sections (Problem, Key idea, Design, Evaluation, Limitations, What it led to, Exam angles) and extracted authors (Ripal Nathuji, Karsten Schwan).
- Updated `01-CS-Foundations/Operating-Systems/AOS/Papers/Optional-MashupOS.md` with structured sections and extracted authors (Helen J. Wang, Xiaofeng Fan, Jon Howell, Collin Jackson).
- Updated `01-CS-Foundations/Operating-Systems/AOS/Papers/Optional-Illinois-Browser-OS.md` with structured sections and extracted authors (Shuo Tang, Haohui Mai, Samuel T. King).
- Formatted all prose to adhere to Vault style (no emojis, no em/en dashes, one sentence per physical line, ASCII punctuation).
- Changed status to `solid` in the frontmatter for each paper.
- Staged the three target paths and committed using a conventional commit message.

**Checks run:**
- Verified one sentence per physical line formatting.
- Checked text for dashes (used `-` instead of em/en dashes).
- Verified frontmatter keys were retained from the original stubs.
- Pre-commit hooks executed successfully without private data violations.

**Anything unverified:**
- I did not verify whether the exact LOC counts or percentage metrics referenced in the evaluations (e.g., MashupOS's 33% overhead on DOM manipulations) are perfectly aligned with every possible interpretation of the paper, though they accurately reflect the source text snippets I extracted.
