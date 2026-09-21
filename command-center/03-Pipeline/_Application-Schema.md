---
type: playbook
status: solid
---

# Application schema

Every application is one tracker note in `Active/<Company>/` or `Archive/<Company>/`.
Its frontmatter is the source of truth for the dashboard, the board, and the inbox review.
`normalize_trackers.py` migrates old notes to this schema; `sync_job_emails.py` never edits frontmatter.

## Fields

| Field | Values | Notes |
| :--- | :--- | :--- |
| `company` | text | Must match the company name used in email subjects or the recruiter's domain, so the email sync can match it. |
| `role` | text | Job title as posted. |
| `track` | `[sde, quant-dev, quant-research, low-latency, ai-eng]` | One or more. |
| `focus` | text | Optional specialization, for example "Market Data". |
| `level` | text | For example "Senior", "L5", "Early Career". |
| `source` | text | Channel: "Direct Application", "LinkedIn", "Referral", an agency name. |
| `referrer` | text | Person who referred you, if any. |
| `applied` | `YYYY-MM-DD` | Date submitted. |
| `stage` | see below | Current stage; update it by hand or with the "Log interview round" macro. |
| `status` | text | Free-text detail, for example "Loop completed, awaiting feedback". |
| `next_action` | text | The single next thing you owe. |
| `next_action_date` | `YYYY-MM-DD` | When it is due; drives the overdue list. |
| `priority` | `high`, `medium`, `low` | |
| `confidence` | `1` to `5` | How likely this converts. |
| `comp_band` | text | Posted or quoted range. |
| `rejection_reason` | text | Set when `stage: rejected`. |
| `recruiter`, `recruiter_email`, `stakeholders` | text or list | Contacts. |
| `links` | list | Job posting, portal, prep notes. |

## Stages

`sourced` -> `applied` -> `recruiter` -> `OA` -> `phone` -> `onsite` -> `offer`, or a terminal `rejected`, `withdrawn`, `ghosted`.

- `recruiter`: recruiter screen or agency right-to-represent.
- `OA`: online assessment or take-home.
- `phone`: technical phone or video rounds.
- `onsite`: the final loop, onsite or virtual, including superdays.
- `ghosted`: no reply 21 days after your last follow-up.

## Timeline

Each tracker ends with a `## Timeline` section.
`sync_job_emails.py --apply` appends one line per matched email there, tagged with an event id so it is never added twice.
Add your own dated lines freely; the sync never removes or rewrites them.
