#!/usr/bin/env bash
# ============================================================
# Auto-AI-WebPost — daily two-way sync between your Mac folder
# /Volumes/AI/Auto AI WebPost and GitHub.
#
#   bash scripts/sync_local.sh          # pull + commit + push
#
# Tip: automate with launchd or run it from cron:
#   30 * * * *  bash "/Volumes/AI/Auto AI WebPost/scripts/sync_local.sh" >> "/Volumes/AI/Auto AI WebPost/.sync.log" 2>&1
# ============================================================
set -euo pipefail

LOCAL_DIR="/Volumes/AI/Auto AI WebPost"
cd "$LOCAL_DIR"

echo "==> [$(date '+%Y-%m-%d %H:%M:%S')] sync start"

# 1. bring remote changes in (GitHub Actions may have published posts)
git fetch origin
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git pull --rebase origin "$BRANCH" || { echo "!! pull failed — resolve rebase manually"; exit 1; }

# 2. send local changes out (new drafts, images, persona edits)
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    git add -A
    git commit -m "sync: local updates $(date '+%Y-%m-%d %H:%M')" || true
    git push origin "$BRANCH"
    echo "==> pushed local changes"
else
    echo "==> nothing new locally"
fi

echo "==> sync done"
