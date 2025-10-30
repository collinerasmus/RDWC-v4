#!/usr/bin/env bash
set -euo pipefail

STAMP=$(date +%F_%H%M)
OUTDIR="backup"
OUTFILE="${OUTDIR}/rdwc-${STAMP}-v4.tgz"

echo "== RDWC backup =="
mkdir -p "$OUTDIR"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

# Collect files
DB_FILE="data/rdwc.db"
ENV_FILE=".env"
SYS_DIR="deploy/systemd"
DOCS=(README.md docs/Ops-Runbook.md)

mkdir -p "$TMPDIR/collect"

# Database
if [ -f "$DB_FILE" ]; then
  echo "include: $DB_FILE"
  mkdir -p "$TMPDIR/collect/data"
  cp -a "$DB_FILE" "$TMPDIR/collect/data/"
else
  echo "note: $DB_FILE not found"
fi

# .env (if exists)
if [ -f "$ENV_FILE" ]; then
  echo "include: $ENV_FILE"
  cp -a "$ENV_FILE" "$TMPDIR/collect/"
else
  echo "note: $ENV_FILE not found"
fi

# systemd units
if compgen -G "$SYS_DIR/*.service" > /dev/null; then
  echo "include: $SYS_DIR/*.service"
  mkdir -p "$TMPDIR/collect/$SYS_DIR"
  cp -a $SYS_DIR/*.service "$TMPDIR/collect/$SYS_DIR/" || true
else
  echo "note: no systemd units in $SYS_DIR"
fi

# docs
for f in "${DOCS[@]}"; do
  if [ -f "$f" ]; then
    echo "include: $f"
    mkdir -p "$TMPDIR/collect/$(dirname "$f")"
    cp -a "$f" "$TMPDIR/collect/$f"
  fi
done

# Pack
( cd "$TMPDIR/collect" && tar -czf "$OLDPWD/$OUTFILE" . )

echo "written: $OUTFILE"
ls -lh "$OUTFILE"
