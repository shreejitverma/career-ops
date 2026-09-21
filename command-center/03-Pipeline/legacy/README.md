# Legacy bootstrap scripts

One-off scripts and their output from the first import of the job search into the vault (September 2026).
They are kept for reference only.

- `generate_vault_trackers.py` rewrites every tracker and company dossier from hard-coded data; running it again would erase hand edits.
- The mail scanners wrote full dumps (`*.json`, `*.txt`) instead of an incremental log.

The maintained pipeline is `../sync_job_emails.py` (incremental, deduplicated, never edits frontmatter) plus `../pipeline_views.py`.
