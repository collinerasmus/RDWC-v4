#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: tools/restore.sh <backup.tgz> [--with-systemd]"
  exit 1
fi

ARCHIVE="$1"
WITH_SYS="no"
if [ "${2:-}" = "--with-systemd" ]; then WITH_SYS="yes"; fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "== RDWC restore =="

if [ ! -f "$ARCHIVE" ]; then
  echo "not found: $ARCHIVE"; exit 1
fi

# Extract
mkdir -p "$TMPDIR/extract"
tar -xzf "$ARCHIVE" -C "$TMPDIR/extract"

# Copy back files
shopt -s dotglob
for f in $(find "$TMPDIR/extract" -type f); do
  rel="${f#$TMPDIR/extract/}"
  case "$rel" in
    deploy/systemd/*.service)
      if [ "$WITH_SYS" = "yes" ]; then
        echo "restore: $rel"
        mkdir -p "$(dirname "$rel")" && cp -a "$f" "$rel"
      else
        echo "skip (systemd): $rel"
      fi
      ;;
    *)
      echo "restore: $rel"
      mkdir -p "$(dirname "$rel")" && cp -a "$f" "$rel"
      ;;
  esac
done

echo "done. review restored files above."
