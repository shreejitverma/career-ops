# Report: Paper Notes L09 Group 2

## What I did
- Processed the source texts for "Democratizing content publication with Coral", "Dynamo: Amazon's Highly Available Key-value Store", and "Unraveling the Web Services Web: An Introduction to SOAP, WSDL, and UDDI".
- Updated the three target markdown files (`L09-Coral.md`, `L09-Dynamo.md`, `L09-Web-Services-SOAP-WSDL-UDDI.md`) in the vault.
- Replaced the placeholder contents with solid summaries according to the provided strict bar (one-line summary in abstract, problem, key idea >= 250 characters, design, evaluation, limitations and critiques, what it led to, 2-4 exam angles).
- Filled the authors list in the frontmatter, kept venue and reading keys, and maintained the "Related" links.
- Strictly followed the formatting rules: no emojis, no em/en dashes (used hyphens instead), one sentence per physical line, and ASCII punctuation.
- Committed the changes with a conventional commit message (`docs(aos): update paper notes for Coral, Dynamo, Web Services`) to the `aos/writer-part-0-1` branch.

## Checks run
- Verified that all lines end cleanly and follow the one-sentence-per-line rule.
- Verified that no em or en dashes were used.
- Counted the characters for the "Key idea" sections to ensure they easily exceeded the 250-character minimum.
- Ran `git add` and `git commit` which passed the internal hooks (e.g., `private_data_violations: 0`).

## Unverified
- The web service paper is an introductory tutorial, so its Evaluation section explicitly notes the lack of empirical numbers; I assumed stating this aligns with the syllabus's expectations.
- Content checks relating to the syllabus limitations and honor code were respected (no project/exam solutions are present), though without access to the actual syllabus, I relied strictly on the prompt's negative constraints.
