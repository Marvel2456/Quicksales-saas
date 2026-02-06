# Quicksales Deployment & Backup Setup Guide

This guide covers the complete setup for automated GitHub Actions deployment and weekly database backups to Google Drive.

## Table of Contents
1. [GitHub Actions Deployment Setup](#github-actions-deployment-setup)
2. [Database Backup Setup](#database-backup-setup)
3. [Cron Job Configuration](#cron-job-configuration)
4. [Troubleshooting](#troubleshooting)

---

## GitHub Actions Deployment Setup

### Prerequisites on Hostinger VPS
1. Git installed and repository cloned
2. Docker and Docker Compose installed
3. Project folder at `~/Quicksales-saas`

### Step 1: Generate SSH Keys for GitHub

**On your local machine** (not the VPS):
```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f deploy_key -N ""
```

This creates two files:
- `deploy_key` (private key)
- `deploy_key.pub` (public key)

### Step 2: Add Public Key to Hostinger VPS

**On your Hostinger VPS**:
```bash
mkdir -p ~/.ssh
cat >> ~/.ssh/authorized_keys << 'EOF'
[PASTE CONTENTS OF deploy_key.pub HERE]
EOF
chmod 600 ~/.ssh/authorized_keys
```

### Step 3: Add Secrets to GitHub Repository

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add:

| Secret Name | Value |
|------------|-------|
| `SSH_PRIVATE_KEY` | Contents of `deploy_key` (private key) |
| `HOSTINGER_HOST` | Your Hostinger VPS IP address |
| `HOSTINGER_USER` | Your VPS username (e.g., `root` or your user) |

### Step 4: Deploy

Simply push to the `main` branch:
```bash
git push origin main
```

Or manually trigger from GitHub UI: **Actions** → **Deploy to Hostinger VPS** → **Run workflow**

---

## Database Backup Setup

### Prerequisites

1. **Rclone installed** on Hostinger VPS:
   ```bash
   curl https://rclone.org/install.sh | sudo bash
   ```

2. **Rclone configured for Google Drive**:
   ```bash
   rclone config
   ```
   
   When prompted:
   - Name: `gdrive`
   - Storage: `drive` (Google Drive)
   - Client ID & Secret: Leave blank (or use your own)
   - Auto config: Choose `N` (you'll get a URL)
   - Visit the URL on your local machine, authorize, and paste the code back

3. **Create a Backups folder** in your Google Drive (optional but recommended)

### Step 1: Update Backup Script

Edit `scripts/backup_to_gdrive.sh` and update these variables:

```bash
# Line ~33-36: Update with your actual database credentials
DB_NAME="quicksales_db"        # Your database name
DB_USER="quicksales_user"      # Your database user

# Line ~39: Update if you used a different Rclone remote name
GDRIVE_FOLDER="gdrive:Backups"  # Your Google Drive backup folder
```

### Step 2: Make Script Executable

**On Hostinger VPS**:
```bash
chmod +x ~/Quicksales-saas/scripts/backup_to_gdrive.sh
```

### Step 3: Test the Script

Run it manually once to verify it works:
```bash
bash ~/Quicksales-saas/scripts/backup_to_gdrive.sh
```

Expected output:
```
✅ Database backup created
✅ Backup uploaded to Google Drive successfully
✅ Database backup process completed!
```

---

## Cron Job Configuration

### Setup Weekly Backup

**On Hostinger VPS**, edit your crontab:
```bash
crontab -e
```

Add one of these lines:

**Option 1: Every Sunday at 3:00 AM**
```bash
0 3 * * 0 bash ~/Quicksales-saas/scripts/backup_to_gdrive.sh >> /var/log/db_backup.log 2>&1
```

**Option 2: Every day at 3:00 AM**
```bash
0 3 * * * bash ~/Quicksales-saas/scripts/backup_to_gdrive.sh >> /var/log/db_backup.log 2>&1
```

**Option 3: Every Monday & Thursday at 2:00 AM**
```bash
0 2 * * 1,4 bash ~/Quicksales-saas/scripts/backup_to_gdrive.sh >> /var/log/db_backup.log 2>&1
```

### View Cron Logs

```bash
# Check if cron job ran
grep CRON /var/log/syslog | tail -20

# Check backup logs
tail -50 /var/log/db_backup.log
```

---

## Quick Setup Checklist

### GitHub Actions
- [ ] Generate SSH key pair locally
- [ ] Add public key to Hostinger `~/.ssh/authorized_keys`
- [ ] Add `SSH_PRIVATE_KEY` secret to GitHub
- [ ] Add `HOSTINGER_HOST` secret to GitHub
- [ ] Add `HOSTINGER_USER` secret to GitHub
- [ ] Push to main branch to test deployment

### Database Backups
- [ ] Install Rclone on Hostinger
- [ ] Configure Rclone with Google Drive
- [ ] Update `scripts/backup_to_gdrive.sh` with DB credentials
- [ ] Make script executable: `chmod +x scripts/backup_to_gdrive.sh`
- [ ] Test script manually
- [ ] Add cron job for weekly backups

---

## Troubleshooting

### Deployment Issues

**"Permission denied (publickey)"**
- Check SSH private key is in `SSH_PRIVATE_KEY` secret
- Verify public key in VPS `~/.ssh/authorized_keys`

**"Docker command not found"**
- SSH to VPS and verify: `docker --version`

### Backup Issues

**"Rclone: command not found"**
- Install: `curl https://rclone.org/install.sh | sudo bash`

**"Failed to upload backup"**
- Re-authenticate Rclone: `rclone config`
- Verify `gdrive:Backups` folder exists

**Cron job not running**
- Check: `sudo service cron status`
- View logs: `grep CRON /var/log/syslog`
- Ensure absolute paths in script

### Useful Commands

```bash
# Test backup script
bash ~/Quicksales-saas/scripts/backup_to_gdrive.sh

# List Google Drive backups
rclone ls gdrive:Backups

# View cron logs
grep backup /var/log/syslog | tail -20

# Check Docker status
docker-compose ps
```

---

## Security Notes

- Never commit `.env` to GitHub
- Use strong SSH keys
- Keep database credentials in `.env` only
- Test backup restoration regularly
- Monitor backup logs for failures
