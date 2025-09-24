#!/usr/bin/env python3
"""
Enhanced ZMQ Client for Delay and Jitter Testing

Features:
- Comprehensive delay measurement
- Jitter analysis
- Real-time statistics
- CSV output for analysis
- Configurable test parameters
"""

import zmq
import time
import json
import numpy as np
import os
import sys
import csv
import argparse
from datetime import datetime

class EnhancedCommunicationTester:
    """Enhanced client for comprehensive communication testing"""

    def __init__(self, server_endpoint="tcp://server:5555"):
        self.server_endpoint = server_endpoint
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)

        # Test configuration
        self.samples = 500
        self.warmup_samples = 10
        self.timeout_ms = 5000

        # Data collection
        self.measurements = []
        self.test_start_time = None

        # Socket configuration
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)

    def configure_test(self, samples=500, warmup=10, timeout_ms=5000):
        """Configure test parameters"""
        self.samples = samples
        self.warmup_samples = warmup
        self.timeout_ms = timeout_ms
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)

    def connect_and_warmup(self):
        """Connect to server and perform warmup"""
        print(f"Connecting to {self.server_endpoint}")
        self.socket.connect(self.server_endpoint)

        print("Performing warmup...")
        for i in range(self.warmup_samples):
            try:
                self.socket.send_string(json.dumps({"type": "warmup", "seq": i}))
                self.socket.recv_string()
            except zmq.Again:
                print(f"Warmup timeout on sample {i}")

        print("Warmup completed")

    def run_measurement_test(self, test_name="enhanced_test"):
        """Run comprehensive measurement test"""

        print(f"\nStarting measurement test: {test_name}")
        print(f"Samples: {self.samples}")

        self.test_start_time = time.time()
        self.measurements = []

        for i in range(self.samples):
            # High precision client-side timing
            client_send_time = time.perf_counter()

            # Create test message
            message = {
                "type": "ping",
                "sequence": i,
                "client_send_time": client_send_time,
                "client_timestamp": time.time()
            }

            try:
                # Send message
                self.socket.send_string(json.dumps(message))

                # Receive response
                response_str = self.socket.recv_string()
                client_recv_time = time.perf_counter()

                # Parse response
                response = json.loads(response_str)

                # Calculate timings
                client_rtt_ms = (client_recv_time - client_send_time) * 1000.0

                # Extract server-reported delays
                server_delay_ms = response.get('applied_delay_ms', 0.0)
                base_delay_ms = response.get('base_delay_ms', 0.0)
                network_delay_ms = response.get('network_delay_ms', 0.0)
                jitter_ms = response.get('jitter_ms', 0.0)
                server_processing_ms = response.get('server_processing_time_ms', 0.0)

                # Store measurement
                measurement = {
                    'sequence': i,
                    'client_rtt_ms': client_rtt_ms,
                    'server_total_delay_ms': server_delay_ms,
                    'server_base_delay_ms': base_delay_ms,
                    'server_network_delay_ms': network_delay_ms,
                    'server_jitter_ms': jitter_ms,
                    'server_processing_ms': server_processing_ms,
                    'client_send_time': client_send_time,
                    'client_recv_time': client_recv_time,
                    'timestamp': time.time()
                }

                self.measurements.append(measurement)

                # Progress reporting
                if (i + 1) % 100 == 0:
                    recent_rtts = [m['client_rtt_ms'] for m in self.measurements[-100:]]
                    recent_avg = np.mean(recent_rtts)
                    recent_std = np.std(recent_rtts)
                    print(f"Sample {i+1}/{self.samples}, Recent RTT: {recent_avg:.2f}±{recent_std:.2f}ms")

            except zmq.Again:
                print(f"Timeout on sample {i}")
                continue

            except json.JSONDecodeError as e:
                print(f"JSON decode error on sample {i}: {e}")
                continue

        print(f"Measurement completed: {len(self.measurements)}/{self.samples} successful")

    def analyze_results(self, test_name="enhanced_test"):
        """Analyze and report results"""

        if not self.measurements:
            print("No measurements to analyze")
            return None

        # Convert to numpy arrays for analysis
        client_rtts = np.array([m['client_rtt_ms'] for m in self.measurements])
        server_delays = np.array([m['server_total_delay_ms'] for m in self.measurements])
        server_jitters = np.array([m['server_jitter_ms'] for m in self.measurements])
        server_processing = np.array([m['server_processing_ms'] for m in self.measurements])

        # Calculate comprehensive statistics
        results = {
            'test_name': test_name,
            'sample_count': len(self.measurements),
            'timestamp': datetime.now().isoformat(),

            # Client-side RTT measurements
            'client_rtt_avg_ms': float(np.mean(client_rtts)),
            'client_rtt_std_ms': float(np.std(client_rtts)),
            'client_rtt_min_ms': float(np.min(client_rtts)),
            'client_rtt_max_ms': float(np.max(client_rtts)),
            'client_rtt_median_ms': float(np.median(client_rtts)),
            'client_rtt_p95_ms': float(np.percentile(client_rtts, 95)),
            'client_rtt_p99_ms': float(np.percentile(client_rtts, 99)),

            # Server-reported delays
            'server_delay_avg_ms': float(np.mean(server_delays)),
            'server_delay_std_ms': float(np.std(server_delays)),
            'server_delay_min_ms': float(np.min(server_delays)),
            'server_delay_max_ms': float(np.max(server_delays)),

            # Jitter analysis
            'server_jitter_avg_ms': float(np.mean(server_jitters)),
            'server_jitter_std_ms': float(np.std(server_jitters)),
            'server_jitter_range_ms': float(np.max(server_jitters) - np.min(server_jitters)),

            # Server processing overhead
            'server_processing_avg_ms': float(np.mean(server_processing)),
            'server_processing_max_ms': float(np.max(server_processing)),

            # Network overhead estimation
            'estimated_network_overhead_ms': float(np.mean(client_rtts - server_delays))
        }

        return results

    def print_results(self, results):
        """Print formatted results"""

        print(f"\n{'='*60}")
        print(f"COMMUNICATION TEST RESULTS: {results['test_name']}")
        print(f"{'='*60}")
        print(f"Samples: {results['sample_count']}")
        print(f"Test Time: {results['timestamp']}")
        print()

        print("CLIENT-SIDE RTT MEASUREMENTS:")
        print(f"  Average: {results['client_rtt_avg_ms']:.3f} ± {results['client_rtt_std_ms']:.3f}ms")
        print(f"  Range: {results['client_rtt_min_ms']:.3f} - {results['client_rtt_max_ms']:.3f}ms")
        print(f"  Median: {results['client_rtt_median_ms']:.3f}ms")
        print(f"  95th percentile: {results['client_rtt_p95_ms']:.3f}ms")
        print(f"  99th percentile: {results['client_rtt_p99_ms']:.3f}ms")
        print()

        print("SERVER-REPORTED DELAYS:")
        print(f"  Average: {results['server_delay_avg_ms']:.3f} ± {results['server_delay_std_ms']:.3f}ms")
        print(f"  Range: {results['server_delay_min_ms']:.3f} - {results['server_delay_max_ms']:.3f}ms")
        print()

        print("JITTER ANALYSIS:")
        print(f"  Average: {results['server_jitter_avg_ms']:.3f} ± {results['server_jitter_std_ms']:.3f}ms")
        print(f"  Range: {results['server_jitter_range_ms']:.3f}ms")
        print()

        print("SERVER PROCESSING:")
        print(f"  Average: {results['server_processing_avg_ms']:.4f}ms")
        print(f"  Maximum: {results['server_processing_max_ms']:.4f}ms")
        print()

        print("NETWORK ANALYSIS:")
        print(f"  Estimated Overhead: {results['estimated_network_overhead_ms']:.3f}ms")

    def save_results(self, results, detailed=True):
        """Save results to files"""

        # Save summary JSON
        summary_file = f"/app/results_{results['test_name']}_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Summary saved to: {summary_file}")

        if detailed and self.measurements:
            # Save detailed CSV
            csv_file = f"/app/results_{results['test_name']}_detailed.csv"
            with open(csv_file, 'w', newline='') as f:
                if self.measurements:
                    fieldnames = self.measurements[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(self.measurements)
            print(f"Detailed data saved to: {csv_file}")

    def cleanup(self):
        """Clean up resources"""
        self.socket.close()
        self.context.term()

def main():
    parser = argparse.ArgumentParser(description='Enhanced Communication Tester')
    parser.add_argument('--server', default='tcp://server:5555', help='Server endpoint')
    parser.add_argument('--samples', type=int, default=500, help='Number of samples')
    parser.add_argument('--warmup', type=int, default=10, help='Warmup samples')
    parser.add_argument('--timeout', type=int, default=5000, help='Timeout in ms')
    parser.add_argument('--test-name', default='enhanced_test', help='Test name')

    args = parser.parse_args()

    # Environment variable overrides
    server_endpoint = os.getenv('SERVER_ENDPOINT', args.server)
    samples = int(os.getenv('SAMPLES', args.samples))
    test_name = os.getenv('TEST_NAME', args.test_name)

    # Create and configure tester
    tester = EnhancedCommunicationTester(server_endpoint)
    tester.configure_test(samples=samples, warmup=args.warmup, timeout_ms=args.timeout)

    try:
        # Run test sequence
        tester.connect_and_warmup()
        tester.run_measurement_test(test_name)

        # Analyze and report
        results = tester.analyze_results(test_name)
        if results:
            tester.print_results(results)
            tester.save_results(results, detailed=True)
            print(f"\n✅ Test {test_name} completed successfully")
        else:
            print(f"\n❌ Test {test_name} failed - no results")
            sys.exit(1)

    except Exception as e:
        print(f"Test error: {e}")
        sys.exit(1)

    finally:
        tester.cleanup()

if __name__ == "__main__":
    main()