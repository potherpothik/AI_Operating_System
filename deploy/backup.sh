#!/usr/bin/env bash
# Phase 20: real pg_dump of every logical database in Phase 19's own
# Postgres topology (deploy/postgres-init/01-create-databases.sql) —
# custom format (-Fc), one file per database, into a timestamped
# directory. Never touches secrets — those are a separate, stricter
# process per the Phase 20 doc's own explicit framing.
set -euo pipefail

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
# PGPASSWORD, if needed, is expected to already be exported by the
# caller (or a .pgpass file used) — never hardcoded or logged here.

OUT_DIR="${1:-./backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_DIR"

DATABASES=(
  governance
  platform
  knowledge
  assembly
  agents
  execution
  database_connector
  planning
  knowledge_pipelines
  extensibility
  observability
)

echo "Backing up ${#DATABASES[@]} databases to $OUT_DIR"
for db in "${DATABASES[@]}"; do
  echo "  -> $db"
  pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    -Fc -f "$OUT_DIR/${db}.dump" "$db"
done

echo "Done. $OUT_DIR/*.dump"
