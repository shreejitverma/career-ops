#!/bin/bash
# Daily job-search sync, run by launchd (com.shreejit.jobsync) at 09:00.
# Paths resolve through the vault symlink into career-ops/command-center.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
DIR="$(cd "$(dirname "$0")" && pwd -P)"
REPO="$(cd "$DIR/../.." && pwd -P)"
LOG="$DIR/sync.log"

{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') daily sync"
  /usr/bin/python3 "$DIR/sync_job_emails.py" --mode daily --apply
  /usr/bin/python3 "$DIR/pipeline_views.py"
  # Job board: re-fetch WSQ and every company board, then regenerate
  # _Job-Board.md from the trackers the email sync just updated. A failed
  # board is logged and never stops the rest of the sync.
  if command -v node >/dev/null 2>&1; then
    out="$(node "$REPO/jobboard/jobboard.mjs" refresh 2>&1)"
    status=$?
    printf '%s\n' "$out" | grep -vE '^ok '
    [ "$status" -eq 0 ] || echo "jobboard: refresh exited with status $status (2 = some boards failed; see data/jobboard/runs.tsv)"
  else
    echo "jobboard: node not found on PATH; skipped"
  fi
} >> "$LOG" 2>&1
