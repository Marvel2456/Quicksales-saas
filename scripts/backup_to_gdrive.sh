#!/bin/bash

################################################################################
# Weekly Database Backup Script for Quicksales
# Purpose: Dump PostgreSQL database, compress it, and upload to Google Drive
# Usage: Run via cron job (e.g., weekly at 3:00 AM)
# Requires: Docker, Rclone (configured for Google Drive)
################################################################################

set -e # Exit on any error

# ============================================================================
# CONFIGURATION
# ============================================================================

# Directory to temporarily store backups before upload
BACKUP_DIR="/home/$USER/backups"
mkdir -p "$BACKUP_DIR"

# Create timestamp for unique filenames
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
FILENAME="quicksales_db_backup_$DATE.sql.gz"
FULL_PATH="$BACKUP_DIR/$FILENAME"

# Docker container name (from docker-compose.yml)
CONTAINER_NAME="quicksales_db"

# Database credentials (should match your .env file)
# You can also source from .env if needed
DB_NAME="quicksales_db"  # Update with your DB name
DB_USER="quicksales_user"  # Update with your DB user

# Google Drive folder path in Rclone
GDRIVE_FOLDER="gdrive:Backups"

# Log file for tracking backups
LOG_FILE="/var/log/db_backup.log"

# ============================================================================
# FUNCTIONS
# ============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ ERROR: $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ $1" | tee -a "$LOG_FILE"
}

# ============================================================================
# MAIN BACKUP PROCESS
# ============================================================================

log "========================================="
log "Starting Quicksales Database Backup"
log "========================================="

# Step 1: Check if Docker container is running
log "🔍 Checking if Docker container is running..."
if ! docker ps | grep -q $CONTAINER_NAME; then
    log_error "Docker container '$CONTAINER_NAME' is not running!"
    exit 1
fi
log_success "Docker container is running"

# Step 2: Create database dump and compress
log "📦 Creating database dump and compressing..."
if docker exec -t $CONTAINER_NAME pg_dump -U $DB_USER $DB_NAME | gzip > "$FULL_PATH"; then
    BACKUP_SIZE=$(du -h "$FULL_PATH" | cut -f1)
    log_success "Database backup created: $FILENAME (Size: $BACKUP_SIZE)"
else
    log_error "Failed to create database backup"
    exit 1
fi

# Step 3: Upload to Google Drive
log "☁️ Uploading backup to Google Drive..."
if rclone copy "$FULL_PATH" "$GDRIVE_FOLDER"; then
    log_success "Backup uploaded to Google Drive successfully"
else
    log_error "Failed to upload backup to Google Drive"
    # Don't exit here, still clean up local file
fi

# Step 4: Delete local backup file
log "🧹 Cleaning up local backup..."
rm -f "$FULL_PATH"
log_success "Local backup file deleted"

# Step 5: (Optional) Clean up old backups on Google Drive (keep last 30 days)
log "🗑️ Removing backups older than 30 days from Google Drive..."
if rclone delete "$GDRIVE_FOLDER" --min-age 30d --verbose; then
    log_success "Old backups cleaned up"
else
    log "Warning: Could not clean old backups (this is not critical)"
fi

# Step 6: Get current backup count on Google Drive
log "📊 Getting backup statistics..."
BACKUP_COUNT=$(rclone ls "$GDRIVE_FOLDER" 2>/dev/null | wc -l)
log "Current backups on Google Drive: $BACKUP_COUNT"

log "========================================="
log_success "Database backup process completed!"
log "========================================="
