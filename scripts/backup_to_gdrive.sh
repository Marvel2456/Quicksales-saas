#!/bin/bash

################################################################################
# Weekly Database Backup Script for Quicksales
# Purpose: Dump PostgreSQL database, compress it, and upload to Google Drive
# Usage: Run via cron job (e.g., weekly at 3:00 AM)
# Requires: Docker, Rclone (configured for Google Drive)
################################################################################

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Directory to temporarily store backups before upload
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
mkdir -p "$BACKUP_DIR"

# Log file for tracking backups (default is user-writable)
LOG_FILE="${LOG_FILE:-$BACKUP_DIR/db_backup.log}"
touch "$LOG_FILE"

# Create timestamp for unique filenames
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
FILENAME="quicksales_db_backup_$DATE.sql.gz"
FULL_PATH="$BACKUP_DIR/$FILENAME"

# Docker container name (from docker-compose.yml)
CONTAINER_NAME="${CONTAINER_NAME:-quicksales_db}"

# Google Drive folder path in Rclone
GDRIVE_FOLDER="${GDRIVE_FOLDER:-gdrive:Backups}"

# Retention period for remote backups
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# Load env files to get DB_NAME / DB_USER if available
if [[ -f "$PROJECT_DIR/.env.local" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env.local"
    set +a
elif [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

DB_NAME="${DB_NAME:-quicksales_db}"
DB_USER="${DB_USER:-quicksales_user}"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE" >&2
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK: $1" | tee -a "$LOG_FILE"
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_error "Missing required command: $1"
        exit 1
    fi
}

# ============================================================================
# MAIN BACKUP PROCESS
# ============================================================================

log "========================================="
log "Starting Quicksales Database Backup"
log "========================================="

require_cmd docker
require_cmd rclone
require_cmd gzip

# Step 1: Check if Docker container is running
log "Checking if Docker container is running..."
if ! docker ps --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
    log_error "Docker container '$CONTAINER_NAME' is not running"
    exit 1
fi
log_success "Docker container is running"

# Step 2: Check if rclone remote is accessible
log "Checking rclone remote access..."
if ! rclone lsd "$GDRIVE_FOLDER" >/dev/null 2>&1; then
    log_error "Cannot access remote '$GDRIVE_FOLDER'. Run 'rclone config' and test with 'rclone lsd $GDRIVE_FOLDER'."
    exit 1
fi
log_success "Rclone remote is accessible"

# Step 3: Create database dump and compress
log "Creating database dump and compressing..."
if docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FULL_PATH"; then
    BACKUP_SIZE=$(du -h "$FULL_PATH" | cut -f1)
    log_success "Database backup created: $FILENAME (Size: $BACKUP_SIZE)"
else
    log_error "Failed to create database backup"
    exit 1
fi

# Step 4: Upload to Google Drive
log "Uploading backup to Google Drive..."
if rclone copy "$FULL_PATH" "$GDRIVE_FOLDER"; then
    log_success "Backup uploaded to Google Drive successfully"

    # Delete local backup only after successful upload
    log "Cleaning up local backup..."
    rm -f "$FULL_PATH"
    log_success "Local backup file deleted"
else
    log_error "Failed to upload backup to Google Drive. Local file kept at $FULL_PATH"
fi

# Step 5: (Optional) Clean up old backups on Google Drive
log "Removing backups older than ${RETENTION_DAYS} days from Google Drive..."
if rclone delete "$GDRIVE_FOLDER" --min-age "${RETENTION_DAYS}d" --verbose; then
    log_success "Old backups cleaned up"
else
    log "Warning: Could not clean old backups (not critical)"
fi

# Step 6: Get current backup count on Google Drive
log "Getting backup statistics..."
BACKUP_COUNT=$(rclone lsf --files-only "$GDRIVE_FOLDER" 2>/dev/null | wc -l | tr -d ' ')
log "Current backups on Google Drive: $BACKUP_COUNT"

log "========================================="
log_success "Database backup process completed"
log "========================================="
