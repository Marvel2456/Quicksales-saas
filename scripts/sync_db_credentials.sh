#!/bin/bash

# Check if docker-compose or docker compose is used
if command -v docker-compose &> /dev/null; then
    DOCKER_CMD="docker-compose"
else
    DOCKER_CMD="docker compose"
fi

# Helper to get variable from .env
get_env_var() {
    grep "^$1=" .env | cut -d'=' -f2- | sed "s/^['\"]//;s/['\"]$//;s/^ *//;s/ *$//"
}

DB_USER=$(get_env_var "DB_USER")
DB_PASSWORD=$(get_env_var "DB_PASSWORD")
DB_NAME=$(get_env_var "DB_NAME")

if [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ]; then
    echo "Error: Could not find DB_USER or DB_PASSWORD in .env"
    exit 1
fi

echo "--- Debug Info ---"
echo "Target User: $DB_USER"
echo "Target DB: $DB_NAME"
echo "------------------"

# 1. Check if containers are running
if ! $DOCKER_CMD ps | grep -q "quicksales_db"; then
    echo "Error: The database container (quicksales_db) is NOT running."
    echo "Please run: $DOCKER_CMD up -d"
    exit 1
fi

echo "Attempting to sync database password..."

# 2. Reset the password. 
# We connect to the default 'postgres' database which ALWAYS exists,
# so we don't get 'database does not exist' errors while trying to fix the user.
echo "Running ALTER USER command..."
docker exec -it quicksales_db psql -U $DB_USER -d postgres -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"

if [ $? -eq 0 ]; then
    echo "✓ Successfully updated database password in the DB!"
    echo ""
    echo "--- Database Status ---"
    echo "Listing all databases in the container:"
    docker exec -it quicksales_db psql -U $DB_USER -d postgres -l
    echo "-----------------------"
    echo ""
    echo "Now checking Django connection to '$DB_NAME'..."
    $DOCKER_CMD exec -T web python manage.py migrate --check
    if [ $? -eq 0 ]; then
        echo "✓ Connection verified! Django can now access the database '$DB_NAME'."
    else
        echo "⚠ Password is fixed, but Django still cannot connect to '$DB_NAME'."
        echo "Possibilities:"
        echo "1. The database name '$DB_NAME' in your .env is wrong (check the list above)."
        echo "2. The DB_PASSWORD in your .env doesn't match the one you just set."
    fi
else
    echo "Failed to update password."
    echo "It seems even '$DB_USER' cannot connect to the 'postgres' database."
    echo "Try this emergency command to see what's inside:"
    echo "docker exec -it quicksales_db psql -U $DB_USER -d postgres"
    exit 1
fi
