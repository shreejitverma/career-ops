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

The daily job (`run_daily_sync.sh`, launchd `com.shreejit.jobsync`, 09:00) runs two scripts that live next to this note:

1. `sync_job_emails.py --mode daily --apply` reads recent mail from the Apple Mail accounts listed in the script, keeps job-related messages, labels each one (offer, rejection, assessment, interview, recruiter, received), matches it to a tracker by company name or recruiter domain, and appends new events to `.sync/events.jsonl`.
   It rewrites [[_Inbox-Review]] (stage disagreements and possible untracked applications) and adds one dated line to the tracker's `## Timeline` for each email that names the company.
   An email matched only by sender domain (for example an agency recruiter, who also writes about other companies) is listed in the review note as "domain match, check" and never appended.
   It never edits frontmatter; update `stage` yourself when the review suggests it.
2. `pipeline_views.py` rewrites [[_Pipeline-Stats]] (funnel, response rate by source, rejection reasons) and [[Pipeline-Board]].

Useful commands:

```sh
python3 sync_job_emails.py --dry-run            # what would change, writes nothing
python3 sync_job_emails.py --mode full --apply  # deeper historical scan
python3 sync_job_emails.py --from-json FILE     # replay a saved export, no Mail needed
python3 normalize_trackers.py                   # check trackers against _Application-Schema
python3 -m unittest discover -s tests           # behavior tests
```

The field and stage definitions are in [[_Application-Schema]].
The first-import scripts are in `legacy/` and must not be re-run.
