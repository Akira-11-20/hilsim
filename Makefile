.PHONY: build up down logs clean status test help

# Python path - tries virtual env first, fallback to system python3
PYTHON := $(shell which python3 2>/dev/null || echo python3)

# Setup Python dependencies
setup:
	@echo "Installing Python dependencies..."
	$(PYTHON) -m pip install -r requirements.txt
	@echo "Dependencies installed."

# Build all Docker images
build:
	@echo "Building HILS Docker containers..."
	docker compose -f docker/compose.yaml build

# Start the HILS simulation
up:
	@echo "Starting HILS simulation..."
	@export RUN_ID=$$(date +%Y%m%d_%H%M%S) && \
	echo "Run ID: $$RUN_ID" && \
	RUN_ID=$$RUN_ID docker compose -f docker/compose.yaml up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@docker inspect hils-plant --format='Plant: {{.State.Health.Status}}' 2>/dev/null >/dev/null && \
	echo "✅ HILS simulation started successfully!" || \
	echo "❌ Failed to start HILS simulation"

# Stop the HILS simulation
down:
	@echo "Stopping HILS simulation..."
	docker compose -f docker/compose.yaml down

# Show logs from all services
logs:
	docker compose -f docker/compose.yaml logs -f --tail=200

# Show logs from plant only
logs-plant:
	docker compose -f docker/compose.yaml logs -f --tail=100 plant

# Show logs from numeric only
logs-numeric:
	docker compose -f docker/compose.yaml logs -f --tail=100 numeric

# Check status of services
status:
	@echo "=== Container Status ==="
	docker compose -f docker/compose.yaml ps
	@echo ""
	@echo "=== Health Checks ==="
	@docker inspect hils-plant --format='Plant: {{.State.Health.Status}}' 2>/dev/null || echo "Plant: Not running"
	@echo ""
	@echo "=== Log Files ==="
	@ls -la logs/ 2>/dev/null || echo "No logs directory found"

# Clean up containers and images
clean:
	@echo "Cleaning up Docker resources..."
	docker compose -f docker/compose.yaml down --rmi all --volumes
	docker system prune -f

# Run a quick test simulation
test: build up
	@echo "Running test simulation (30 seconds)..."
	@sleep 30
	@echo "=== Test Results ==="
	@echo "Plant log entries:"
	@wc -l logs/plant_log.csv 2>/dev/null || echo "No plant log found"
	@echo "Numeric log entries:"
	@wc -l logs/numeric_log.csv 2>/dev/null || echo "No numeric log found"
	@echo "=== Recent Plant Log Sample ==="
	@tail -n 5 logs/plant_log.csv 2>/dev/null || echo "No plant log found"
	@echo "=== Recent Numeric Log Sample ==="
	@tail -n 5 logs/numeric_log.csv 2>/dev/null || echo "No numeric log found"
	@$(MAKE) down

# Restart the simulation (generates new RUN_ID)
restart: down
	@$(MAKE) up

# Force rebuild and restart
rebuild: clean build up

# Monitor real-time performance
monitor:
	@echo "Monitoring HILS performance (Ctrl+C to stop)..."
	@while true; do \
		clear; \
		echo "=== HILS Real-time Monitor ==="; \
		echo "Time: $$(date)"; \
		echo ""; \
		echo "Container Status:"; \
		docker compose -f docker/compose.yaml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"; \
		echo ""; \
		echo "Recent Logs:"; \
		docker compose -f docker/compose.yaml logs --tail=3 plant 2>/dev/null | grep -E "(INFO|ERROR|WARNING)" || echo "No recent plant logs"; \
		docker compose -f docker/compose.yaml logs --tail=3 numeric 2>/dev/null | grep -E "(INFO|ERROR|WARNING)" || echo "No recent numeric logs"; \
		echo ""; \
		echo "Log Files:"; \
		ls -la logs/ 2>/dev/null || echo "No logs directory"; \
		sleep 5; \
	done

# Integrated log management and visualization
analyze:
	@echo "Running HILS analysis..."
	$(PYTHON) scripts/hils_analyzer.py visualize
	@echo "Analysis complete."

# Show log status
logs-status:
	$(PYTHON) scripts/hils_analyzer.py status



# Show help
help:
	@echo "HILS Simulation Makefile Commands:"
	@echo ""
	@echo "  setup     - Install Python dependencies"
	@echo "  build     - Build all Docker containers"
	@echo "  up        - Start the HILS simulation"
	@echo "  down      - Stop the HILS simulation"  
	@echo "  restart   - Restart the simulation (down + up)"
	@echo "  rebuild   - Force clean rebuild (clean + build + up)"
	@echo ""
	@echo "  logs      - Show logs from all services"
	@echo "  logs-plant    - Show logs from plant only"
	@echo "  logs-numeric  - Show logs from numeric only" 
	@echo "  monitor   - Real-time monitoring dashboard"
	@echo ""
	@echo "  status    - Check container and service status"
	@echo "  test      - Run a quick test simulation"
	@echo ""
	@echo "  analyze   - Run integrated log analysis and visualization"
	@echo "  logs-status - Show current log file status"
	@echo ""
	@echo "  clean     - Clean up all Docker resources"
	@echo ""
	@echo "  help      - Show this help message"

# Default target
all: build up