#!/usr/bin/env python3
"""
Generate detailed CSV results for RTT measurements
"""

import zmq
import time
import json
import numpy as np
import pandas as pd
from datetime import datetime
import os

def collect_detailed_measurements(server_endpoint, config_name, samples=200):
    """Collect detailed RTT measurements and save to CSV"""

    print(f"Collecting detailed measurements: {config_name}")
    print(f"Server: {server_endpoint}, Samples: {samples}")

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout

    measurements = []

    try:
        socket.connect(server_endpoint)
        time.sleep(0.5)  # Allow connection

        print("Starting measurements...")
        start_test_time = time.time()

        for i in range(samples):
            # High precision timing
            client_send_time = time.perf_counter()
            client_wall_time = time.time()

            message = {
                "type": "ping",
                "sequence": i,
                "client_send_time": client_send_time,
                "client_timestamp": client_wall_time
            }

            socket.send_string(json.dumps(message))
            response_str = socket.recv_string()

            client_recv_time = time.perf_counter()
            client_recv_wall_time = time.time()

            # Parse server response
            try:
                response = json.loads(response_str)
            except:
                response = {}

            # Calculate RTT
            client_rtt_ms = (client_recv_time - client_send_time) * 1000.0

            # Store detailed measurement
            measurement = {
                'test_config': config_name,
                'sequence': i,
                'timestamp': client_wall_time,
                'test_elapsed_sec': client_wall_time - start_test_time,

                # Client-side timing (high precision)
                'client_send_time': client_send_time,
                'client_recv_time': client_recv_time,
                'client_rtt_ms': client_rtt_ms,

                # Server-reported values
                'server_timestamp': response.get('server_timestamp', 0),
                'server_applied_delay_ms': response.get('applied_delay_ms', 0),
                'server_base_delay_ms': response.get('base_delay_ms', 0),
                'server_network_delay_ms': response.get('network_delay_ms', 0),
                'server_jitter_ms': response.get('jitter_ms', 0),
                'server_processing_time_ms': response.get('server_processing_time_ms', 0),
                'message_id': response.get('message_id', i),

                # Calculated values
                'estimated_network_overhead_ms': client_rtt_ms - response.get('applied_delay_ms', 0),
                'server_client_time_diff_ms': (response.get('server_timestamp', client_wall_time) - client_wall_time) * 1000
            }

            measurements.append(measurement)

            # Progress indicator
            if (i + 1) % 50 == 0:
                recent_rtts = [m['client_rtt_ms'] for m in measurements[-50:]]
                avg_rtt = np.mean(recent_rtts)
                std_rtt = np.std(recent_rtts)
                print(f"  {i+1}/{samples}: RTT={avg_rtt:.2f}±{std_rtt:.2f}ms")

        print(f"Completed {len(measurements)} measurements")
        return measurements

    except Exception as e:
        print(f"Error during measurement: {e}")
        return measurements  # Return partial results

    finally:
        socket.close()
        context.term()

def save_results_to_csv(measurements, config_name):
    """Save measurements to CSV file with timestamp"""

    if not measurements:
        print("No measurements to save")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Create results directory if it doesn't exist
    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    # Save detailed CSV
    df = pd.DataFrame(measurements)
    csv_filename = f"{results_dir}/rtt_detailed_{config_name}_{timestamp}.csv"
    df.to_csv(csv_filename, index=False)

    # Generate summary statistics
    summary = {
        'config_name': config_name,
        'timestamp': timestamp,
        'total_samples': len(measurements),
        'test_duration_sec': measurements[-1]['test_elapsed_sec'] if measurements else 0,

        # RTT statistics
        'rtt_mean_ms': float(df['client_rtt_ms'].mean()),
        'rtt_std_ms': float(df['client_rtt_ms'].std()),
        'rtt_min_ms': float(df['client_rtt_ms'].min()),
        'rtt_max_ms': float(df['client_rtt_ms'].max()),
        'rtt_median_ms': float(df['client_rtt_ms'].median()),
        'rtt_p95_ms': float(df['client_rtt_ms'].quantile(0.95)),
        'rtt_p99_ms': float(df['client_rtt_ms'].quantile(0.99)),

        # Server delay statistics
        'server_delay_mean_ms': float(df['server_applied_delay_ms'].mean()) if df['server_applied_delay_ms'].notna().any() else 0,
        'server_delay_std_ms': float(df['server_applied_delay_ms'].std()) if df['server_applied_delay_ms'].notna().any() else 0,

        # Jitter statistics
        'jitter_mean_ms': float(df['server_jitter_ms'].mean()) if df['server_jitter_ms'].notna().any() else 0,
        'jitter_std_ms': float(df['server_jitter_ms'].std()) if df['server_jitter_ms'].notna().any() else 0,
        'jitter_range_ms': float(df['server_jitter_ms'].max() - df['server_jitter_ms'].min()) if df['server_jitter_ms'].notna().any() else 0,

        # Network overhead
        'network_overhead_mean_ms': float(df['estimated_network_overhead_ms'].mean()) if df['estimated_network_overhead_ms'].notna().any() else 0,
        'network_overhead_std_ms': float(df['estimated_network_overhead_ms'].std()) if df['estimated_network_overhead_ms'].notna().any() else 0
    }

    # Save summary JSON
    summary_filename = f"{results_dir}/rtt_summary_{config_name}_{timestamp}.json"
    with open(summary_filename, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nResults saved:")
    print(f"  Detailed CSV: {csv_filename}")
    print(f"  Summary JSON: {summary_filename}")

    # Print summary
    print(f"\nSUMMARY for {config_name}:")
    print(f"  Samples: {summary['total_samples']}")
    print(f"  RTT: {summary['rtt_mean_ms']:.2f} ± {summary['rtt_std_ms']:.2f}ms")
    print(f"  Range: {summary['rtt_min_ms']:.2f} - {summary['rtt_max_ms']:.2f}ms")
    print(f"  P95: {summary['rtt_p95_ms']:.2f}ms, P99: {summary['rtt_p99_ms']:.2f}ms")
    if summary['server_delay_mean_ms'] > 0:
        print(f"  Server Delay: {summary['server_delay_mean_ms']:.2f} ± {summary['server_delay_std_ms']:.2f}ms")
    if summary['jitter_std_ms'] > 0:
        print(f"  Jitter: {summary['jitter_mean_ms']:.2f} ± {summary['jitter_std_ms']:.2f}ms")

    return csv_filename, summary_filename

def main():
    """Generate CSV results for available servers"""

    print("=== RTT Measurement CSV Generation ===")
    print(f"Time: {datetime.now()}")

    # Test configurations available
    test_configs = [
        {
            'name': 'baseline_bridge',
            'endpoint': 'tcp://localhost:5557',
            'description': 'Baseline Docker bridge network'
        },
        {
            'name': 'delay_30ms_fixed',
            'endpoint': 'tcp://localhost:5561',
            'description': '30ms fixed delay server'
        }
    ]

    results_generated = []

    for config in test_configs:
        print(f"\n{'='*60}")
        print(f"Testing: {config['description']}")
        print(f"{'='*60}")

        try:
            measurements = collect_detailed_measurements(
                config['endpoint'],
                config['name'],
                samples=300  # Increase samples for better statistics
            )

            if measurements:
                csv_file, summary_file = save_results_to_csv(measurements, config['name'])
                results_generated.append({
                    'config': config['name'],
                    'csv_file': csv_file,
                    'summary_file': summary_file,
                    'samples': len(measurements)
                })
            else:
                print(f"No measurements collected for {config['name']}")

        except Exception as e:
            print(f"Failed to test {config['name']}: {e}")

    # Final summary
    print(f"\n{'='*60}")
    print("CSV GENERATION COMPLETE")
    print(f"{'='*60}")

    for result in results_generated:
        print(f"✅ {result['config']}: {result['samples']} samples -> {result['csv_file']}")

    if results_generated:
        print(f"\nGenerated {len(results_generated)} CSV files with detailed RTT measurements")
        print("Use these files for further analysis, plotting, or integration testing")
    else:
        print("⚠️  No CSV files generated. Check if servers are running.")
        print("Run: docker compose up -d to start test servers")

if __name__ == "__main__":
    main()