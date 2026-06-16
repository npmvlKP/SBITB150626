#!/bin/bash
set -euo pipefail

# TimescaleDB Backup Script

# Configuration
BACKUP_DIR="/backups/timescaledb"
DATE=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="${BACKUP_DIR}/trading_bot_${DATE}.sql.gz"
RETENTION_DAYS=7
PG_USER="trading"
PG_DATABASE="trading_bot"
PG_HOST="timescaledb"

# Ensure backup directory exists
mkdir -p $BACKUP_DIR

# Create backup with compression
echo "Creating TimescaleDB backup..."
docker exec trading_timescaledb pg_dump -U $PG_USER -d $PG_DATABASE --format=custom \
    --blobs --verbose --compress=9 --file=/tmp/trading_dump.dump

# Copy backup file locally
docker cp trading_timescaledb:/tmp/trading_dump.dump $BACKUP_FILE

# Clean up temporary file on container
docker exec trading_timescaledb rm -f /tmp/trading_dump.dump

# Verify backup
if [ -f "$BACKUP_FILE" ] && [ -s "$BACKUP_FILE" ]; then
    echo "Backup created successfully: ${BACKUP_FILE}"
    echo "Backup size: $(du -h $BACKUP_FILE | cut -f1)"
else
    echo "ERROR: Backup failed to create or is empty!"
    exit 1
fi

# Clean up old backups
echo "Cleaning up old backups (older than $RETENTION_DAYS days)..."
find $BACKUP_DIR -name "trading_bot_*.sql.gz" -mtime +$RETENTION_DAYS -exec rm -f {} \;

# Verify retention
echo "Current backups:"
ls -lh $BACKUP_DIR

echo "TimescaleDB backup completed successfully."
