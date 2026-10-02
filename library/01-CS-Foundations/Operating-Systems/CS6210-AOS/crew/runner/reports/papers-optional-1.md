# Report: papers-optional-1

## What I did
- Read the source texts for three optional AOS papers: "Protection in the HYDRA Operating System", "Scalability Study of the KSR-1", and "The Multikernel: A New OS Architecture for Scalable Multicore Systems".
- Authored notes for all three papers, updating the corresponding stub markdown files.
- Each note includes the required sections: Problem, Key idea, Design, Evaluation, Limitations and critiques, What it led to, Exam angles, and Related.
- Filled the `authors` key in the frontmatter and kept `venue` and `reading`. Status was updated to `solid`.
- Ensured formatting adheres to the CI-enforced Vault style rules: one full sentence per physical line, no emojis, plain dashes ('-') instead of em/en dashes, and ASCII punctuation.
- Strictly followed the honor code and privacy limits (no project solutions, no unquoted sources without citation, no personal data).
- Staged the three target files and committed them with a conventional commit message (`docs: write notes for HYDRA, KSR-1, and Multikernel papers`).

## Checks run
- `git status` to verify that only the three required files were modified.
- `git commit` automatically ran the pre-commit checks (`private_data_violations: 0`) and succeeded.
- Visual inspection of the generated markdown files to ensure the single sentence per line constraint and no forbidden characters.

## Anything unverified
- HYDRA paper lacked extensive quantitative evaluation, so the "Evaluation" section primarily discusses the qualitative benefits observed by the authors based on the provided text.
