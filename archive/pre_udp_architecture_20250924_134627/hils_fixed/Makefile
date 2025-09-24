# Fixed HILS Makefile - REQ/REP Based Implementation

.PHONY: help build up down logs clean test

# Default target
help:
	@echo "Fixed HILS Control System - REQ/REP Based"
	@echo ""
	@echo "Available commands:"
	@echo "  build     - Build Docker containers"
	@echo "  up        - Start HILS simulation"
	@echo "  down      - Stop HILS simulation"
	@echo "  logs      - View logs from both services"
	@echo "  clean     - Clean Docker resources"
	@echo "  test      - Run short test (100 steps)"

build:
	@echo "Building Fixed HILS containers..."
	docker compose -f docker/compose.yaml build

up:
	@echo "Starting Fixed HILS simulation..."
	@echo "Run ID: $(shell date +%Y%m%d_%H%M%S)"
	docker compose -f docker/compose.yaml up --remove-orphans

down:
	@echo "Stopping Fixed HILS simulation..."
	docker compose -f docker/compose.yaml down

logs:
	@echo "=== Fixed HILS Logs ==="
	docker compose -f docker/compose.yaml logs

logs-plant:
	@echo "=== Fixed Plant Logs ==="
	docker compose -f docker/compose.yaml logs fixed-plant

logs-numeric:
	@echo "=== Fixed Numeric Logs ==="
	docker compose -f docker/compose.yaml logs fixed-numeric

clean:
	@echo "Cleaning Fixed HILS Docker resources..."
	docker compose -f docker/compose.yaml down --rmi all --volumes
	docker system prune -f

test:
	@echo "Running Fixed HILS test (100 steps)..."
	@# Override command for short test
	docker compose -f docker/compose.yaml run --rm fixed-numeric python -c "\
import sys; sys.path.append('.'); \
from numeric_client import FixedNumericClient; \
client = FixedNumericClient('tcp://fixed-plant:5555'); \
client.connect(); \
client.run_control_loop(100)"