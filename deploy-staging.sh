#!/bin/bash
# Deploy to Staging Environment
# Usage: ./deploy-staging.sh

set -e  # Exit on error

echo "🚀 Deploying to STAGING environment..."
echo "=====================================\n"

# Check if .env.staging exists
if [ ! -f ".env.staging" ]; then
    echo "❌ Error: .env.staging not found!"
    echo "Please create .env.staging file first"
    exit 1
fi

# Load staging environment
export $(cat .env.staging | grep -v '#' | xargs)

# Stop any running staging containers
echo "🛑 Stopping existing staging containers..."
docker-compose -f docker-compose.staging.yml down || true

# Build and start staging environment
echo "🔨 Building staging environment..."
docker-compose -f docker-compose.staging.yml build

echo "🚀 Starting staging services..."
docker-compose -f docker-compose.staging.yml up -d

# Wait for database to be ready
echo "⏳ Waiting for database to be ready..."
sleep 10

# Run migrations
echo "📦 Running database migrations..."
docker-compose -f docker-compose.staging.yml exec -T web python manage.py migrate

# Collect static files
echo "📁 Collecting static files..."
docker-compose -f docker-compose.staging.yml exec -T web python manage.py collectstatic --noinput

# Create test data (optional)
# docker-compose -f docker-compose.staging.yml exec -T web python manage.py loaddata fixtures/test_data.json

# Show status
echo "\n✅ Staging deployment complete!"
echo "==============================\n"
echo "📊 Services running:"
docker-compose -f docker-compose.staging.yml ps

echo "\n🔗 Access points:"
echo "  - Web: http://localhost:8001"
echo "  - pgAdmin: http://localhost:5051"
echo "  - API: http://localhost:8001/api/"

echo "\n📝 To view logs:"
echo "  docker-compose -f docker-compose.staging.yml logs -f web"

echo "\n💾 To backup database:"
echo "  docker-compose -f docker-compose.staging.yml exec db pg_dump -U \$DB_USER quicksales_staging > backups/staging/backup_\$(date +%Y%m%d_%H%M%S).sql"

echo "\n🛑 To stop staging:"
echo "  docker-compose -f docker-compose.staging.yml down"
