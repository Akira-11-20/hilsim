#!/usr/bin/env python3
"""
Enhanced ZMQ Server with Configurable Delay and Jitter Simulation

Features:
- Configurable processing delay
- Configurable network simulation delay
- Jitter simulation (random variation)
- Real-time delay statistics
- Multiple delay distribution types
"""

import zmq
import time
import json
import sys
import os
import numpy as np
import threading
from queue import Queue
import argparse

class DelaySimulationServer:
    """Enhanced server with delay and jitter simulation capabilities"""

    def __init__(self, port=5555):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)

        # Delay configuration
        self.base_delay_ms = 0.0        # Base processing delay [ms]
        self.network_delay_ms = 0.0     # Network simulation delay [ms]
        self.jitter_ms = 0.0           # Jitter amplitude [ms]
        self.jitter_type = "uniform"   # uniform, gaussian, exponential

        # Statistics
        self.message_count = 0
        self.total_delay_applied = 0.0
        self.delay_history = []

        # Control flags
        self.running = True
        self.stats_interval = 100  # Print stats every N messages

    def configure_delay(self, base_delay_ms=0.0, network_delay_ms=0.0,
                       jitter_ms=0.0, jitter_type="uniform"):
        """
        Configure delay simulation parameters

        Args:
            base_delay_ms: Fixed processing delay [ms]
            network_delay_ms: Fixed network delay [ms]
            jitter_ms: Jitter amplitude [ms]
            jitter_type: Distribution type ("uniform", "gaussian", "exponential")
        """
        self.base_delay_ms = base_delay_ms
        self.network_delay_ms = network_delay_ms
        self.jitter_ms = jitter_ms
        self.jitter_type = jitter_type

        total_fixed_delay = base_delay_ms + network_delay_ms

        print(f"Delay Configuration:")
        print(f"  Base Processing: {base_delay_ms:.1f}ms")
        print(f"  Network Simulation: {network_delay_ms:.1f}ms")
        print(f"  Jitter: {jitter_ms:.1f}ms ({jitter_type})")
        print(f"  Total Fixed: {total_fixed_delay:.1f}ms")

    def generate_jitter(self):
        """Generate jitter based on configured distribution"""
        if self.jitter_ms <= 0:
            return 0.0

        if self.jitter_type == "uniform":
            return np.random.uniform(-self.jitter_ms, self.jitter_ms)
        elif self.jitter_type == "gaussian":
            return np.random.normal(0, self.jitter_ms / 3.0)  # 3σ = jitter_ms
        elif self.jitter_type == "exponential":
            # Exponential with mean = jitter_ms/2, clipped to [0, jitter_ms]
            return np.clip(np.random.exponential(self.jitter_ms / 2.0), 0, self.jitter_ms)
        else:
            return 0.0

    def apply_delay(self, delay_ms):
        """Apply delay with high precision"""
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    def process_message(self, message):
        """Process message with configured delays"""
        start_time = time.perf_counter()

        # Parse message
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            data = {"echo": message}

        # Generate total delay
        jitter = self.generate_jitter()
        total_delay_ms = self.base_delay_ms + self.network_delay_ms + jitter

        # Apply processing delay (simulates server computation)
        if self.base_delay_ms > 0:
            self.apply_delay(self.base_delay_ms)

        # Prepare response
        data.update({
            'server_timestamp': time.time(),
            'message_id': self.message_count,
            'applied_delay_ms': total_delay_ms,
            'base_delay_ms': self.base_delay_ms,
            'network_delay_ms': self.network_delay_ms,
            'jitter_ms': jitter,
            'server_processing_time_ms': (time.perf_counter() - start_time) * 1000
        })

        response = json.dumps(data)

        # Apply network delay (simulates network latency)
        if self.network_delay_ms + jitter > self.base_delay_ms:
            remaining_delay = (self.network_delay_ms + jitter) - self.base_delay_ms
            if remaining_delay > 0:
                self.apply_delay(remaining_delay)

        # Update statistics
        self.delay_history.append(total_delay_ms)
        self.total_delay_applied += total_delay_ms

        # Keep only recent history (for memory management)
        if len(self.delay_history) > 1000:
            self.delay_history = self.delay_history[-500:]

        return response

    def print_statistics(self):
        """Print delay statistics"""
        if len(self.delay_history) > 0:
            recent_delays = self.delay_history[-self.stats_interval:]
            avg_delay = np.mean(recent_delays)
            std_delay = np.std(recent_delays)
            min_delay = np.min(recent_delays)
            max_delay = np.max(recent_delays)

            print(f"Messages: {self.message_count}, "
                  f"Recent Delay: {avg_delay:.2f}±{std_delay:.2f}ms "
                  f"[{min_delay:.2f}-{max_delay:.2f}ms]")

    def run_server(self):
        """Run the delay simulation server"""

        self.socket.bind(f"tcp://*:{self.port}")
        print(f"Enhanced Echo Server with Delay Simulation started on port {self.port}")
        print("Ready to receive messages...")

        try:
            while self.running:
                # Receive message
                message = self.socket.recv_string()

                # Process with delay
                response = self.process_message(message)

                # Send response
                self.socket.send_string(response)

                self.message_count += 1

                # Print statistics periodically
                if self.message_count % self.stats_interval == 0:
                    self.print_statistics()

        except KeyboardInterrupt:
            print("Server stopping...")
        finally:
            self.socket.close()
            self.context.term()
            print("Server stopped")

def main():
    parser = argparse.ArgumentParser(description='Enhanced ZMQ Server with Delay Simulation')
    parser.add_argument('--port', type=int, default=5555, help='Server port')
    parser.add_argument('--base-delay', type=float, default=0.0, help='Base processing delay [ms]')
    parser.add_argument('--network-delay', type=float, default=0.0, help='Network delay [ms]')
    parser.add_argument('--jitter', type=float, default=0.0, help='Jitter amplitude [ms]')
    parser.add_argument('--jitter-type', choices=['uniform', 'gaussian', 'exponential'],
                       default='uniform', help='Jitter distribution type')

    args = parser.parse_args()

    # Create and configure server
    server = DelaySimulationServer(port=args.port)
    server.configure_delay(
        base_delay_ms=args.base_delay,
        network_delay_ms=args.network_delay,
        jitter_ms=args.jitter,
        jitter_type=args.jitter_type
    )

    # Environment variable overrides (for Docker)
    if 'DELAY_BASE_MS' in os.environ:
        args.base_delay = float(os.environ['DELAY_BASE_MS'])
    if 'DELAY_NETWORK_MS' in os.environ:
        args.network_delay = float(os.environ['DELAY_NETWORK_MS'])
    if 'DELAY_JITTER_MS' in os.environ:
        args.jitter = float(os.environ['DELAY_JITTER_MS'])
    if 'DELAY_JITTER_TYPE' in os.environ:
        args.jitter_type = os.environ['DELAY_JITTER_TYPE']

    # Reconfigure with environment variables
    server.configure_delay(
        base_delay_ms=args.base_delay,
        network_delay_ms=args.network_delay,
        jitter_ms=args.jitter,
        jitter_type=args.jitter_type
    )

    # Run server
    server.run_server()

if __name__ == "__main__":
    main()