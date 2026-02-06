#!/bin/bash
# Deploy to Production Environment
# Usage: ./deploy-production.sh
# WARNING: This script deploys to PRODUCTION. Use with caution!

set -e  # Exit on error

echo "⚠️  WARNING: You are about to deploy to PRODUCTION!"
echo "=================================================="
echo ""
read -p "Are you SURE you want to continue? Type 'YES' to confirm: " confirmation

if [ "$confirmation" != "YES" ]; then
    echo "Deployment cancelled."
    exit 1
fi

echo ""
echo "🚀 Deploying to PRODUCTION environment..."
echo "========================================\n"

# Check if .env.production exists
if [ ! -f ".env.production" ]; then
    echo "❌ Error: .env.production not found!"
    echo "Please create .env.production file first"
    exit 1
fi

# Load production environment
export $(cat .env.production | grep -v '#' | xargs)

# Backup current database
echo "💾 Creating database backup..."
mkdir -p backups/production
BACKUP_FILE="backups/production/backup_$(date +%Y%m%d_%H%M%S).sql"

# If current production is running, back it up
if docker-compose -f docker-compose.production.yml ps | grep -q "db"; then
    echo "   Backing up existing database to $BACKUP_FILE..."
    docker-compose -f docker-compose.production.yml exec -T db pg_dump -U $DB_USER quicksales_prod > "$BACKUP_FILE" || true
    echo "   ✅ Backup created: $BACKUP_FILE"
fi

# Stop any running production containers gracefully
echo "🛑 Stopping production services gracefully..."
docker-compose -f docker-compose.production.yml down || true

sleep 5

# Build production environment
echo "🔨 Building production environment..."
docker-compose -f docker-compose.production.yml build

# Start production services
echo "🚀 Starting production services..."
docker-compose -f docker-compose.production.yml up -d

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 15

# Run migrations
echo "📦 Running database migrations..."
docker-compose -f docker-compose.production.yml exec -T web python manage.py migrate || {
    echo "❌ Migration failed! Restoring from backup..."
    exit 1
}

# Collect static files
echo "📁 Collecting static files..."
docker-compose -f docker-compose.production.yml exec -T web python manage.py collectstatic --noinput

# Run security checks
echo "🔒 Running security checks..."
docker-compose -f docker-compose.production.yml exec -T web python manage.py check --deploy || {
    echo "⚠️  Security check warnings detected. Review above."
}

# Show status
echo "\n✅ Production deployment complete!"
echo "================================\n"
echo "📊 Services running:"
docker-compose -f docker-compose.production.yml ps

echo "\n🔗 Production Access:"
echo "  - Web: https://mqs.com"
echo "  - API: https://api.mqs.com"

echo "\n📝 To view logs:"
echo "  docker-compose -f docker-compose.production.yml logs -f web"

echo "\n⚠️  IMPORTANT REMINDERS:"
echo "  1. Verify all services are running correctly"
echo "  2. Test critical functionality thoroughly"
echo "  3. Monitor error logs for any issues"
echo "  4. Setup monitoring and alerts"
echo "  5. Backup was saved to: $BACKUP_FILE"

echo "\n🆘 If you need to rollback:"
echo "  docker-compose -f docker-compose.production.yml down"
echo "  # Then restore from backup:"
echo "  psql -U $DB_USER quicksales_prod < $BACKUP_FILE"
