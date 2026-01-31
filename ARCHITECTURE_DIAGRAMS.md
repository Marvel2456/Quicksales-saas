# 📊 Multi-Environment Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                      QUICKSALES SAAS DEPLOYMENT                    │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  YOUR LOCAL MACHINE (Development)                                           │
│  ═════════════════════════════════════                                      │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │  Docker Compose (docker-compose.yml)                           │        │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐             │        │
│  │  │  Web App    │  │  PostgreSQL  │  │  Redis    │             │        │
│  │  │  (port 8000)│  │  (port 5432) │  │ (6379)    │             │        │
│  │  └─────────────┘  └──────────────┘  └───────────┘             │        │
│  │                                                                 │        │
│  │  ✅ DEBUG=True                                                  │        │
│  │  ✅ Hot reload enabled                                         │        │
│  │  ✅ Verbose logging                                            │        │
│  │  ✅ Easy database reset                                        │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│         |                                                                   │
│         | git push                                                         │
│         v                                                                   │
└──────────────────────────────────────────────────────────────────────────────┘

                              git repository

                                    ↓ pull latest

┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  STAGING SERVER (Testing Environment)                                       │
│  ════════════════════════════════════════                                   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │  Docker Compose (docker-compose.staging.yml)                   │        │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐             │        │
│  │  │  Web App    │  │  PostgreSQL  │  │  Redis    │             │        │
│  │  │  (port 8001)│  │  (port 5433) │  │ (6380)    │             │        │
│  │  └─────────────┘  └──────────────┘  └───────────┘             │        │
│  │                                                                 │        │
│  │  Status: quicksales_staging (separate DB)                      │        │
│  │  ✅ DEBUG=False                                                 │        │
│  │  ✅ SSL enabled                                                │        │
│  │  ✅ Manual backups                                             │        │
│  │  ✅ QA testing                                                 │        │
│  │  ✅ Paystack TEST keys                                        │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│         |                                                                   │
│         | Review & Approve (./deploy-staging.sh)                           │
│         v                                                                   │
└──────────────────────────────────────────────────────────────────────────────┘

                         ⚠️  APPROVAL GATE ⚠️

                              git push

                                    ↓ pull latest

┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  PRODUCTION SERVER (Live Environment)                                       │
│  ═══════════════════════════════════════                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │  Docker Compose (docker-compose.production.yml)                │        │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────┐             │        │
│  │  │  Web App    │  │  PostgreSQL  │  │  Redis    │             │        │
│  │  │  (port 8002)│  │  (AWS RDS)   │  │ (Managed) │             │        │
│  │  └─────────────┘  └──────────────┘  └───────────┘             │        │
│  │           ↓                                                    │        │
│  │  ┌─────────────────────────────────────┐                      │        │
│  │  │  Nginx (port 80/443)                │                      │        │
│  │  │  SSL Certificates                   │                      │        │
│  │  │  Reverse Proxy                      │                      │        │
│  │  └─────────────────────────────────────┘                      │        │
│  │                                                                 │        │
│  │  Status: quicksales_prod (LIVE DATA)                           │        │
│  │  ✅ DEBUG=False                                                 │        │
│  │  🔒 SSL REQUIRED                                               │        │
│  │  🔒 AUTO BACKUPS (daily)                                      │        │
│  │  🔒 Paystack LIVE keys                                        │        │
│  │  🔒 REAL USER DATA                                            │        │
│  │  🔒 Production security settings                              │        │
│  │  📊 Sentry monitoring                                         │        │
│  │  📊 Error tracking                                            │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│         ↓                                                                   │
│    🌐 https://mqs.com                                                      │
│    Users → Real transactions → Real business impact                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Deployment Flow Diagram

```
┌─────────────────┐
│  CODE CHANGE    │
│  in GitHub      │
└────────┬────────┘
         │
         │ git push
         v
    ┌─────────────────┐
    │ Push to main    │
    └────────┬────────┘
             │
             │ Pull in dev
             v
    ┌─────────────────────┐
    │ LOCAL TESTING       │
    │ docker-compose up   │
    └────────┬────────────┘
             │ ✅ Passed?
             v
    ┌─────────────────────┐
    │ COMMIT & PUSH       │
    │ git push origin     │
    └────────┬────────────┘
             │
             │ Pull in staging
             v
    ┌──────────────────────────┐
    │ STAGING DEPLOYMENT       │
    │ ./deploy-staging.sh      │
    └────────┬─────────────────┘
             │ ✅ Test passes?
             v
    ┌──────────────────────────┐
    │ QA TESTING               │
    │ - Core functionality     │
    │ - Payment flow           │
    │ - Database queries       │
    │ - Performance            │
    └────────┬─────────────────┘
             │ ✅ Ready for prod?
             v
    ┌──────────────────────────┐
    │ APPROVAL GATE            │
    │ Review checklist         │
    │ - Backups verified       │
    │ - Rollback tested        │
    │ - Security checks        │
    └────────┬─────────────────┘
             │ ✅ APPROVED?
             v
    ┌──────────────────────────┐
    │ PRODUCTION DEPLOYMENT    │
    │ ./deploy-production.sh   │
    │ (Requires: "YES" input)  │
    └────────┬─────────────────┘
             │ ✅ Confirmed?
             v
    ┌──────────────────────────┐
    │ DATABASE BACKUP          │
    │ pg_dump --backup         │
    └────────┬─────────────────┘
             │
             v
    ┌──────────────────────────┐
    │ PRODUCTION UPDATE        │
    │ - Build images           │
    │ - Run migrations         │
    │ - Collect static files   │
    │ - Start services         │
    └────────┬─────────────────┘
             │
             v
    ┌──────────────────────────┐
    │ MONITORING & VERIFICATION│
    │ - Check logs             │
    │ - Verify functionality   │
    │ - Monitor performance    │
    │ - Alert if issues        │
    └────────┬─────────────────┘
             │
             v
        🎉 DEPLOYED! 🎉
```

---

## Database Isolation

```
┌──────────────────────────────────────────────────────────────────┐
│                      DATABASE STRATEGY                           │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────────────┐
│ DEVELOPMENT DATABASE    │
│ quicksales_dev          │
│                         │
│ ✅ Local SQLite/PG     │
│ ✅ Frequent reset OK   │
│ ✅ 0 cost              │
│ ✅ Easy backup         │
│ ❌ Data loss is fine   │
└─────────────────────────┘

                    ↓ (Different database)

┌─────────────────────────┐
│ STAGING DATABASE        │
│ quicksales_staging      │
│                         │
│ ✅ PostgreSQL          │
│ ✅ Manual backups      │
│ ✅ Can be reset        │
│ ✅ Test Paystack keys  │
│ ⚠️  Keep test data     │
└─────────────────────────┘

                    ↓ (Different database)

┌─────────────────────────┐
│ PRODUCTION DATABASE     │
│ quicksales_prod         │
│                         │
│ 🔒 AWS RDS             │
│ 🔒 AUTO backups        │
│ 🔒 NEVER reset         │
│ 🔒 LIVE Paystack keys  │
│ 🔒 REAL user data      │
└─────────────────────────┘
```

---

## Service Dependencies

```
┌─────────────────────────────────────────────────────────────────┐
│                  SERVICE DEPENDENCIES                           │
└─────────────────────────────────────────────────────────────────┘

                        Web Application
                                ↓
                    ┌───────────┴───────────┐
                    ↓                       ↓
            PostgreSQL Database         Redis Cache
                    ↓                       ↓
        ┌───────────┬─────────┐    ┌──────┴────────┐
        ↓           ↓         ↓    ↓               ↓
    [Models]   [Queries]  [Auth]  Celery         Sessions
                                  Worker         Cache
                                    ↓
                            Task Queue Broker
```

---

## Port Reference

```
┌──────────────────────────────────────────────────────────┐
│               PORT ALLOCATION REFERENCE                 │
└──────────────────────────────────────────────────────────┘

DEVELOPMENT ENVIRONMENT:
├─ 8000  : Django Web Server
├─ 5432  : PostgreSQL
├─ 6379  : Redis
└─ 5050  : pgAdmin

STAGING ENVIRONMENT:
├─ 8001  : Django Web Server
├─ 5433  : PostgreSQL
├─ 6380  : Redis
└─ 5051  : pgAdmin

PRODUCTION ENVIRONMENT:
├─ 8002  : Django Web Server (behind nginx)
├─ 5434  : PostgreSQL (not exposed)
├─ N/A   : Redis (managed service)
├─ 80    : HTTP (nginx redirect)
└─ 443   : HTTPS (nginx + SSL)
```

---

## Security Progression

```
        SECURITY LEVEL PROGRESSION
        
Development (Local)
    ↓
    - DEBUG=True
    - No SSL required
    - Verbose logging
    - Test credentials
    
Staging (Pre-production)
    ↓
    - DEBUG=False
    - SSL enabled
    - Monitoring active
    - Test Paystack keys
    
Production (Live)
    ↓
    - DEBUG=False
    - SSL REQUIRED
    - Full monitoring
    - LIVE Paystack keys
    - Auto backups
    - Security headers
    - Rate limiting
    - IP whitelist (optional)
    - WAF protection
```

---

This visual architecture shows how your three environments are completely isolated yet follow the same deployment pattern!
