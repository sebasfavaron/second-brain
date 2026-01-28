#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_FILE="$ROOT_DIR/.deploy"

if [[ ! -f "$DEPLOY_FILE" ]]; then
  echo "Missing .deploy file" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$DEPLOY_FILE"

if [[ -z "${SSH_HOST:-}" || -z "${REMOTE_DIR:-}" ]]; then
  echo "Missing SSH_HOST or REMOTE_DIR in .deploy" >&2
  exit 1
fi

SERVICE_NAME="${SERVICE_NAME:-second-brain-bot.service}"
COMMIT_MESSAGE="${1:-Update via Telegram admin}"

cd "$ROOT_DIR"

git add -A
if ! git diff --cached --quiet; then
  git commit -m "$COMMIT_MESSAGE"
  git push
fi

ssh "$SSH_HOST" "cd $REMOTE_DIR && git pull && sudo systemctl restart $SERVICE_NAME && sudo systemctl status $SERVICE_NAME --no-pager -l | sed -n '1,12p'"
