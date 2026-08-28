#!/usr/bin/env bash
# ============================================================
# Auto-AI-WebPost — one-time setup on your Mac
# Connects /Volumes/AI/Auto AI WebPost to GitHub and installs deps.
#
#   bash scripts/mac-setup.sh
# ============================================================
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/tarnatphon/Auto-AI-Webpost.git}"
LOCAL_DIR="/Volumes/AI/Auto AI WebPost"

echo "==> Auto-AI-WebPost setup"
echo "    local folder : $LOCAL_DIR"
echo "    github repo  : $REPO_URL"

# --- 1. folder + git ----------------------------------------
if [ -d "$LOCAL_DIR/.git" ]; then
    echo "==> Folder is already a git clone. Ensuring remote is set..."
    git -C "$LOCAL_DIR" remote set-url origin "$REPO_URL"
elif [ -d "$LOCAL_DIR" ]; then
    echo "==> Folder exists but is not a git repo. Initializing in place (files kept)..."
    git -C "$LOCAL_DIR" init -b main
    git -C "$LOCAL_DIR" remote add origin "$REPO_URL"
    git -C "$LOCAL_DIR" fetch origin
    # merge without losing local changes
    git -C "$LOCAL_DIR" add -A
    git -C "$LOCAL_DIR" commit -m "Local snapshot before sync" || true
    git -C "$LOCAL_DIR" branch -M main
    git -C "$LOCAL_DIR" merge origin/main --allow-unrelated-histories -m "Merge GitHub version" || \
        echo "!! Merge conflicts — resolve them, then run scripts/sync_local.sh"
else
    echo "==> Cloning fresh..."
    git clone "$REPO_URL" "$LOCAL_DIR"
fi

# --- 2. python env ------------------------------------------
cd "$LOCAL_DIR"
if [ ! -d ".venv" ]; then
    echo "==> Creating .venv..."
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# --- 3. starter files ---------------------------------------
[ -f .env ] || cp .env.example .env
[ -f data/config.yaml ] || cp data/config.example.yaml data/config.yaml
[ -f data/persona.yaml ] || cp data/persona.example.yaml data/persona.yaml

# --- 4. install the free cloud-scheduler workflow (needs YOUR git push,
#        since GitHub only lets users - not bots - create workflow files)
if [ ! -f .github/workflows/autopost.yml ]; then
    mkdir -p .github/workflows
    cp .github/workflow-templates/autopost.yml .github/workflows/autopost.yml
    echo "==> Installed .github/workflows/autopost.yml (will activate on your next push)"
fi

echo ""
echo "Setup complete. Next:"
echo "  cd \"/Volumes/AI/Auto AI WebPost\" && source .venv/bin/activate"
echo "  1. edit data/persona.yaml        (your identity — powers E-E-A-T)"
echo "  2. edit .env                     (API keys, only for platforms you use)"
echo "  3. python -m autowebpost.cli sites          (see the catalog)"
echo "  4. python -m autowebpost.cli register githubpages devto telegraph --open"
echo "  5. python -m autowebpost.cli run --topic 'Your first topic' --wait 60"
