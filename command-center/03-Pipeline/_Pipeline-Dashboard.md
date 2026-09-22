---
type: playbook
status: solid
---

# Pipeline dashboard

[[Pipeline-Board|Board]] - [[_Inbox-Review|Inbox review]] - [[_Pipeline-Stats|Statistics]] - [[_Application-Schema|Schema]]

The daily sync (09:00) refreshes the inbox review, the statistics, and the board.
Tables below are live: they read tracker frontmatter every time the note opens.

## Overdue follow-ups

```dataview
TABLE WITHOUT ID
  file.link AS "Application",
  company AS "Company",
  stage AS "Stage",
  next_action AS "Next action",
  next_action_date AS "Due"
FROM "16-Interview-Command-Center/03-Pipeline/Active"
WHERE next_action_date AND date(next_action_date) < date(today)
  AND !contains(list("offer", "rejected", "withdrawn", "ghosted"), stage)
SORT next_action_date ASC
```

## Active pipeline

```dataview
TABLE WITHOUT ID
  file.link AS "Application",
  company AS "Company",
  role AS "Role",
  stage AS "Stage",
  next_action AS "Next action",
  next_action_date AS "Due",
  priority AS "Priority",
  confidence AS "Confidence"
FROM "16-Interview-Command-Center/03-Pipeline/Active"
WHERE stage AND !contains(list("rejected", "withdrawn", "ghosted"), stage)
SORT choice(priority = "high", 1, choice(priority = "medium", 2, 3)) ASC, next_action_date ASC
```

## Upcoming in the next 7 days

```dataview
TABLE WITHOUT ID
  file.link AS "Application",
  next_action AS "Next action",
  next_action_date AS "Due"
FROM "16-Interview-Command-Center/03-Pipeline/Active"
WHERE next_action_date AND date(next_action_date) >= date(today)
  AND date(next_action_date) <= date(today) + dur(7 days)
SORT next_action_date ASC
```

## Statistics

![[_Pipeline-Stats]]
