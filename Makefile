.PHONY: build up up-bg down logs clean status test help

# UV-based Python dependency management
UV := $(shell which uv 2>/dev/null || echo "uv-not-found")

# Default Docker Compose file (override with `make COMPOSE_FILE=...`)
COMPOSE_FILE ?= docker-compose.yml

# Setup Python dependencies with uv
setup:
	@echo "Setting up Python environment with uv..."
	@if [ "$(UV)" = "uv-not-found" ]; then \
		echo "❌ uv not found. Please install uv first:"; \
		echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; \
	fi
	$(UV) sync
	@echo "✅ Dependencies installed with uv."

# Install development dependencies
setup-dev: setup
	@echo "Installing development dependencies..."
	$(UV) sync --extra dev
	@echo "✅ Development dependencies installed."

# Build all Docker images
build:
	@echo "Building HILS Docker containers..."
	docker compose -f $(COMPOSE_FILE) build

# Start the HILS simulation and wait for completion
up:
	@echo "Starting HILS simulation..."
	@export RUN_ID=$$(date +%Y%m%d_%H%M%S) && \
	echo "Run ID: $$RUN_ID" && \
	echo "⏳ Running simulation... (This will take ~40 seconds)" && \
	RUN_ID=$$RUN_ID docker compose -f $(COMPOSE_FILE) up

# Start the HILS simulation in background (detached mode)
up-bg:
	@echo "Starting HILS simulation in background..."
	@export RUN_ID=$$(date +%Y%m%d_%H%M%S) && \
	echo "Run ID: $$RUN_ID" && \
	RUN_ID=$$RUN_ID docker compose -f $(COMPOSE_FILE) up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@docker inspect hils-plant --format='Plant: {{.State.Health.Status}}' 2>/dev/null >/dev/null && \
	echo "✅ HILS simulation started successfully!" || \
	echo "❌ Failed to start HILS simulation"

# Stop the HILS simulation
down:
	@echo "Stopping HILS simulation..."
	docker compose -f $(COMPOSE_FILE) down

# Show logs from all services
logs:
	docker compose -f $(COMPOSE_FILE) logs -f --tail=200

# Show logs from plant only
logs-plant:
	docker compose -f $(COMPOSE_FILE) logs -f --tail=100 plant

# Show logs from numeric only
logs-numeric:
	docker compose -f $(COMPOSE_FILE) logs -f --tail=100 numeric

# Check status of services
status:
	@echo "=== Container Status ==="
	docker compose -f $(COMPOSE_FILE) ps
	@echo ""
	@echo "=== Health Checks ==="
	@docker inspect hils-plant --format='Plant: {{.State.Health.Status}}' 2>/dev/null || echo "Plant: Not running"
	@echo ""
	@echo "=== Log Files ==="
	@ls -la logs/ 2>/dev/null || echo "No logs directory found"

# Clean up containers and images
clean:
	@echo "Cleaning up Docker resources..."
	docker compose -f $(COMPOSE_FILE) down --rmi all --volumes
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

# Test communication modules only (no Docker)
test-comm:
	@echo "Testing communication logic (recommended)..."
	cd communication_tests && $(UV) run python delay_logic_test.py
	@echo "Communication logic test complete."

# Test communication with delay simulation
test-comm-delay:
	@echo "Testing communication modules with delay simulation..."
	cd communication_tests && $(UV) run python test_communication_integration.py --duration 10 --delay
	@echo "Communication delay test complete."

# RTT monitoring test
test-rtt:
	@echo "Starting RTT monitoring..."
	cd communication_tests && $(UV) run python rtt_monitor.py

# Test Plant communication module only
test-plant-comm:
	@echo "Testing Plant communication module..."
	cd plant/app && $(UV) run python test_plant_communication.py --duration 15
	@echo "Plant communication test complete."

# Test Numeric communication module only
test-numeric-comm:
	@echo "Testing Numeric communication module..."
	cd numeric/app && $(UV) run python test_numeric_communication.py --duration 15
	@echo "Numeric communication test complete."

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
		docker compose -f $(COMPOSE_FILE) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"; \
		echo ""; \
		echo "Recent Logs:"; \
		docker compose -f $(COMPOSE_FILE) logs --tail=3 plant 2>/dev/null | grep -E "(INFO|ERROR|WARNING)" || echo "No recent plant logs"; \
		docker compose -f $(COMPOSE_FILE) logs --tail=3 numeric 2>/dev/null | grep -E "(INFO|ERROR|WARNING)" || echo "No recent numeric logs"; \
		echo ""; \
		echo "Log Files:"; \
		ls -la logs/ 2>/dev/null || echo "No logs directory"; \
		sleep 5; \
	done

# Integrated log management and visualization
analyze:
	@echo "Running HILS analysis..."
	$(UV) run python scripts/hils_analyzer.py visualize
	@echo "Analysis complete."

analyze-all:
	@echo "Running full HILS analysis..."
	$(UV) run python scripts/hils_analyzer.py analyze-all
	@echo "Full analysis complete."

# Communication structure analysis
analyze-comm:
	@echo "Running communication structure analysis..."
	cd analysis && $(UV) run python communication_flow_analysis.py
	@echo "Communication analysis complete."

# Delay pattern comparison analysis
analyze-delay:
	@echo "Creating delay pattern comparison..."
	cd analysis && $(UV) run python create_delay_comparison.py
	@echo "Delay analysis complete."

# Show log status
logs-status:
	$(UV) run python scripts/hils_analyzer.py status

# Show help
help:
	@echo "HILS Simulation Makefile Commands:"
	@echo ""
	@echo "  setup     - Install Python dependencies with uv"
	@echo "  setup-dev - Install Python dependencies with dev tools"
	@echo "  build     - Build all Docker containers"
	@echo "  up        - Start the HILS simulation and wait for completion"
	@echo "  up-bg     - Start the HILS simulation in background"
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
	@echo "  test-comm - Test communication modules (no Docker)"
	@echo "  test-comm-delay - Test communication with delay simulation"
	@echo "  test-plant-comm - Test Plant communication module only"
	@echo "  test-numeric-comm - Test Numeric communication module only"
	@echo ""
	@echo "  analyze   - Run integrated log analysis and visualization"
	@echo "  logs-status - Show current log file status"
	@echo ""
	@echo "  clean     - Clean up all Docker resources"
	@echo ""
	@echo "  help      - Show this help message"

# Default target
all: build up
