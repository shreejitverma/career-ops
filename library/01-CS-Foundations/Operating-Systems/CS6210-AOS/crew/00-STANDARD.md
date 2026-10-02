# CS 6210 AOS crew standard (read first, applies to every brief)

## Where the work lives

- Repo: `~/github/SDE-Interview-Prep` (public Obsidian vault). Base branch: `vault/cs6210-aos` (local; scaffold commits 5c160080, ef770347, 73204417). Cut your branch from it; land only by local fast-forward into `vault/cs6210-aos` after the captain approves. Never push; the final ship goes through `no-mistakes` once.
- Section root: `01-CS-Foundations/Operating-Systems/AOS/`. Read `README.md`, `00-Study-Plan.md`, `00-Resources.md`, `labs/setup/README.md`, and the templates `16-Interview-Command-Center/_Templates/CS6210-{Lesson,Paper,Lab}.md` first.
- The coverage matrix `AOS/_coverage.csv` is the contract: every row is a concept (or paper) with the note, the exact heading, the lab, and the practice file that must cover it. Do not edit the CSV; the integrator runs `--sync-status`.
- Progress check: `python3 tools/check_aos_coverage.py --lesson L04b --verbose` (use your lesson ids). Your rows must all pass before you finish.
- Vault rules: read `CLAUDE.md` in the repo root. Highlights: frontmatter schema (keep the seed frontmatter keys; change `status: seed` to `draft` while writing and `solid` when the note meets the bar below), no emojis, no em dashes or en dashes (use "-"), one full sentence per line in prose, plain ASCII in tool source, `[[Note\|Alias]]` inside tables (prefer relative Markdown links), never commit PDFs or binaries.

## Sources (private, local only; never copy text verbatim into the vault)

- Lecture notes text: `~/github/career-ops/library/01-CS-Foundations/Operating-Systems/CS6210-AOS/text/slides/` (L02a-L09c; no L01, L08, L10, L11 slides exist locally, so use the papers and the syllabus for those).
- Papers: `.../CS6210-AOS/papers/` (PDF and PS) and their text in `.../CS6210-AOS/text/papers/`. Two scans have no text layer (System R recovery manager, one cache-affinity copy): read the PDF images or the other copy.
- Official: `.../CS6210-AOS/official/` (Fall 2026 syllabus, prerequisites and concepts list, diagnostic test).
- Section "Review Questions.pdf" files under `text/papers/notes-fork/*/`: use only to check you covered a topic. Never copy, paraphrase as a question, or answer them in the vault.
- OneDrive course folder (`~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/CS6210 Adv Operating Systems`) may sync later; if it has files, use them the same way (Exam and Previous_Tests: coverage check only, never copied).
- Your own knowledge of the papers and the systems; when a fact is not in the sources, verify it (paper text, kernel docs) or leave it out.

## Honor code and privacy (hard rules)

- Georgia Tech's CS 6210 syllabus forbids posting projects publicly. The four projects are VM scheduling in KVM (vCPU scheduler and memory coordinator), barrier synchronization (OpenMP and MPI barrier algorithms), a distributed service with gRPC, and a MapReduce framework with gRPC.
- Never write, in any language, a vCPU scheduler, a memory coordinator, an OpenMP or MPI or C implementation of a counting, tree, MCS-tree, tournament, or dissemination barrier, a gRPC store or vendor service, or a MapReduce master and worker framework. Explaining the algorithms in prose, pseudocode from the published paper with citation, diagrams, and simulators that count rounds or messages are fine.
- No project specs, autograder details, past exam questions, review-question answers, slide text, or paper text in the vault. Short quotes need a citation.
- No personal data: no staff or student names with contact details, no emails.

## Lesson note bar (status: solid)

Each lesson stub already has every concept as an exact `### heading` with a `<!-- coverage: Lxxx-NN -->` comment and a seed callout. Replace every `> [!todo] Seed` callout; keep the headings and the coverage comments verbatim.
- TL;DR (3-5 sentences) and Learning outcomes (measurable verbs).
- Motivation and the problem.
- Core concepts: for each concept heading, at least 250 characters of your own explanation; usually 1-4 paragraphs, with a definition callout (`> [!note]`), a diagram or table where it helps, and the "why" not just the "what".
- Mechanisms step by step with at least one Mermaid diagram per note (sequenceDiagram, flowchart, or stateDiagram), plus ASCII figures where Mermaid is awkward.
- Worked examples with numbers (bus transactions per lock handoff, barrier rounds and messages, LRPC copy counts, GMS age math, DQ arithmetic, LRVM log sizes, timer overshoot), each checked by arithmetic.
- Comparison tables (designs side by side with strengths, costs, and when to use).
- Paper deep dives: one paragraph per paper of the lesson plus a link to its paper note.
- Modern descendants (eBPF, unikernels, seL4, EPT and NPT, virtio, KSM, qspinlock, RCU, CFS and EEVDF, Raft-era systems, Dynamo-style stores) with correct current facts.
- Pitfalls and exam traps as `> [!warning]` callouts.
- Practice link, Lab link, Further reading (papers, kernel docs; verified URLs only).
- Obsidian features to use: callouts (note, tip, example, warning, question with `-` to fold), Mermaid, tables, frontmatter properties (keep `papers` and `lab` wikilinks), aliases for common names (for example "MCS lock"), and heading links between notes (`[text](L04b-Synchronization.md#ticket-lock)` style relative links).

## Paper note bar (status: solid)

Problem, Key idea (at least 250 characters; the checker reads this heading), Design, Evaluation (setup and the two or three numbers worth remembering), Limitations and critiques, What it led to, Exam angles (2-4 folded original questions), Related. Fill `authors` and keep `venue` and `reading`. For partial readings, say which sections the syllabus requires.

## Practice bar

`Practice/Practice-<Lnn>.md`: original exam-style questions; every concept id and every non-optional paper id (`P-<slug>`) of the lesson must be cited at least once, for example:

```
> [!question]- Q7. Why does the MCS lock need compare-and-swap on release? (concepts: L04b-09, L04b-10)
> Answer in 3-8 lines, with the reasoning, a diagram or numbers where useful.
```

Mix: definitions, compare and contrast, traces (step a lock queue or a Lamport mutual exclusion run), numeric problems, design questions ("how would you change X if Y"), and true-or-false-with-justification. Aim for 3-5 questions per sub-lesson. Set the page to `status: solid` when complete.

## Cheat sheets

Each Part writer adds `Cheatsheets/Part-<n>-Cheatsheet.md` (frontmatter type: playbook, tags [cs6210, cs6210/cheatsheet]): one dense page per Part with the tables, formulas, and diagrams to rebuild from memory before a test. Link it from the Part README, and in `Cheatsheets/README.md` replace only your Part's "(planned)" line with a link (other crews edit the other lines).

## Verification before you report done

```sh
python3 tools/check_aos_coverage.py --lesson L04 --verbose   # one call per lesson number you own (covers its sub-lessons and papers); lab rows may wait on the lab crew
python3 tools/audit_vault.py --out - --check links
python3 tools/audit_vault.py --out - --check style
python3 tools/audit_pii.py --check
python3 -m unittest discover tools/tests
```

The audit tools read only git-tracked files: commit (or `git add`) before running them. Report: files changed, rows passing for your lessons, anything not verified, and claims you are unsure of.
