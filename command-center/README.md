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

## Rules

- Never copy files from here into the public vault; `tools/private_paths.py` there lists the private locations.
- `PII-INVENTORY.md` is the 2026-09-21 inventory taken before the move.
