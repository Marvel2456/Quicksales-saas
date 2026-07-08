# Migrations Deployment Guide

## Overview
This guide explains how to run pending Django migrations on your live server.

## Recent Migrations
- `account.0006_alter_branch_name` - Makes Branch name field required
- `account.0007_branch_unique_branch_name_per_organization` - Adds unique constraint on (organization, name)

## How to Deploy Migrations to Live Server

### Option 1: SSH into Production Server

```bash
# 1. SSH into your production server
ssh your-user@your-production-server.com

# 2. Navigate to your project directory
cd /path/to/Quicksales-saas

# 3. Activate virtual environment (if using venv)
source env/bin/activate

# 4. Pull latest code (if using git)
git pull origin dev

# 5. Install any new dependencies
pip install -r requirements.txt

# 6. Run migrations
python manage.py migrate

# 7. Collect static files (if needed)
python manage.py collectstatic --noinput

# 8. Restart your web server (gunicorn/uwsgi)
# Example for gunicorn:
sudo systemctl restart gunicorn
# Or if using supervisord:
sudo supervisorctl restart quicksales
```

### Option 2: If Using Docker in Production

```bash
# 1. SSH into your production server
ssh your-user@your-production-server.com

# 2. Navigate to your project directory
cd /path/to/Quicksales-saas

# 3. Pull latest code
git pull origin dev

# 4. Run migrations in Docker
docker-compose exec -T web python manage.py migrate

# 5. Restart containers
docker-compose restart web

# 6. (Optional) Clear any caches
docker-compose exec -T web python manage.py clear_cache
```

### Option 3: Using SSH in VS Code or Git Hooks

Create a deployment script at `deploy.sh`:

```bash
#!/bin/bash

# Set variables
SERVER="your-user@your-production-server.com"
PROJECT_PATH="/path/to/Quicksales-saas"
BRANCH="dev"

# SSH and execute commands
ssh $SERVER << 'SSHEOF'
cd $PROJECT_PATH
git pull origin $BRANCH
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
echo "✓ Deployed successfully"
SSHEOF
```

Then run:
```bash
chmod +x deploy.sh
./deploy.sh
```

## Checking if Migrations Are Applied

```bash
# Check migration status
python manage.py migrate --plan

# Show applied migrations
python manage.py showmigrations account
```

## What Each Migration Does

### Migration: 0006_alter_branch_name
- **Change**: Makes Branch.name field required (not null, not blank)
- **Default**: "Main Branch" for existing rows
- **Benefit**: Prevents data integrity issues

### Migration: 0007_branch_unique_branch_name_per_organization
- **Change**: Adds unique constraint on (organization, name)
- **Benefit**: Prevents duplicate branch names within the same organization
- **enforcement**: Enforced at database level

## Testing Before Deployment

### On Local/Staging:
```bash
# 1. Create backup of database
docker-compose exec -T db pg_dump -U postgres quicksales > backup.sql

# 2. Run migrations
docker-compose exec -T web python manage.py migrate

# 3. Test branch creation by creating a new branch
# 4. Verify organization isolation by checking branches from different orgs

# 5. If issues occur, rollback:
docker-compose exec -T db psql -U postgres quicksales < backup.sql
docker-compose exec -T web python manage.py migrate account 0005
```

## Troubleshooting

### Issue: Migration conflicts
```bash
# Check for unapplied migrations
python manage.py migrate --plan

# If conflicts exist, check which migrations are applied
python manage.py showmigrations account
```

### Issue: Unique constraint violation on 0007
This shouldn't happen since the code ensures no duplicates exist. If it does:
```bash
# Check for duplicate branch names in same org
python manage.py shell
>>> from account.models import Branch
>>> from django.db.models import Count
>>> duplicates = Branch.objects.values('organization', 'name').annotate(count=Count('id')).filter(count__gt=1)
>>> for dup in duplicates:
...     print(f"Organization {dup['organization']}: {dup['name']} appears {dup['count']} times")
```

## Future Migrations

When new migrations are created:
1. They will be automatically generated with `makemigrations`
2. Test them locally first
3. Deploy using the steps above
4. Monitor logs for any errors: `docker-compose logs -f web`

## Database Connection Info

For production, ensure your database connection is secure:
- Use environment variables for credentials
- Don't commit .env files
- Use SSL if connecting remotely

## Post-Deployment Checklist

- [ ] Verify migrations are applied: `python manage.py migrate --plan`
- [ ] Check logs for errors: `docker-compose logs web`
- [ ] Test branch creation functionality
- [ ] Test with multiple organizations
- [ ] Monitor performance

## Support

If you encounter issues during migration deployment:
1. Stop other operations
2. Check logs: `docker-compose logs web | tail -100`
3. Rollback if necessary using previous backups
4. Contact database administrator if needed
