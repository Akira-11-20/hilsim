#!/usr/bin/env python3
"""
Communication Delay Verification Test

This script tests the actual communication delay implementation against configured values.
It bypasses all PID control logic and focuses purely on measuring RTT with different delay settings.
"""

import zmq
import time
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import logging
from typing import Dict, List, Tuple
import threading
import queue
import argparse
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DelayVerificationServer:
    """Simple server that echoes messages with configured delays"""

    def __init__(self, port: int = 5555, delay_config: Dict = None):
        self.port = port
        self.delay_config = delay_config or {'processing': 0, 'response': 0, 'variation': 0}
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.running = False

    def apply_delay(self):
        """Apply configured delay with variation"""
        processing_delay = self.delay_config['processing'] / 1000.0  # ms to seconds
        response_delay = self.delay_config['response'] / 1000.0
        variation = self.delay_config['variation'] / 1000.0

        # Processing delay (fixed)
        if processing_delay > 0:
            time.sleep(processing_delay)

        # Response delay with random variation
        if response_delay > 0 or variation > 0:
            total_response_delay = response_delay
            if variation > 0:
                # Add random variation (uniform distribution)
                variation_amount = np.random.uniform(-variation, variation)
                total_response_delay += variation_amount

            # Ensure non-negative delay
            total_response_delay = max(0, total_response_delay)
            time.sleep(total_response_delay)

    def start(self):
        """Start the echo server"""
        self.socket.bind(f"tcp://*:{self.port}")
        self.running = True
        logger.info(f"Delay verification server started on port {self.port}")
        logger.info(f"Delay config: {self.delay_config}")

        message_count = 0

        while self.running:
            try:
                # Wait for request with timeout
                if self.socket.poll(timeout=100):  # 100ms timeout
                    message = self.socket.recv_string(zmq.NOBLOCK)
                    message_count += 1

                    # Apply configured delay
                    self.apply_delay()

                    # Parse message and add timestamp
                    try:
                        data = json.loads(message)
                        data['server_timestamp'] = time.time()
                        data['message_id'] = message_count
                        response = json.dumps(data)
                    except json.JSONDecodeError:
                        # Handle simple string messages
                        response = json.dumps({
                            'echo': message,
                            'server_timestamp': time.time(),
                            'message_id': message_count
                        })

                    self.socket.send_string(response)

                    if message_count % 100 == 0:
                        logger.info(f"Processed {message_count} messages")

            except zmq.Again:
                continue
            except Exception as e:
                logger.error(f"Server error: {e}")
                break

    def stop(self):
        """Stop the server"""
        self.running = False
        self.socket.close()
        self.context.term()


class DelayVerificationClient:
    """Client that measures RTT to the delay server"""

    def __init__(self, server_endpoint: str = "tcp://localhost:5555"):
        self.server_endpoint = server_endpoint
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.measurements = []

    def connect(self):
        """Connect to the server"""
        self.socket.connect(self.server_endpoint)
        logger.info(f"Connected to delay verification server at {self.server_endpoint}")

    def measure_rtt(self, num_samples: int = 100) -> List[Dict]:
        """Measure RTT for specified number of samples"""
        logger.info(f"Starting RTT measurement with {num_samples} samples...")

        measurements = []

        for i in range(num_samples):
            # Send ping message
            send_time = time.time()
            message = {
                'type': 'ping',
                'client_timestamp': send_time,
                'sample_id': i
            }

            self.socket.send_string(json.dumps(message))

            # Receive response
            response_str = self.socket.recv_string()
            receive_time = time.time()

            try:
                response = json.loads(response_str)

                # Calculate RTT
                rtt_ms = (receive_time - send_time) * 1000.0

                measurement = {
                    'sample_id': i,
                    'send_time': send_time,
                    'receive_time': receive_time,
                    'server_timestamp': response.get('server_timestamp', 0),
                    'rtt_ms': rtt_ms,
                    'message_id': response.get('message_id', 0)
                }

                measurements.append(measurement)

                if (i + 1) % 20 == 0:
                    logger.info(f"Completed {i + 1}/{num_samples} measurements, current RTT: {rtt_ms:.2f}ms")

                # Small delay between measurements to avoid overwhelming
                time.sleep(0.01)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode response: {e}")
                continue

        self.measurements.extend(measurements)
        return measurements

    def disconnect(self):
        """Disconnect from server"""
        self.socket.close()
        self.context.term()


def run_delay_verification_test(delay_configs: List[Dict], samples_per_config: int = 100) -> pd.DataFrame:
    """Run verification test for multiple delay configurations"""

    results = []

    for i, config in enumerate(delay_configs):
        logger.info(f"\n=== Testing Configuration {i+1}/{len(delay_configs)} ===")
        logger.info(f"Config: {config}")

        # Start server in background thread
        server = DelayVerificationServer(port=5555, delay_config=config)
        server_thread = threading.Thread(target=server.start)
        server_thread.daemon = True
        server_thread.start()

        # Wait for server to start
        time.sleep(0.5)

        try:
            # Create client and measure RTT
            client = DelayVerificationClient()
            client.connect()

            measurements = client.measure_rtt(samples_per_config)

            # Calculate statistics
            rtts = [m['rtt_ms'] for m in measurements]
            stats = {
                'config_name': config.get('name', f'Config_{i+1}'),
                'processing_delay_ms': config['processing'],
                'response_delay_ms': config['response'],
                'variation_ms': config['variation'],
                'total_config_delay_ms': config['processing'] + config['response'],
                'measured_rtt_avg_ms': np.mean(rtts),
                'measured_rtt_std_ms': np.std(rtts),
                'measured_rtt_min_ms': np.min(rtts),
                'measured_rtt_max_ms': np.max(rtts),
                'measured_rtt_median_ms': np.median(rtts),
                'sample_count': len(rtts),
                'timestamp': datetime.now().isoformat()
            }

            # Calculate overhead (difference between measured and configured)
            stats['system_overhead_ms'] = stats['measured_rtt_avg_ms'] - stats['total_config_delay_ms']

            results.append(stats)

            logger.info(f"Results: RTT={stats['measured_rtt_avg_ms']:.2f}±{stats['measured_rtt_std_ms']:.2f}ms, "
                       f"Range={stats['measured_rtt_min_ms']:.2f}-{stats['measured_rtt_max_ms']:.2f}ms")

            client.disconnect()

        except Exception as e:
            logger.error(f"Test failed for config {config}: {e}")
        finally:
            server.stop()
            time.sleep(0.2)  # Allow server to clean up

    return pd.DataFrame(results)


def create_verification_report(results_df: pd.DataFrame, output_prefix: str = "delay_verification"):
    """Create analysis report and visualizations"""

    # Save raw data to proper directory
    output_dir = 'analysis'
    os.makedirs(output_dir, exist_ok=True)

    csv_filename = f"{output_dir}/{output_prefix}_results.csv"
    results_df.to_csv(csv_filename, index=False)
    logger.info(f"Results saved to {csv_filename}")

    # Create visualization
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))

    # 1. Configured vs Measured RTT
    config_delays = results_df['total_config_delay_ms']
    measured_rtts = results_df['measured_rtt_avg_ms']
    measured_stds = results_df['measured_rtt_std_ms']

    ax1.errorbar(config_delays, measured_rtts, yerr=measured_stds,
                fmt='o', capsize=5, markersize=8, alpha=0.8)

    # Add ideal line (y = x + constant overhead)
    if len(results_df) > 1:
        # Estimate base overhead from no-delay configuration or regression
        base_overhead = np.mean(results_df['system_overhead_ms'])
        max_delay = max(config_delays)
        ideal_x = np.linspace(0, max_delay, 100)
        ideal_y = ideal_x + base_overhead
        ax1.plot(ideal_x, ideal_y, 'r--', alpha=0.7, label=f'Ideal (config + {base_overhead:.1f}ms)')

    ax1.set_xlabel('Configured Delay (ms)')
    ax1.set_ylabel('Measured RTT (ms)')
    ax1.set_title('Configured vs Measured Delay')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # Add correlation coefficient
    if len(config_delays) > 1:
        correlation = np.corrcoef(config_delays, measured_rtts)[0, 1]
        ax1.text(0.05, 0.95, f'Correlation: {correlation:.4f}',
                transform=ax1.transAxes, bbox=dict(boxstyle="round", facecolor='wheat'))

    # 2. System Overhead Analysis
    config_names = results_df['config_name']
    overheads = results_df['system_overhead_ms']

    bars = ax2.bar(range(len(config_names)), overheads, alpha=0.7)
    ax2.set_xlabel('Configuration')
    ax2.set_ylabel('System Overhead (ms)')
    ax2.set_title('System Overhead by Configuration')
    ax2.set_xticks(range(len(config_names)))
    ax2.set_xticklabels(config_names, rotation=45)
    ax2.grid(True, alpha=0.3)

    # Add average line
    avg_overhead = np.mean(overheads)
    ax2.axhline(y=avg_overhead, color='red', linestyle='--', alpha=0.7,
                label=f'Average: {avg_overhead:.1f}ms')
    ax2.legend()

    # 3. RTT Distribution (Box plot)
    # This would require raw measurement data, so we'll show range instead
    rtts_avg = results_df['measured_rtt_avg_ms']
    rtts_min = results_df['measured_rtt_min_ms']
    rtts_max = results_df['measured_rtt_max_ms']

    x_pos = range(len(config_names))
    ax3.errorbar(x_pos, rtts_avg,
                yerr=[rtts_avg - rtts_min, rtts_max - rtts_avg],
                fmt='o', capsize=5, markersize=8, alpha=0.8)

    ax3.set_xlabel('Configuration')
    ax3.set_ylabel('RTT (ms)')
    ax3.set_title('RTT Range by Configuration')
    ax3.set_xticks(x_pos)
    ax3.set_xticklabels(config_names, rotation=45)
    ax3.grid(True, alpha=0.3)

    # 4. Accuracy Analysis (Measured vs Expected)
    expected_rtts = config_delays + np.mean(overheads)  # Config + average overhead
    accuracy_errors = measured_rtts - expected_rtts

    ax4.bar(range(len(config_names)), accuracy_errors, alpha=0.7,
            color=['green' if x >= 0 else 'red' for x in accuracy_errors])
    ax4.set_xlabel('Configuration')
    ax4.set_ylabel('Error (Measured - Expected) ms')
    ax4.set_title('Delay Implementation Accuracy')
    ax4.set_xticks(range(len(config_names)))
    ax4.set_xticklabels(config_names, rotation=45)
    ax4.grid(True, alpha=0.3)
    ax4.axhline(y=0, color='black', linestyle='-', alpha=0.3)

    plt.tight_layout()

    # Save plot to proper directory
    output_dir = 'analysis'
    os.makedirs(output_dir, exist_ok=True)

    plot_filename = f"{output_dir}/{output_prefix}_analysis.png"
    plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
    logger.info(f"Analysis plot saved to {plot_filename}")

    # Print summary
    print("\n" + "="*60)
    print("DELAY VERIFICATION SUMMARY")
    print("="*60)

    for _, row in results_df.iterrows():
        print(f"\n{row['config_name']}:")
        print(f"  Configured: {row['processing_delay_ms']}ms + {row['response_delay_ms']}ms ± {row['variation_ms']}ms")
        print(f"  Measured RTT: {row['measured_rtt_avg_ms']:.1f} ± {row['measured_rtt_std_ms']:.1f}ms")
        print(f"  Range: {row['measured_rtt_min_ms']:.1f} - {row['measured_rtt_max_ms']:.1f}ms")
        print(f"  System Overhead: {row['system_overhead_ms']:.1f}ms")

    if len(results_df) > 1:
        avg_overhead = np.mean(results_df['system_overhead_ms'])
        std_overhead = np.std(results_df['system_overhead_ms'])
        correlation = np.corrcoef(results_df['total_config_delay_ms'],
                                 results_df['measured_rtt_avg_ms'])[0, 1]

        print(f"\nOverall Analysis:")
        print(f"  Average System Overhead: {avg_overhead:.1f} ± {std_overhead:.1f}ms")
        print(f"  Config-Measurement Correlation: {correlation:.4f}")

        if correlation > 0.95:
            print("  ✅ Excellent correlation - delay implementation is accurate")
        elif correlation > 0.8:
            print("  ✅ Good correlation - delay implementation works well")
        else:
            print("  ⚠️ Poor correlation - delay implementation may have issues")


def main():
    parser = argparse.ArgumentParser(description="Verify communication delay implementation accuracy")
    parser.add_argument('--samples', type=int, default=100,
                       help='Number of RTT samples per configuration (default: 100)')
    parser.add_argument('--output', type=str, default='delay_verification',
                       help='Output file prefix (default: delay_verification)')

    args = parser.parse_args()

    # Define test configurations
    test_configs = [
        {
            'name': 'No_Delay',
            'processing': 0,
            'response': 0,
            'variation': 0
        },
        {
            'name': 'Light_Delay',
            'processing': 5,
            'response': 3,
            'variation': 2
        },
        {
            'name': 'Medium_Delay',
            'processing': 10,
            'response': 5,
            'variation': 3
        },
        {
            'name': 'High_Delay',
            'processing': 20,
            'response': 10,
            'variation': 5
        },
        {
            'name': 'Very_High_Delay',
            'processing': 50,
            'response': 20,
            'variation': 10
        }
    ]

    logger.info("Starting communication delay verification test...")
    logger.info(f"Testing {len(test_configs)} configurations with {args.samples} samples each")

    # Run tests
    results_df = run_delay_verification_test(test_configs, args.samples)

    # Generate report
    create_verification_report(results_df, args.output)

    logger.info("Delay verification test completed!")


if __name__ == "__main__":
    main()