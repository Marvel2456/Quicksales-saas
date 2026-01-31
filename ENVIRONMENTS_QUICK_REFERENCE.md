# 🎯 Quick Reference: Multi-Environment Setup

## 📁 Files Created

```
✅ .env.development          → Local development
✅ .env.staging              → Staging environment
✅ .env.production           → Production environment (⚠️ NEVER commit!)
✅ docker-compose.staging.yml    → Staging services
✅ docker-compose.production.yml  → Production services
✅ deploy-staging.sh         → Deploy to staging (executable)
✅ deploy-production.sh      → Deploy to production (executable)
✅ DEPLOYMENT_GUIDE.md       → Complete documentation
```

---

## 🚀 Quick Commands

### **Development** (Default - Your Laptop)
```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# Logs
docker-compose logs -f web

# Access: http://localhost:8000
```

### **Staging** (Test Before Production)
```bash
# Deploy
./deploy-staging.sh

# Stop
docker-compose -f docker-compose.staging.yml down

# Access: http://localhost:8001
```

### **Production** (Live)
```bash
# Deploy (requires YES confirmation)
./deploy-production.sh

# Stop
docker-compose -f docker-compose.production.yml down

# Access: https://mqs.com (via nginx)
```

---

## 🔑 Key Differences

| Aspect | Dev | Staging | Production |
|--------|-----|---------|------------|
| **DEBUG** | ✅ True | ❌ False | ❌ False |
| **Port** | 8000 | 8001 | 8002 |
| **DB** | Local | Staging DB | RDS/External |
| **SSL** | ❌ | ✅ | ✅ REQUIRED |
| **Security** | Low | Medium | **MAX** |
| **Backups** | - | Manual | **Automatic** |
| **Data Loss** | OK | Avoid | **NEVER** |

---

## ✅ Setup Checklist

### **First Time Setup**

- [ ] Read `DEPLOYMENT_GUIDE.md`
- [ ] Copy `.env.development` to `.env` for development
- [ ] Update `.env.staging` with staging credentials
- [ ] Update `.env.production` with production credentials
- [ ] Create backup directories: `mkdir -p backups/{staging,production}`
- [ ] Test development locally: `docker-compose up -d`
- [ ] Test staging: `./deploy-staging.sh`

### **Before Production Deployment**

- [ ] All code changes tested in staging
- [ ] Database migrations verified
- [ ] Security checks passed: `python manage.py check --deploy`
- [ ] Backups verified working
- [ ] Rollback plan documented
- [ ] Monitoring/alerts configured
- [ ] SSL certificates installed
- [ ] Nginx reverse proxy configured

---

## 🔐 Security Notes

### **Development**
- ✅ No restrictions (debug mode, test keys)
- ✅ Reset database freely

### **Staging**
- ⚠️ Secure but not critical
- ⚠️ Use test Paystack keys
- ✅ Can reset if needed

### **Production**
- 🔒 **Maximum security enabled**
- 🔒 **LIVE Paystack keys**
- 🔒 **LIVE payment processing**
- 🔒 **Real user data**
- 🔒 **Database backups mandatory**

---

## 📝 Environment Variables Quick Ref

### **Most Important to Update Per Environment:**

```bash
# Always change for each environment:
SECRET_KEY=unique-per-env
DEBUG=0 or 1
ENV=development/staging/production
DB_NAME=different-name
DB_PASSWORD=unique-password
PAYSTACK_PUBLIC_KEY
PAYSTACK_SECRET_KEY

# Optional but recommended:
EMAIL_HOST_PASSWORD
ALLOWED_HOSTS
SENTRY_DSN
```

---

## 🆘 Emergency Commands

```bash
# If staging/prod database is corrupt:
docker-compose -f docker-compose.staging.yml down
docker-compose -f docker-compose.staging.yml exec -T db psql -U user db < backup.sql
docker-compose -f docker-compose.staging.yml up -d

# View real-time logs:
docker-compose -f docker-compose.staging.yml logs -f --tail=50 web

# Run one-off command:
docker-compose -f docker-compose.staging.yml exec web python manage.py shell

# Backup database NOW:
docker-compose -f docker-compose.staging.yml exec db pg_dump -U user db > backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## 📊 Workflow Summary

```
CODE CHANGE
    ↓
TEST LOCALLY (Development)
    ↓
GIT PUSH
    ↓
DEPLOY TO STAGING (./deploy-staging.sh)
    ↓
QA TESTING IN STAGING
    ↓
APPROVE FOR PRODUCTION
    ↓
DEPLOY TO PRODUCTION (./deploy-production.sh)
    ↓
MONITOR & VERIFY
```

---

## 💡 Pro Tips

1. **Always test in staging first** - Staging mirrors production
2. **Automate backups** - Use cron jobs for daily backups
3. **Monitor both environments** - Sentry/DataDog tracking
4. **Document changes** - Keep changelog per deployment
5. **Practice rollbacks** - Know how to restore from backups
6. **Keep secrets secure** - Never commit `.env.production`
7. **Version control** - Always commit docker-compose.yml and deploy scripts
8. **Test locally first** - Reduce staging/production issues

---

## 📞 Useful Commands

```bash
# List all containers
docker ps -a

# View specific env services
docker-compose -f docker-compose.staging.yml ps

# Stop specific service
docker-compose -f docker-compose.staging.yml stop web

# Restart service
docker-compose -f docker-compose.staging.yml restart web

# Delete volume (⚠️ data loss!)
docker volume rm quicksales-saas_staging_postgres_data

# Check disk usage
docker system df

# Clean unused resources
docker system prune -a
```

---

**Setup Complete! 🎉**

You now have three isolated environments:
- ✅ **Development** for coding
- ✅ **Staging** for testing changes
- ✅ **Production** for live deployment

Read `DEPLOYMENT_GUIDE.md` for complete documentation!
