#!/usr/bin/env bash
set -e
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
SRC="/var/lib/docker/volumes/doge_carry_bot_src_db/_data/state.db"
DEST="/opt/doge/backups/state_${TIMESTAMP}.db"

mkdir -p /opt/doge/backups
cp "$SRC" "$DEST"
find /opt/doge/backups -type f -mtime +14 -delete   # храним 2 недели

