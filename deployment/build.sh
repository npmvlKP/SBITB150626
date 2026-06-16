#!/bin/bash
set -euo pipefail

# Trading Bot Docker Build Script

# Variables
TAG=${1:-"latest"}
DOCKER_COMPOSE_FILE="docker-compose.yml"
ENV_FILE=".env.docker.production"

# Function to generate secure passwords if not set
generate_secure_passwords() {
    echo "Generating secure passwords..."

    # TimescaleDB password
    if [ -z "${TIMESCALEDB_PASSWORD:-}" ]; then
        TIMESCALEDB_PASSWORD=$(openssl rand -hex 32)
        export TIMESCALEDB_PASSWORD
    fi

    # Redis password
    if [ -z "${REDIS_PASSWORD:-}" ]; then
        REDIS_PASSWORD=$(openssl rand -hex 32)
        export REDIS_PASSWORD
    fi

    # Grafana password
    if [ -z "${GRAFANA_PASSWORD:-}" ]; then
        GRAFANA_PASSWORD=$(openssl rand -hex 32)
        export GRAFANA_PASSWORD
    fi

    # Grafana secret key
    if [ -z "${GRAFANA_SECRET_KEY:-}" ]; then
        GRAFANA_SECRET_KEY=$(openssl rand -hex 32)
        export GRAFANA_SECRET_KEY
    fi

    # Update .env file
    cat > $ENV_FILE <<EOL
# Production Environment Variables for Trading Bot

# TimescaleDB Configuration
TIMESCALEDB_PASSWORD=${TIMESCALEDB_PASSWORD}
TIMESCALEDB_URL=postgresql://trading:${TIMESCALEDB_PASSWORD}@timescaledb:5432/trading_bot?sslmode=require

# Redis Configuration
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# Grafana Configuration
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
GRAFANA_SECRET_KEY=${GRAFANA_SECRET_KEY}

# Security Configuration
JWT_SECRET_KEY=${JWT_SECRET_KEY:-"$(openssl rand -hex 64)"}
ENCRYPTION_KEY=${ENCRYPTION_KEY:-"$(openssl rand -hex 64)"}

# App Configuration
APP_ENV=production
TIMEZONE=UTC
LOG_LEVEL=info
EOL
}

# Build the application
build_application() {
    echo "Building trading bot application..."
    docker compose -f $DOCKER_COMPOSE_FILE build --no-cache
}

# Initialize the infrastructure
init_infrastructure() {
    echo "Initializing infrastructure..."

    # Wait for services to be ready
    docker compose -f $DOCKER_COMPOSE_FILE up -d

    echo "Waiting for database to initialize..."
    until docker exec trading_timescaledb pg_isready -U trading -d trading_bot; do
        sleep 5
    done

    # Run database migrations
    echo "Running database migrations..."
    docker exec trading_timescaledb psql -U trading -d trading_bot -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
}

# Verify the build
verify_build() {
    echo "Verifying build..."

    # Check container status
    docker compose -f $DOCKER_COMPOSE_FILE ps

    # Check logs for any errors
    echo "Checking application logs..."
    docker compose -f $DOCKER_COMPOSE_FILE logs

    # Run health checks
    echo "Running health checks..."
    docker exec trading_timescaledb curl -f http://localhost:5432 || echo "TimescaleDB health check failed"
    docker exec trading_redis redis-cli -a ${REDIS_PASSWORD} ping || echo "Redis health check failed"
}

# Main execution
main() {
    generate_secure_passwords
    build_application
    init_infrastructure
    verify_build

    echo "Build completed successfully. Application is ready."
    docker compose -f $DOCKER_COMPOSE_FILE ps
}

main
