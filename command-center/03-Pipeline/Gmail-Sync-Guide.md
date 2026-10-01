---
tags: [gmail, automation, pipeline, prompt, ingestion, tools, daily-sync]
---

# Master Gmail Job Ingestion & Daily 48-Hour Sync System

> **Purpose:** A dual-mode system to automatically fetch, extract, and integrate all job-hunting emails from Gmail into your **Interview Command Center**:
> 1. **Full Initial Sync:** Historical ingestion of all past applications, recruiter outreach, and OAs.
> 2. **Daily Incremental Sync (Rolling 48h):** A 60-second daily routine to refresh active pipelines, advance stages, append interview rounds, record assessment links, and log rejections without creating duplicate files.

---

## Quick Reference: The Two Gmail Search Queries

### 1. Daily Refresh Query (Rolling Past 2 Days - Run Every Morning)
Copy and paste this into Gmail every morning to grab only updates from the past 48 hours:

```gmail
("application" OR "interview" OR "recruiter" OR "hiring team" OR "assessment" OR "coding challenge" OR "hackerrank" OR "codesignal" OR "karat" OR "codility" OR "right to represent" OR "offer" OR "rejection" OR "status of your application" OR "next steps" OR "scheduling" OR "availability" OR "phone screen" OR "technical round" OR "onsite" OR "take-home" OR "congratulations" OR "thank you for your interest" OR "applied to") -from:(jobalerts-noreply@linkedin.com OR alert@indeed.com OR messages-noreply@linkedin.com OR digest-noreply@quora.com OR "newsletter" OR "job recommendations" OR "jobs for you") -subject:("job alert" OR "jobs you may like" OR "recommended jobs" OR "daily job alert" OR "weekly digest") newer_than:2d
```

### 2. Full Initial Historical Query (All-Time / Last 60 Days)
Run this once to discover and bootstrap all existing historical pipelines:

```gmail
("application" OR "interview" OR "recruiter" OR "hiring team" OR "assessment" OR "coding challenge" OR "hackerrank" OR "codesignal" OR "karat" OR "codility" OR "right to represent" OR "offer" OR "rejection" OR "status of your application" OR "next steps" OR "scheduling" OR "availability" OR "phone screen" OR "technical round" OR "onsite" OR "take-home" OR "congratulations" OR "thank you for your interest" OR "applied to") -from:(jobalerts-noreply@linkedin.com OR alert@indeed.com OR messages-noreply@linkedin.com OR digest-noreply@quora.com OR "newsletter" OR "job recommendations" OR "jobs for you") -subject:("job alert" OR "jobs you may like" OR "recommended jobs" OR "daily job alert" OR "weekly digest")
```

---

## The Master AI Prompt (With Dual-Mode Support)

This prompt features an automatic **Sync Mode Detector** that handles both initial onboarding and state-preserving daily refreshes.

```markdown
You are an elite Career Operations & Interview Pipeline Assistant managing my "16-Interview-Command-Center" Obsidian vault.

### OPERATIONAL SYNC MODES:
Determine the operational mode based on the user request:

1. [MODE: FULL_SYNC] -> Ingesting historical emails to create new company directories and baseline interview tracker files.
2. [MODE: DAILY_INCREMENTAL] -> Processing new emails from the past 48 hours to update, advance, or create pipeline entries.

---

### INGESTION & MATCHING RULES:

#### Step 1: Identity & Entity Resolution
From the email(s), extract:
- Company Name (standardized slug, e.g., "Bank-of-America", "Citadel", "Google", "Meta")
- Role Title & Target Track (SDE, Quant-Dev, Quant-Research, AI-Engineer, Low-Latency)
- Seniority Level (Junior, Mid, Senior, Lead, VP, Contract)
- Sender & Stakeholder Info (Recruiter name, email, agency, hiring manager)
- Event Type:
  * Application Receipt (ATS acknowledgment)
  * Recruiter Screen / Right to Represent (RTR) confirmation
  * Online Assessment (OA) / Take-home challenge invitation + deadline
  * Interview Scheduling Request / Calendar Confirmation (Date/Time/Format)
  * Interview Feedback / Next Round Progression
  * Offer Letter / Compensation Rate Lock
  * Rejection Notice

#### Step 2: State-Aware Pipeline Handling (For DAILY_INCREMENTAL)
Does this company/role already exist in my vault?
- IF EXISTING ACTIVE TRACK:
  DO NOT recreate the file. Output a structured "FILE UPDATE PATCH":
  1. Updated Frontmatter Fields:
     - Advance `stage` (e.g., `applied` -> `phone-screen`, or `phone-screen` -> `technical`)
     - Update `next_action` with the exact next requirement (e.g., "Complete HackerRank by Sept 22")
     - Update `next_deadline` (YYYY-MM-DD)
  2. Append Timeline Row to `## Interview Timeline`:
     `| YYYY-MM-DD | [Round Name] | [Interviewer/Recruiter] | [Format] | [Duration] | [Status] |`
  3. Action Checklist Items: Add any test links, prep tasks, or confirmation replies needed.

- IF BRAND NEW APPLICATION OR RECRUITER OUTREACH:
  Create the dedicated folder and full tracker note under:
  `16-Interview-Command-Center/03-Pipeline/Active/[Company-Name]/[Track-or-Role]/[Company]-[Role]-Interview-Tracker.md`
  using the standard Interview Command Center YAML frontmatter.

- IF REJECTION:
  - Update `stage: rejected` in the frontmatter.
  - Append rejection date to Timeline table.
  - Suggest creating a retrospective note in `04-Retrospectives/` if an interview was completed.

---

### OUTPUT FORMAT SPECIFICATION:

For each email or thread processed, generate:

#### 1. Action Type: [NEW_TRACK | UPDATE_EXISTING | STAGE_ADVANCEMENT | REJECTION]

#### 2. Target File Path:
`16-Interview-Command-Center/03-Pipeline/Active/[Company-Name]/...`

#### 3. Exact Markdown Output:
- If NEW_TRACK: Complete Interview Tracker Markdown with full frontmatter, timeline, technical checklist, and notes template.
- If UPDATE_EXISTING: Precise diff/snippet showing updated YAML frontmatter and the new timeline table row to insert.

#### 4. Daily Log Entry (Copy-Paste for `06-Daily-Log/YYYY-MM-DD.md`):
A clean 2-3 line summary:
- **[Company]** ([Role]): [Event Description] -> Action required: [Next Step] (Due: [Date])

---
RAW EMAIL TEXT / DAILY 48-HOUR EXPORT TO PROCESS:
"""
[PASTE EMAILS OR THREADS HERE]
"""
```

---

## The 60-Second Daily Morning Sync Routine

Integrate this into your morning routine to stay 100% on top of all recruiter messages and coding test deadlines:

```
Step 1: Open Gmail Search
   │
   │ Paste Daily Query:
   │ newer_than:2d
   ▼
Step 2: Copy Any Job Emails From Yesterday / Today
   │
   │ Copy thread text (recruiter reply, OA link, interview invite)
   ▼
Step 3: Paste into Assistant Chat
   │
   │ "Here is my daily 48h Gmail sync. Update my Interview Command Center."
   ▼
Step 4: Vault Automatically Updated
   │
   │ Tracker notes updated with new dates and stages
   │ 00-Dashboard.md reflects updated deadlines
   │ Daily log recorded
```

---

## Automated sync (the maintained pipeline)

The daily job (`run_daily_sync.sh`, launchd `com.shreejit.jobsync`, 09:00) runs two scripts that live next to this note, then refreshes the job board:

1. `sync_job_emails.py --apply --notify` reads **every new message in every account** (see "Complete coverage" below), keeps job-related messages, labels each one (offer, rejection, assessment, interview, recruiter, received, or reply for a Re:/Fwd: thread with a person; body text only counts when it is job phrasing, so news articles about interviews do not), matches it to a tracker by company name (or one of the tracker's `aliases`) or recruiter domain, and appends new events to `.sync/events.jsonl`, keyed by Message-ID.
   It rewrites [[_Inbox-Review]] (stage disagreements, possible untracked applications, and every other unmatched job email from the last 14 days, listed by date, sender and subject) and adds one dated line to the tracker's `## Timeline` for each email that names the company.
   An email matched only by sender domain (for example an agency recruiter, who also writes about other companies) is listed in the review note as "domain match, check" and never appended.
   It never edits frontmatter; update `stage` yourself when the review suggests it.
   Bulk mail (GitHub CI notifications, newsletters, marketing, career-center events, job-alert digests) is dropped by `NOISE_RE` even from dedicated job labels, and hidden from the review even if it was recorded earlier.
   "Possible untracked applications" looks back 180 days, because a missing tracker matters long after the email.
2. `pipeline_views.py` rewrites [[_Pipeline-Stats]] (funnel, response rate by source, rejection reasons) and [[Pipeline-Board]].
3. `node jobboard/jobboard.mjs refresh` (in the career-ops repo) re-fetches every job posting and rewrites [[_Job-Board]] from the trackers step 1 just updated.
   A failed board is logged in `sync.log` and never stops the sync.

## Complete coverage (how no email is missed)

`mail_sources.py` discovers every enabled account in Apple Mail and reads each one the most complete way available:

| Account | Read through | What is read |
| :--- | :--- | :--- |
| Gmail-hosted (the Google accounts, `sverma16@stevens.edu`) and iCloud, **with an app password in the Keychain** | IMAP, by UID | Gmail: All Mail, Spam and Trash, which hold every message in every label, with each message's labels. Others: every folder. |
| Exchange / Office 365 (`sverma16@stevens.edu` Exchange, `sverma357@gatech.edu`) | Mail.app | Every folder, including nested and duplicate-named ones, Junk and Deleted Items. |
| Gmail-hosted **without** an app password | Mail.app (fallback) | Your job labels first, then All Mail, Spam and Trash. Slow for large mailboxes, and a message Mail downloads more than two days late can be missed; the inbox review says so until the app password is stored. |

Only outgoing and system folders are skipped (Sent, Drafts, Outbox, Notes, Tasks, Journal).

Guarantees:

- Each mailbox has a checkpoint of what was actually read (`.sync/checkpoints.json`): the last IMAP UID, or for Mail.app the time range read and any stretch inside it still unread.
  It moves forward only after the messages it covers were recorded, so a failed, interrupted or budget-limited run re-reads instead of skipping.
- IMAP is exact: a message that arrives late still gets a higher UID than the checkpoint.
  Mail.app re-reads two days before the last run to catch mail it downloaded late.
- Mail.app reads in budgeted steps that resume where they stopped (`--budget-minutes`, default 45).
  Per mailbox, new mail comes first, then any stretch an earlier run left unread, then older mail back to the backfill window (`--backfill-days N`, default 180).
  The fast accounts (Exchange, iCloud, everything but Gmail through Mail.app) do all three before the slow Gmail-fallback accounts read their new mail.
  New-mail reads never spend the last 30% of the budget, which is kept for unread stretches and backfill; while the Gmail-fallback accounts are still to be read, the fast accounts may use half of it, so the slow accounts' unread stretches get the rest.
  Unread stretches and backfill each start at the mailbox the previous run stopped in.
  After a long absence, a run that cannot read all the new mail keeps what it read and records the stretch between it and the previous run as unread; later runs read that stretch, newest first, without reading the covered mail again.
  A scan cut short starts at the mailbox it stopped in next time, after the job folders, so no mailbox is starved by the ones before it.
- Consecutive Mail.app chunk reads overlap by a few positions, so a message deleted or moved between two reads cannot push another past the reader.
- Mail from applicant-tracking and assessment platforms, or from a tracker's recruiter domain, counts as job mail even without job wording; bulk mail (CI notifications, newsletters, marketing, job-alert digests) does not.
- A message seen twice (two labels, both sources, overlapping runs) is recorded once.
- A message is counted as handled only once it is delivered: when a job label fails after reading a header, All Mail still delivers the same message.
- Every run records per-mailbox health (`.sync/health.json`).
  The top of [[_Inbox-Review]] lists any mailbox that failed or fell behind, any mailbox whose message bodies Mail could not return (with how many; those messages are classified from subject and sender, and retried while still inside the two-day re-read window unless recorded), and warns when the last run is more than two days old.
  A mailbox is partial when its new mail was not all read, when a stretch of recent mail is still unread, or when its backfill was given time and did not move; one still partial after three runs in a row is listed as failed and posts the notification.
  A backfill that moved further back is progress, not a failure: the review shows one line per account, "backfill in progress: <account> covered back to <date>, target <date>", and never notifies about it.
- A failed mailbox, a run that cannot read mail at all (for example Mail automation denied, or Mail not answering), and an unreadable state file all set exit status 2, appear in the review, and post a macOS notification.
  An unreadable `checkpoints.json` or `seen.json` is moved aside as `*.corrupt-<timestamp>` (an earlier copy is never overwritten; a `--dry-run` only reports it, and `--doctor` prints an `error:` line and exits 2); the mail it covered is read again, never skipped.

### Store app passwords (once per address)

Gmail: create one at myaccount.google.com/apppasswords (needs 2-Step Verification).
iCloud: account.apple.com > Sign-In and Security > App-Specific Passwords.
Then store it; the command prompts for the password and never echoes it:

```sh
security add-generic-password -s career-ops-mail -a shreejitverma@gmail.com -T /usr/bin/security -w
```

`python3 sync_job_emails.py --doctor` lists each account's read method, coverage and the exact command for any address still missing a password.

Useful commands:

```sh
python3 sync_job_emails.py --doctor             # accounts, read method, passwords, coverage
python3 sync_job_emails.py --dry-run            # read and report, write nothing
python3 sync_job_emails.py --backfill-days 365 --apply  # extend coverage a year back (resumable)
python3 sync_job_emails.py --from-json FILE     # replay a saved export, no Mail needed
python3 normalize_trackers.py                   # check trackers against _Application-Schema
python3 -m unittest discover -s tests           # behavior tests
```

The field and stage definitions are in [[_Application-Schema]].
The first-import scripts are in `legacy/` and must not be re-run.
