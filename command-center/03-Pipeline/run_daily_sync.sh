#!/bin/bash
# Daily job-search sync, run by launchd (com.shreejit.jobsync) at 09:00.
# Paths resolve through the vault symlink into career-ops/command-center.
set -u
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
DIR="$(cd "$(dirname "$0")" && pwd -P)"
LOG="$DIR/sync.log"

{
  echo "== $(date '+%Y-%m-%d %H:%M:%S') daily sync"
  /usr/bin/python3 "$DIR/sync_job_emails.py" --mode daily --apply
  /usr/bin/python3 "$DIR/pipeline_views.py"
} >> "$LOG" 2>&1
