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
  The "My focus" preset shows US experienced QD/QR/AI/SWE roles you have not applied to.
  Filters, sort, tab, and theme are remembered per browser.
- **Apply.**
  Clicking Apply opens the posting in a new tab and asks whether you submitted the application.
  "Yes" marks the role Applied and records the date.
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
node jobboard/jobboard.mjs mark <jobId> Applied --note "referred by ..."
node jobboard/jobboard.mjs companies
node jobboard/jobboard.mjs scan --company <id>
node jobboard/jobboard.mjs --self-test
```

## Data (all gitignored, user layer)

| File | Written by | Holds |
|---|---|---|
| `data/jobboard/jobs.json` | refresh / ingest-wsq / scan | merged job store |
| `data/jobboard/state.json` | the page and `mark` only | your status, dates, notes, stars, history, manual jobs |
| `data/jobboard/runs.tsv` | every source run | per-board fetch results, including errors |
| `data/jobboard/companies.md` | refresh | the company directory as a Markdown table |

## How merging works

A job's id is `{companyId}:{ATS requisition id}`.
The requisition id is the Greenhouse `gh_jid`, a Lever/Ashby UUID, a Workday `_R123` suffix, or an Eightfold/Oracle `/job/N`.
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

Firms with no public ATS API (Citadel, Citadel Securities, Two Sigma, D. E. Shaw, SIG, Renaissance, Trexquant, Wolverine, Verition, Goldman Sachs, Morgan Stanley, and others) are listed with `boards: []`.
Their roles come from WSQ where WSQ covers them, and the Companies tab links to their careers pages.

## Security

The server binds to `127.0.0.1` only.
It refuses foreign `Host` headers (DNS rebinding) and cross-origin or non-JSON writes.
Posting text is untrusted content: the page escapes every field it renders and never executes anything from a posting.
