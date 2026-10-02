# Command Center (private)

Private half of the Interview Command Center from the public `SDE-Interview-Prep` vault.
It holds company profiles with application status, the application pipeline and Gmail sync, retrospectives, behavioral stories, and daily logs.

## How it is wired

Each folder here is symlinked into the vault at its original path, and those paths are gitignored in the public repo:

```sh
V=~/github/SDE-Interview-Prep/16-Interview-Command-Center
for d in 02-Companies 03-Pipeline 04-Retrospectives 05-Behavioral 06-Daily-Log; do
  ln -s ~/github/career-ops/command-center/$d "$V/$d"
done
```

Obsidian links, Dataview queries, and the daily Gmail sync (cron and launchd call `03-Pipeline/run_daily_sync.sh` through the vault path) keep working unchanged.

## Integration with career-ops

- **Job board** (`node jobboard/jobboard.mjs serve --open`, see `jobboard/README.md`): the tracker notes in `03-Pipeline/` are the source of truth for real applications.
  The board reads every tracker, links it to a posting by URL (or by a link you chose on the board), shows its `stage`, and lists all trackers in its "My pipeline" tab.
  Confirming an application on the board writes a new tracker (schema in `03-Pipeline/_Application-Schema.md`), recording the resume variant sent; when the company already has an active tracker it asks whether to link to it or start a new one (see "Link or new" in `jobboard/README.md`).
  Tracker links open in Obsidian when the vault folder is found; set `JOBBOARD_VAULT_DIR` if it moves from the path in "How it is wired".
- **Daily sync** (`03-Pipeline/run_daily_sync.sh`, 09:00): the email sync, then `pipeline_views.py`, then a job-board refresh that rewrites `03-Pipeline/_Job-Board.md`.
  The email sync reads every folder of every account in Apple Mail with per-mailbox checkpoints, so no message is skipped; Gmail and iCloud are read exactly over IMAP once their app passwords are in the Keychain (`03-Pipeline/Gmail-Sync-Guide.md`, `sync_job_emails.py --doctor`).
- **Resumes** live in `resume/` at the repository root (see `resume/README.md`).
- Generated notes (`_Inbox-Review.md`, `_Pipeline-Stats.md`, `Pipeline-Board.md`, `_Job-Board.md`) and `sync.log` are gitignored; trackers and `.sync/events.jsonl` are tracked.
- Tests: `python3 -m unittest discover -s command-center/03-Pipeline/tests`, run by the no-mistakes gate.

## Rules

- Never copy files from here into the public vault; `tools/private_paths.py` there lists the private locations.
- `PII-INVENTORY.md` is the 2026-09-21 inventory taken before the move.
