#!/bin/bash

# Load environment variables from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "Error: .env file not found."
    exit 1
fi

echo "Attempting to sync database password for user: $DB_USER"

# Use docker exec to run ALTER USER inside the postgres container
# We use the postgres superuser to change the password for the app user
docker compose exec -T db psql -U postgres -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"

if [ $? -eq 0 ]; then
    echo "Successfully updated database password in PostgreSQL."
    echo "Now checking if Django can connect..."
    docker compose exec -T web python manage.py migrate --check
    if [ $? -eq 0 ]; then
        echo "✓ Connection verified! Django can now access the database."
    else
        echo "⚠ Password updated, but Django still cannot connect. Please check logs: docker compose logs web"
    fi
else
    echo "Error: Failed to update password. Ensure the database container is running."
    exit 1
fi
