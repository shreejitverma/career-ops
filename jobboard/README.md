# Job board

A local job board and application tracker for quant, trading, and AI roles.
It pulls postings from two public sources and adds your own application state on top of them.
No LLM tokens are used.

- **thewallstreetquants.com/openings (WSQ).** The page is a Next.js app whose server payload embeds every listing as JSON (about 2,300 roles at 53 firms), so it is parsed directly with no browser.
- **Company ATS boards.** Each firm in `companies.yml` is fetched through the same `providers/` modules `scan.mjs` uses (Greenhouse, Lever, Ashby, Workday, Eightfold, Oracle Cloud).

Fork-local: `jobboard/` is declared in `config/local-paths.txt`, so `update-system.mjs` never touches it.

## Run it

```sh
node jobboard/jobboard.mjs refresh        # WSQ + every company board (~4 min)
node jobboard/jobboard.mjs serve --open   # http://127.0.0.1:4178
```

The page has a **Refresh jobs** button that runs the same refresh in the background.

## What the page does

- **Jobs.**
  Every open role gets a status badge, and it starts as **NOT APPLIED** (amber).
  You can filter by status, role category (Quant Research, Quant Dev, AI/ML, Software Eng, Data, Trading, Risk), firm type, seniority, region, tech tags (C++, Python, Rust, OCaml, KDB/q, FPGA, low latency, ML, LLM), source, posting age, and starred.
  A role listed in several cities carries every region they map to, and matches a region filter if any of them is selected.
  The "My focus" preset shows US experienced QD/QR/AI/SWE roles you have not applied to.
  Filters, sort, tab, and theme are remembered per browser.
- **Apply.**
  Clicking Apply opens the posting in a new tab and asks whether you submitted the application.
  "Yes" marks the role Applied and records the date.
  When the company already has an active command-center tracker, you pick instead: link the posting to one of those trackers, start a new application, or "Not yet" (see below).
  A job already linked to a tracker only opens the posting.
  Each role's status dropdown, star, and notes save immediately.
- **My pipeline.**
  A board with Saved / Applied / Interviewing / Offer / Rejected columns.
  An Applied role with no update after 14 days shows a follow-up nudge.
- **Companies.**
  Every firm with its type, open roles, not-applied and applied counts, and source (company board, or WSQ only when no public ATS exists).
  It also links to each firm's careers page.
  Click a company to see its jobs.
- **Add a job.**
  Track a role found elsewhere.
  It is stored with your state, so refreshes never remove it.
- **Export CSV** exports the current filtered view.

## Command line

```sh
node jobboard/jobboard.mjs                  # summary + next steps
node jobboard/jobboard.mjs list --status "Not Applied" --category "Quant Dev" --region USA [--q text] [--limit N | --full]
node jobboard/jobboard.mjs mark <jobId> Applied --note "referred by ..." [--resume <variant>] [--tracker <rel|new>]
node jobboard/jobboard.mjs companies
node jobboard/jobboard.mjs scan --company <id>
node jobboard/jobboard.mjs --self-test
```

## Data (all gitignored, user layer)

| File | Written by | Holds |
|---|---|---|
| `data/jobboard/jobs.json` | refresh / ingest-wsq / scan | merged job store |
| `data/jobboard/state.json` | the page and `mark`; `ingest-wsq`/`refresh` only re-key entries when a previously unmapped WSQ firm is added to `companies.yml` | your status, dates, notes, stars, history, manual jobs, and board-side tracker links (`jobs[id].tracker`) |
| `data/jobboard/runs.tsv` | every source run | per-board fetch results, including errors |
| `data/jobboard/companies.md` | refresh / ingest-wsq / scan | the company directory as a Markdown table |
| `command-center/03-Pipeline/<Active>/<Company>/*-Tracker.md` | the page and `mark`, when you set an application status on a job with no tracker | a new tracker note (never edits or overwrites an existing one) |
| `command-center/03-Pipeline/_Job-Board.md` | refresh / ingest-wsq / scan | the board as an Obsidian note (gitignored) |

## Command center, resumes and reports

When `command-center/03-Pipeline/` exists (override with `JOBBOARD_COMMAND_CENTER`), its tracker notes own the status of real applications:

- **Reading trackers.**
  Every tracker with a `company` and a `stage` is read.
  A tracker is linked to a board job when one of its `links` is that job's posting, matched by requisition id, so a firm-domain `?gh_jid=` link and a `job-boards.greenhouse.io` link are the same job.
  A tracker is also linked to a posting you tied to it on the board (`tracker` on that job in `state.json`); the note itself is never edited, and the link survives the note moving from `Active/` to `Archive/`.
  A linked job's status comes from the tracker's `stage` (applied/recruiter/OA -> Applied, phone/onsite -> Interviewing, offer -> Offer, rejected/ghosted -> Rejected, withdrawn -> Not Interested, sourced -> Saved).
  The board refuses to change it and names the note to edit instead; notes and stars still save.
- **Writing trackers.**
  Setting Applied, Interviewing, Offer or Rejected on an untracked job writes a schema-compliant tracker first, in the company's existing folder when there is one.
  Its `applied` date is the one the board already recorded for the job, else today; an Offer or Rejected tracker gets no follow-up next action.
- **Link or new.**
  When the job's company already has non-archived trackers, that application status needs an explicit choice, so an existing application is never double-counted.
  The page offers "This is my existing application: <tracker> (<stage>)" per tracker, "New application", and "Not yet".
  The API takes `patch.tracker` (a tracker's `rel` to link, or `"new"`), `mark` takes `--tracker <rel|new>`, and without one the change is refused with the existing trackers named.
  Company names match the registry by exact name first; a suffix-stripped name shared by two firms (Citadel, Citadel Securities) matches neither.
  A tracker counts for a job by registry id, or by its company name or aliases when its firm is not in `companies.yml` (so an added Talan posting still offers the existing Talan tracker, and "New application" reuses its folder).
  Adding a job with an application status for such a company saves it as Not Applied and opens the choice on the Jobs tab.
  If that write fails, nothing is recorded.
  The daily Gmail sync then matches replies to it by company name.
- **My pipeline** lists every tracker, not only board jobs, with its stage and next action (overdue ones in red), plus board jobs you gave a status without a tracker.
- **Resumes.**
  Confirming an application offers the `resume/<track>/<length>/*.pdf` variants, remembers the last one per role category, and records the choice on the job and in the tracker.
  `GET /api/resume?variant=` serves only discovered variants.
- **Reports.**
  A posting evaluated by career-ops (`reports/*.md` with a `**URL:**` header) shows a "Report NNN - score" badge that opens the report.
- **Obsidian.**
  Tracker links open in Obsidian when the vault folder mirroring `command-center/` is found (`JOBBOARD_VAULT_DIR`, or the default documented in `command-center/README.md`, used only when its `03-Pipeline` resolves to this command center).

Without a command center the board keeps statuses in `state.json` only, as before.

## How merging works

A job's id is `{companyId}:{ATS requisition id}`.
The requisition id is the Greenhouse `gh_jid`, a Lever/Ashby UUID, a Workday `_R123` or `_R-533492` suffix (a trailing repost `-1` is dropped), or an Eightfold/Oracle `/job/N`.
WSQ often links a firm's own domain (`?gh_jid=N`) while the board links `job-boards.greenhouse.io/.../jobs/N`, and both collapse into one job.

A job is **closed** only when every source that listed it has since fetched successfully without it.
A timeout or HTTP error never closes anything, and `runs.tsv` records the failure.
Postings that are still listed but no longer classify as relevant roles are removed, unless WSQ lists them or you have tracked them.

## Adding a company

1. Find its public board.
   The ATS directories in `scan-ats-full.mjs`'s dataset, or `node discover-ats.mjs "<Name>"`, can resolve a slug.
2. **Check sample titles before trusting a slug.**
   `headlandsresearch` on Greenhouse, for example, is a clinical-research firm, not Headlands Technologies.
3. Add an entry to `companies.yml`, using `filter: strict` for large banks and fintechs.
4. Run `node jobboard/jobboard.mjs scan --company <id>`.

A WSQ firm that is missing from `companies.yml` is filed under a `wsq-<slug>` id.
Once you list that firm name under the entry's `wsq:` aliases, the next `ingest-wsq` or `refresh` moves its jobs and your tracked state to the registry id.
State already recorded under the new id is never overwritten.

Firms with no public ATS API (Citadel, Citadel Securities, Two Sigma, D. E. Shaw, SIG, Renaissance, Trexquant, Wolverine, Verition, Goldman Sachs, Morgan Stanley, and others) are listed with `boards: []`.
Their roles come from WSQ where WSQ covers them, and the Companies tab links to their careers pages.

## Security

The server binds to `127.0.0.1` only.
It refuses foreign `Host` headers (DNS rebinding) and cross-origin or non-JSON writes.
Posting text is untrusted content: the page escapes every field it renders and never executes anything from a posting.
