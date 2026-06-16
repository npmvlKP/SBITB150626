#!/bin/bash
set -euo pipefail

# Trading Bot Infrastructure Test Script

# Load environment variables
source .env.docker.production

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print test result
print_result() {
    if [ "$1" -eq 0 ]; then
        echo -e "${GREEN}[PASS]${NC} $2"
    else
        echo -e "${RED}[FAIL]${NC} $2"
        exit 1
    fi
}

# Test 1: Container status
echo -e "${YELLOW}=== Testing container status ===${NC}"
docker compose -f docker-compose.yml ps
docker compose -f docker-compose.yml ps | grep -q "healthy" || docker compose -f docker-compose.yml logs
sleep 10 # Wait for containers to initialize fully

# Test 2: TimescaleDB connection and basic functionality
echo -e "${YELLOW}=== Testing TimescaleDB ===${NC}"
docker exec trading_timescaledb pg_isready -U trading -d trading_bot
docker exec trading_timescaledb psql -U trading -d trading_bot -c "SELECT 1;" >/dev/null 2>&1
print_result $? "TimescaleDB basic connectivity"

docker exec trading_timescaledb psql -U trading -d trading_bot -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';" | grep -q "audit_events"
print_result $? "TimescaleDB contains audit_events table"

docker exec trading_timescaledb psql -U trading -d trading_bot -c "SELECT count(*) FROM audit_events;" >/dev/null 2>&1
print_result $? "TimescaleDB can query audit_events table"

docker exec trading_timescaledb psql -U trading -d trading_bot -c "SELECT hypertable_relation_size('audit_events');" >/dev/null 2>&1
print_result $? "TimescaleDB audit hypertable exists"

# Test 3: Redis connection and basic functionality
echo -e "${YELLOW}=== Testing Redis ===${NC}"
docker exec trading_redis redis-cli -a "$REDIS_PASSWORD" ping | grep -q "PONG"
print_result $? "Redis basic connectivity"

docker exec trading_redis redis-cli -a "$REDIS_PASSWORD" set test_key test_value >/dev/null 2>&1
docker exec trading_redis redis-cli -a "$REDIS_PASSWORD" get test_key | grep -q "test_value"
print_result $? "Redis set/get operations"

docker exec trading_redis redis-cli -a "$REDIS_PASSWORD" del test_key >/dev/null 2>&1
print_result $? "Redis delete operation"

# Test 4: Prometheus metrics
echo -e "${YELLOW}=== Testing Prometheus ===${NC}"
curl -s -f http://localhost:9090/-/healthy >/dev/null 2>&1
print_result $? "Prometheus health check"

curl -s -f http://localhost:9090/metrics | grep -q "prometheus_build_info"
print_result $? "Prometheus metrics endpoint"

# Test 5: Grafana availability
echo -e "${YELLOW}=== Testing Grafana ===${NC}"
curl -s -f "http://admin:${GRAFANA_PASSWORD}@localhost:3000/api/health" >/dev/null 2>&1
print_result $? "Grafana health check"

# Test 6: Network isolation
echo -e "${YELLOW}=== Testing network isolation ===${NC}"
docker exec trading_redis ping -c 1 timescaledb >/dev/null 2>&1
print_result $? "Redis can reach TimescaleDB"

docker exec trading_timescaledb ping -c 1 redis >/dev/null 2>&1
print_result $? "TimescaleDB can reach Redis"

# Test 7: Volume persistence
echo -e "${YELLOW}=== Testing volume persistence ===${NC}"
# Create test files
docker exec trading_timescaledb touch /var/lib/postgresql/data/test_persistence
docker exec trading_redis touch /data/test_persistence

# Restart containers
docker compose -f docker-compose.yml restart

# Verify test files still exist
docker exec trading_timescaledb ls /var/lib/postgresql/data/test_persistence >/dev/null 2>&1
print_result $? "TimescaleDB volume persistence"

docker exec trading_redis ls /data/test_persistence >/dev/null 2>&1
print_result $? "Redis volume persistence"

# Clean up test files
docker exec trading_timescaledb rm -f /var/lib/postgresql/data/test_persistence
docker exec trading_redis rm -f /data/test_persistence

# Test 8: Security settings
echo -e "${YELLOW}=== Testing security settings ===${NC}"
docker compose -f docker-compose.yml ps | grep trading_timescaledb | grep -q "no-new-privileges"
print_result $? "TimescaleDB no-new-privileges security option"

docker compose -f docker-compose.yml ps | grep trading_redis | grep -q "no-new-privileges"
print_result $? "Redis no-new-privileges security option"

# Test 9: Resource limits
echo -e "${YELLOW}=== Testing resource limits ===${NC}"
docker stats --no-stream | grep trading_timescaledb | awk '{print $3}' | grep -q "2.00%"
print_result $? "TimescaleDB CPU limit enforced"

docker stats --no-stream | grep trading_redis | awk '{print $3}' | grep -q "1.00%"
print_result $? "Redis CPU limit enforced"

# Test 10: Audit trail features
echo -e "${YELLOW}=== Testing audit trail features ===${NC}"
# Test that we can insert but not update/delete
docker exec trading_timescaledb psql -U trading -d trading_bot -c "
    INSERT INTO audit_events (event_id, timestamp, event_type, source, details, checksum)
    VALUES ('$(uuidgen)', NOW(), 'test_event', 'test_script', '{}', 'test_checksum')
    ON CONFLICT DO NOTHING;
" >/dev/null 2>&1
print_result $? "Audit events insert permission"

docker exec trading_timescaledb psql -U trading -d trading_bot -c "
    UPDATE audit_events SET details = 'updated' WHERE event_type = 'test_event';
" 2>&1 | grep -q "Updates not permitted"
print_result $? "Audit events update prevention"

docker exec trading_timescaledb psql -U trading -d trading_bot -c "
    DELETE FROM audit_events WHERE event_type = 'test_event';
" 2>&1 | grep -q "Deletion not permitted"
print_result $? "Audit events delete prevention"

# Clean up
docker exec trading_timescaledb psql -U trading -d trading_bot -c "
    DELETE FROM audit_events WHERE event_type = 'test_event';
"

echo -e "${GREEN}=== All tests passed successfully! ===${NC}"
echo "Infrastructure is ready for production."
