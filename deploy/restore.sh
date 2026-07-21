#!/usr/bin/env bash
# Phase 20: real pg_restore from a backup.sh-produced directory into a
# NAMED target database — never implicitly the source database. A
# restore drill (docs/aios-architecture-and-phases.md#phase-20-backup-strategy-disaster-recovery, Section 3)
# always names its target explicitly rather than silently restoring
# over a live database, matching this project's own destructive-action
# discipline (CLAUDE.md).
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: restore.sh <backup_dir> <database_name> [target_db_name]" >&2
  echo "  target_db_name defaults to <database_name> — set it explicitly" >&2
  echo "  when restoring into a disposable drill database instead." >&2
  exit 1
fi

BACKUP_DIR="$1"
DATABASE_NAME="$2"
TARGET_DB="${3:-$DATABASE_NAME}"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"

DUMP_FILE="$BACKUP_DIR/${DATABASE_NAME}.dump"
if [ ! -f "$DUMP_FILE" ]; then
  echo "no such backup file: $DUMP_FILE" >&2
  exit 1
fi

echo "Restoring $DUMP_FILE into database '$TARGET_DB'"
pg_restore -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  --clean --if-exists --no-owner -d "$TARGET_DB" "$DUMP_FILE"

echo "Done."
