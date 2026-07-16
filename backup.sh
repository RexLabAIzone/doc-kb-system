#!/bin/bash
# Daily PostgreSQL backup to NFS
set -e

BACKUP_DIR="/mnt/nas/FileZol/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

docker exec postgres pg_dump -U docadmin -d docdb \
  --format=custom \
  --compress=9 \
  --file=/tmp/db_backup.dump

docker cp postgres:/tmp/db_backup.dump "$BACKUP_DIR/docdb_$TIMESTAMP.dump"

echo "[$(date)] Backup saved: docdb_$TIMESTAMP.dump ($(du -h "$BACKUP_DIR/docdb_$TIMESTAMP.dump" | cut -f1))"

# Clean old backups
find "$BACKUP_DIR" -name "docdb_*.dump" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Done"
