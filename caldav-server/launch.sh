#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

STORAGE_GIT_IGNORE_FILE="$SCRIPT_DIR/storage-gitignore"
STORAGE_DIR="$SCRIPT_DIR/storage"

CALENDAR_PROPS="$SCRIPT_DIR/the-schedule.Radicale.props"
CALENDAR="$STORAGE_DIR/collection-root/scheduler/the-schedule"

GIT_REMOTE_URL="git@github.com:bermudafunk/shared-station-schedule-radicale-storage.git"

HOOK_CMD='git add -A && (git diff --cached --quiet || git commit -m "Changes by "%(user)s) && git push'

function prepare_calendar() {
  mkdir -p "$CALENDAR"

  cp "$CALENDAR_PROPS" "$CALENDAR/.Radicale.props"
}

function prepare_git_repository() {
  cd "$STORAGE_DIR"

  git init

  git config user.email "scheduler@bermudafunk.org"
  git config user.name "bermudafunk & radioaktiv scheduler"
  git config commit.gpgsign false

  git remote remove origin || true
  git remote add --fetch origin "$GIT_REMOTE_URL"

  cp "$STORAGE_GIT_IGNORE_FILE" "$STORAGE_DIR/.gitignore"
  git branch --move --force main
  git add --all

  if [ -n "$(git status --porcelain)" ]; then
    git commit -m "Init git repo"
  fi

  git merge --allow-unrelated-histories --strategy ours --no-edit origin/main

  git push -u origin main
}

function exec_radicale() {
  cd "$SCRIPT_DIR"

  pipenv sync

  CMD=(
    "pipenv"
    "run"
    "radicale"
    "--config"
    ""
    "--logging-level"
    "info"
    "--server-hosts"
    "localhost:5232"
    "--storage-type"
    "multifilesystem"
    "--storage-filesystem-folder"
    "$STORAGE_DIR"
    "--storage-hook"
    "$HOOK_CMD"
    "--auth-type"
    "none"
    "--rights-type"
    "authenticated"
  )

  exec "${CMD[@]}"
}

prepare_calendar
prepare_git_repository
exec_radicale
