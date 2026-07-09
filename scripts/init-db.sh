#!/bin/bash
# ── init-db.sh — SUBVOX Database Initialization ─────────────────
# Runs all SQL migration files in order against the database.
# Safe to run multiple times (uses IF NOT EXISTS).

set -e

MIGRATIONS_DIR="/app/migrations"

echo "⏳ Waiting for PostgreSQL..."
until PGPASSWORD="${DB_PASSWORD:-}" psql -h "${DB_HOST:-db}" -U "${DB_USER:-subvox}" -d "${DB_NAME:-subvox}" -c "SELECT 1" > /dev/null 2>&1; do
  sleep 1
done
echo "✅ PostgreSQL ready"

echo "⏳ Running migrations..."
for f in $(ls ${MIGRATIONS_DIR}/*.sql 2>/dev/null | sort); do
  echo "  → $(basename $f)"
  PGPASSWORD="${DB_PASSWORD:-}" psql -h "${DB_HOST:-db}" -U "${DB_USER:-subvox}" -d "${DB_NAME:-subvox}" -1 -f "$f" > /dev/null 2>&1
done
echo "✅ Migrations done"
