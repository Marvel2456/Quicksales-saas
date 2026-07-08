# GitHub Actions Deployment with Migrations Guide

This guide explains how to automatically run migrations when you deploy via GitHub Actions.

## Overview

There are two approaches:

1. **Automatic migrations on deployment** (Recommended)
2. **Manual migrations after deployment**

---

## Option 1: Automatic Migrations (Recommended)

### Step 1: Create Deployment Script

Create a file at `/scripts/deploy.sh` on your **Hostinger VPS**:

```bash
#!/bin/bash

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting deployment...${NC}"

# Navigate to project
cd ~/Quicksales-saas || exit 1

# Pull latest code
echo -e "${GREEN}Pulling latest code...${NC}"
git pull origin dev

# Pull latest images
echo -e "${GREEN}Pulling Docker images...${NC}"
docker-compose pull

# Start containers
echo -e "${GREEN}Starting containers...${NC}"
docker-compose up -d

# Wait for containers to be ready
echo -e "${GREEN}Waiting for services to start...${NC}"
sleep 5

# Run migrations
echo -e "${GREEN}Running database migrations...${NC}"
docker-compose exec -T web python manage.py migrate

# Collect static files
echo -e "${GREEN}Collecting static files...${NC}"
docker-compose exec -T web python manage.py collectstatic --noinput

# Clear cache
echo -e "${GREEN}Clearing cache...${NC}"
docker-compose exec -T web python manage.py clear_cache 2>/dev/null || true

echo -e "${GREEN}Deployment completed successfully!${NC}"
```

Make it executable:
```bash
chmod +x ~/Quicksales-saas/scripts/deploy.sh
```

### Step 2: Create GitHub Actions Workflow

Create a file at `.github/workflows/deploy.yml` in your **repository**:

```yaml
name: Deploy to Hostinger

on:
  push:
    branches:
      - dev
  workflow_dispatch:  # Allow manual trigger

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        
      - name: Setup SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/deploy_key
          chmod 600 ~/.ssh/deploy_key
          ssh-keyscan -H ${{ secrets.HOSTINGER_HOST }} >> ~/.ssh/known_hosts 2>/dev/null || true
          
      - name: Pull code and deploy
        run: |
          ssh -i ~/.ssh/deploy_key ${{ secrets.HOSTINGER_USER }}@${{ secrets.HOSTINGER_HOST }} << 'EOF'
          set -e
          cd ~/Quicksales-saas
          git checkout dev
          git pull origin dev
          docker-compose pull
          docker-compose up -d
          sleep 5
          echo "Running migrations..."
          docker-compose exec -T web python manage.py migrate
          echo "Collecting static files..."
          docker-compose exec -T web python manage.py collectstatic --noinput
          echo "Deployment complete!"
          EOF
          
      - name: Verify deployment
        run: |
          ssh -i ~/.ssh/deploy_key ${{ secrets.HOSTINGER_USER }}@${{ secrets.HOSTINGER_HOST }} << 'EOF'
          docker-compose ps
          docker-compose logs web | tail -20
          EOF
```

Save this to your repo and commit:
```bash
git add .github/workflows/deploy.yml
git commit -m "Add automated GitHub Actions deployment with migrations"
git push origin dev
```

---

## Option 2: Manual Migrations After Deployment

If you prefer to run migrations manually after pushing:

### Step 1: SSH into VPS

```bash
ssh your-user@your-hostinger-ip
```

### Step 2: Run Migrations

```bash
cd ~/Quicksales-saas

# Option A: Using Docker Compose (Recommended)
docker-compose exec -T web python manage.py migrate

# Option B: Using shell access
docker-compose exec -T web /bin/bash
python manage.py migrate
exit
```

### Step 3: Verify Migrations

```bash
docker-compose exec -T web python manage.py migrate --plan
```

---

## Checking Migration Status

### After Deployment

Check which migrations are applied:
```bash
docker-compose exec -T web python manage.py showmigrations account
```

Expected output showing applied migrations:
```
account
 [X] 0001_initial
 [X] 0002_alter_customuser_branch
 [X] 0003_subscription
 ...
 [X] 0006_alter_branch_name
 [X] 0007_branch_unique_branch_name_per_organization
```

### Current Pending Migrations

To see migrations that haven't been applied:
```bash
docker-compose exec -T web python manage.py migrate --plan
```

---

## Your Current Pending Migrations

You have 2 migrations ready to deploy:

1. **account.0006_alter_branch_name** - Makes branch name required
2. **account.0007_branch_unique_branch_name_per_organization** - Ensures organization-level branch name uniqueness

These will be automatically applied when you deploy if using Option 1.

---

## Deployment Workflow

### Recommended Process:

1. **Make code changes locally**
   ```bash
   git add .
   git commit -m "Your commit message"
   ```

2. **Push to dev branch**
   ```bash
   git push origin dev
   ```

3. **GitHub Actions automatically:**
   - Pulls latest code
   - Starts Docker containers
   - **Runs migrations** ← Automatic
   - Collects static files
   - Reports status

4. **Monitor deployment**
   - Go to GitHub repository
   - Click "Actions" tab
   - Watch your workflow run
   - Check for any errors

---

## Troubleshooting

### Migration Fails on Deployment

**Issue**: "Migration failed" in GitHub Actions

**Solution**:
```bash
# SSH to VPS
ssh user@host

# Check logs
docker-compose logs web | tail -50

# Manually rollback if needed
docker-compose exec -T web python manage.py migrate account 0005

# Fix the issue locally, then re-deploy
```

### Deployment Hangs

**Issue**: Workflow takes too long

**Solution**: Add timeout to workflow:
```yaml
      - name: Pull code and deploy
        timeout-minutes: 15
        run: |
          # deployment commands...
```

### Container Not Ready

**Issue**: "Connection refused" when running migrations

**Solution**: Increase wait time in deploy script:
```bash
# Increase from 5 to 10 seconds
sleep 10
```

---

## Rollback Procedure

If something goes wrong:

```bash
# SSH to VPS
ssh user@host

# Stop containers
docker-compose down

# Checkout previous version
cd ~/Quicksales-saas
git checkout HEAD~1

# Start containers
docker-compose up -d

# Verify
docker-compose ps
```

---

## Environment Variables

Ensure these GitHub Secrets are set:

| Secret | Description |
|--------|-------------|
| `SSH_PRIVATE_KEY` | Your SSH private key |
| `HOSTINGER_HOST` | Hostinger VPS IP address |
| `HOSTINGER_USER` | VPS username |

To update secrets:
1. Go to GitHub repo → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add/update the values

---

## Database Backup During Deployment

If using automated backups, consider running backups before deployment:

```yaml
      - name: Backup database before deployment
        run: |
          ssh -i ~/.ssh/deploy_key ${{ secrets.HOSTINGER_USER }}@${{ secrets.HOSTINGER_HOST }} << 'EOF'
          bash ~/Quicksales-saas/scripts/backup_to_gdrive.sh
          EOF
          
      - name: Deploy application
        run: |
          # deployment commands...
```

---

## Best Practices

1. **Always backup before migrations**
   - Automated: Use cron jobs (see BACKUP_AND_DEPLOYMENT.md)
   - Manual: Run backup script before deploying

2. **Test migrations locally first**
   ```bash
   docker-compose exec -T web python manage.py migrate --plan
   ```

3. **Monitor logs after deployment**
   ```bash
   docker-compose logs -f web
   ```

4. **Keep `.env` in .gitignore**
   - Secret credentials should NOT be in version control
   - Use environment variables instead

5. **Use dev branch for testing**
   - Deploy to dev first
   - Test thoroughly
   - Then merge to main for production

---

## Quick Reference

| Task | Command |
|------|---------|
| Make file executable | `chmod +x script.sh` |
| Run migrations | `docker-compose exec -T web python manage.py migrate` |
| Check migration status | `docker-compose exec -T web python manage.py showmigrations account` |
| View pending migrations | `docker-compose exec -T web python manage.py migrate --plan` |
| View deployment logs | `docker-compose logs web` |
| View GitHub Actions | GitHub repo → Actions tab |
| Update GitHub Secrets | GitHub repo → Settings → Secrets |

---

## Need Help?

Common issues and solutions are in the **Troubleshooting** section above.

For more information, see:
- [MIGRATIONS_DEPLOYMENT_GUIDE.md](MIGRATIONS_DEPLOYMENT_GUIDE.md)
- [BACKUP_AND_DEPLOYMENT.md](BACKUP_AND_DEPLOYMENT.md)
