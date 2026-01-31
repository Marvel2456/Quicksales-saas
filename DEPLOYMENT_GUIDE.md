# 🚀 Multi-Environment Deployment Guide

This guide explains how to use the three-environment setup for development, staging, and production.

## 📋 Environment Overview

### 1. **Development** (`.env.development`)
- **Purpose**: Local development and testing
- **Database**: SQLite or local PostgreSQL (`quicksales_dev`)
- **Security**: Minimal (DEBUG=True, no HTTPS requirement)
- **Port**: 8000 (default)
- **Use Case**: Daily development work
- **Data Persistence**: Not critical

### 2. **Staging** (`.env.staging`)
- **Purpose**: Pre-production testing
- **Database**: Separate PostgreSQL (`quicksales_staging`)
- **Security**: Medium (DEBUG=False, HTTPS, cookies secure)
- **Port**: 8001
- **Use Case**: Test all changes before production
- **Data Persistence**: Moderate (can be reset if needed)

### 3. **Production** (`.env.production`)
- **Purpose**: Live application
- **Database**: Managed PostgreSQL (RDS/external)
- **Security**: Maximum (all hardening enabled)
- **Port**: 8002 (behind reverse proxy)
- **Use Case**: Real users, real data
- **Data Persistence**: **CRITICAL** - Daily backups required

---

## 🎯 Quick Start

### **Step 1: Initial Setup**

```bash
# Make scripts executable
chmod +x deploy-staging.sh
chmod +x deploy-production.sh

# Create directories for backups
mkdir -p backups/staging
mkdir -p backups/production
```

### **Step 2: Configure Environments**

#### Edit `.env.development` (for local work)
```bash
nano .env.development
# Update values if needed
```

#### Edit `.env.staging` (for staging server)
```bash
nano .env.staging
# Update:
#   - DB_PASSWORD
#   - DB_HOST (if staging DB is separate)
#   - EMAIL_HOST_PASSWORD
#   - PAYSTACK_PUBLIC_KEY/SECRET_KEY (test keys)
#   - ALLOWED_HOSTS
```

#### Edit `.env.production` (SECURE!)
```bash
nano .env.production
# MUST UPDATE:
#   - SECRET_KEY (generate new strong key)
#   - DB_PASSWORD (strong password)
#   - DB_HOST (external RDS endpoint)
#   - EMAIL_HOST_PASSWORD
#   - PAYSTACK_PUBLIC_KEY/SECRET_KEY (LIVE keys)
#   - ALLOWED_HOSTS
#   - SENTRY_DSN
```

⚠️ **NEVER commit `.env.production` to git!**

---

## 🔄 Workflow

### **Development → Staging → Production**

```
┌─────────────┐
│ Development │  (Your laptop)
│   port 8000 │
└──────┬──────┘
       │ Test locally
       ↓
┌─────────────┐
│   Staging   │  (Staging server)
│   port 8001 │
└──────┬──────┘
       │ Verify everything works
       ↓
┌─────────────┐
│ Production  │  (Live server)
│   port 8002 │  (behind nginx)
└─────────────┘
```

---

## 🛠️ Commands for Each Environment

### **Development (Default)**

```bash
# Use existing docker-compose.yml
docker-compose up -d

# View logs
docker-compose logs -f web

# Run migrations
docker-compose exec web python manage.py migrate

# Stop
docker-compose down
```

### **Staging Environment**

```bash
# Deploy to staging
./deploy-staging.sh

# Or manual commands:
docker-compose -f docker-compose.staging.yml up -d
docker-compose -f docker-compose.staging.yml exec web python manage.py migrate

# Access staging
# Browser: http://localhost:8001
# pgAdmin: http://localhost:5051 (admin@staging.admin.com / staging-admin-password)

# View logs
docker-compose -f docker-compose.staging.yml logs -f web

# Backup staging database
docker-compose -f docker-compose.staging.yml exec db pg_dump -U quicksales_staging_user quicksales_staging > backups/staging/backup_$(date +%Y%m%d_%H%M%S).sql

# Restore staging database
docker-compose -f docker-compose.staging.yml exec -T db psql -U quicksales_staging_user quicksales_staging < backups/staging/backup_20260123_120000.sql

# Stop staging
docker-compose -f docker-compose.staging.yml down
```

### **Production Environment**

```bash
# Deploy to production (requires confirmation)
./deploy-production.sh

# Or manual commands:
docker-compose -f docker-compose.production.yml up -d
docker-compose -f docker-compose.production.yml exec web python manage.py migrate

# Access production
# Browser: https://mqs.com (via nginx/reverse proxy)
# API: https://api.mqs.com

# View logs
docker-compose -f docker-compose.production.yml logs -f web

# Emergency backup
docker-compose -f docker-compose.production.yml exec db pg_dump -U quicksales_prod_user quicksales_prod > backups/production/emergency_backup_$(date +%Y%m%d_%H%M%S).sql

# Rollback production
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d
docker-compose -f docker-compose.production.yml exec -T db psql -U quicksales_prod_user quicksales_prod < backups/production/backup_20260123_120000.sql

# Stop production
docker-compose -f docker-compose.production.yml down
```

---

## 📊 Port Reference

| Environment | Web  | DB   | Redis | pgAdmin | Notes |
|-------------|------|------|-------|---------|-------|
| Development | 8000 | 5432 | 6379  | 5050    | Local |
| Staging     | 8001 | 5433 | 6380  | 5051    | Separate DB |
| Production  | 8002 | 5434 | -     | -       | Use external services |

---

## 🔐 Security Checklist

### Before Deploying to Staging:
- [ ] `.env.staging` configured with staging credentials
- [ ] Test email configured
- [ ] Paystack test keys in place
- [ ] Database backups location created
- [ ] All migrations run successfully

### Before Deploying to Production:
- [ ] `.env.production` created with production credentials
- [ ] `SECRET_KEY` is strong and unique
- [ ] Database passwords are strong
- [ ] Paystack **LIVE** keys configured
- [ ] Email service configured for production
- [ ] Database backups automated
- [ ] SSL certificates installed
- [ ] Nginx reverse proxy configured
- [ ] Monitoring/alerting setup (Sentry, DataDog, etc)
- [ ] Database backup tested (can be restored)
- [ ] Security check passes: `python manage.py check --deploy`

---

## 📈 Database Management

### **Create Database (First Time)**

```bash
# For staging
docker-compose -f docker-compose.staging.yml exec db createdb -U quicksales_staging_user quicksales_staging

# For production (usually done by RDS/managed service)
```

### **Backup Strategy**

```bash
# Daily backup script (cron job on production server)
0 2 * * * /path/to/backup-production.sh

# Backup script content:
#!/bin/bash
BACKUP_DIR=/backups/production
DATE=$(date +%Y%m%d_%H%M%S)
docker-compose -f docker-compose.production.yml exec -T db pg_dump \
  -U $DB_USER $DB_NAME | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 30 days
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

### **Restore from Backup**

```bash
# Stop the application
docker-compose -f docker-compose.staging.yml down

# Restore database
gunzip < backups/staging/backup_20260123_120000.sql.gz | \
  docker-compose -f docker-compose.staging.yml exec -T db psql -U quicksales_staging_user quicksales_staging

# Start application
docker-compose -f docker-compose.staging.yml up -d
```

---

## 🔄 Typical Deployment Workflow

### **Making Changes:**

1. **Development**:
   ```bash
   # Work locally
   docker-compose up -d
   # Make code changes
   # Test locally
   git commit -m "Feature X"
   git push
   ```

2. **Staging**:
   ```bash
   # Pull latest code
   git pull origin main
   
   # Deploy to staging
   ./deploy-staging.sh
   
   # Test thoroughly
   # Run security tests
   # Load testing
   ```

3. **Production** (after staging approval):
   ```bash
   # Pull latest code
   git pull origin main
   
   # Deploy to production
   ./deploy-production.sh
   
   # Monitor logs
   # Verify functionality
   # Monitor performance
   ```

---

## ⚠️ Important Notes

### **Development Environment**
- ✅ Safe to reset/clear database
- ✅ DEBUG mode enabled
- ❌ No data persistence needed

### **Staging Environment**
- ✅ Almost identical to production
- ✅ Can test real scenarios
- ⚠️ Keep test data for reference
- ❌ NOT for production data

### **Production Environment**
- ❌ NEVER reset or delete
- ❌ DEBUG mode disabled
- ⚠️ Daily backups MANDATORY
- ⚠️ Test all changes in staging first
- ⚠️ Have rollback plan ready

---

## 🚨 Emergency Procedures

### **Database Corrupted/Lost in Production**

```bash
# 1. Stop production immediately
docker-compose -f docker-compose.production.yml down

# 2. Restore from latest backup
docker-compose -f docker-compose.production.yml up -d
docker-compose -f docker-compose.production.yml exec -T db psql \
  -U $DB_USER $DB_NAME < backups/production/latest_backup.sql

# 3. Verify data integrity
docker-compose -f docker-compose.production.yml exec web \
  python manage.py check

# 4. Restart services
docker-compose -f docker-compose.production.yml restart web
```

### **Web Service Crashes in Production**

```bash
# 1. Check logs
docker-compose -f docker-compose.production.yml logs web --tail=100

# 2. Restart service
docker-compose -f docker-compose.production.yml restart web

# 3. If persists, rollback code
git revert HEAD  # Or checkout previous version
docker-compose -f docker-compose.production.yml build
docker-compose -f docker-compose.production.yml up -d web
```

---

## 📞 Support & Troubleshooting

### **Common Issues**

**Issue**: Database connection refused
```bash
# Check database is running
docker-compose -f docker-compose.staging.yml ps db

# Check credentials in .env.staging
# Try reconnecting
```

**Issue**: Port already in use
```bash
# Change port in docker-compose file
# Or stop other services using that port
lsof -i :8001  # Find what's using port
```

**Issue**: Migrations fail
```bash
# Check migration files
ls subscriptions/migrations/

# Run specific migration
docker-compose -f docker-compose.staging.yml exec web \
  python manage.py migrate subscriptions 0007
```

---

## 📞 Questions?

Refer to Django deployment documentation:
- https://docs.djangoproject.com/en/4.0/howto/deployment/
- https://docs.docker.com/compose/
- https://www.postgresql.org/docs/

