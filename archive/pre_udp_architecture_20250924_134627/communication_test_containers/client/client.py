#!/usr/bin/env python3
"""
Minimal ZMQ Client for Communication Overhead Testing
"""

import zmq
import time
import json
import numpy as np
import os
import sys

def measure_communication_overhead(server_endpoint="tcp://server:5555", samples=500, test_name="default"):
    """Measure pure communication overhead with minimal processing"""

    print(f"Testing communication overhead: {test_name}")
    print(f"Server: {server_endpoint}")
    print(f"Samples: {samples}")

    context = zmq.Context()
    socket = context.socket(zmq.REQ)

    # Set socket options for performance
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout

    try:
        socket.connect(server_endpoint)
        print("Connected to server")

        # Warm up
        for _ in range(10):
            socket.send_string(json.dumps({"type": "warmup"}))
            socket.recv_string()

        print("Starting measurements...")

        rtts = []

        for i in range(samples):
            # High precision timing
            start_time = time.perf_counter()

            # Send minimal message
            message = {
                "type": "ping",
                "sequence": i,
                "client_timestamp": start_time
            }

            socket.send_string(json.dumps(message))
            response = socket.recv_string()

            end_time = time.perf_counter()

            # Calculate RTT in milliseconds
            rtt_ms = (end_time - start_time) * 1000.0
            rtts.append(rtt_ms)

            if (i + 1) % 100 == 0:
                avg_rtt = np.mean(rtts[-100:])
                print(f"Sample {i+1}/{samples}, Recent RTT: {avg_rtt:.2f}ms")

        # Calculate statistics
        rtts = np.array(rtts)

        results = {
            'test_name': test_name,
            'sample_count': len(rtts),
            'rtt_avg_ms': float(np.mean(rtts)),
            'rtt_std_ms': float(np.std(rtts)),
            'rtt_min_ms': float(np.min(rtts)),
            'rtt_max_ms': float(np.max(rtts)),
            'rtt_median_ms': float(np.median(rtts)),
            'rtt_p95_ms': float(np.percentile(rtts, 95)),
            'rtt_p99_ms': float(np.percentile(rtts, 99))
        }

        print(f"\nResults for {test_name}:")
        print(f"  Average RTT: {results['rtt_avg_ms']:.2f} ± {results['rtt_std_ms']:.2f}ms")
        print(f"  Range: {results['rtt_min_ms']:.2f} - {results['rtt_max_ms']:.2f}ms")
        print(f"  Median: {results['rtt_median_ms']:.2f}ms")
        print(f"  95th percentile: {results['rtt_p95_ms']:.2f}ms")
        print(f"  99th percentile: {results['rtt_p99_ms']:.2f}ms")

        # Save results
        output_file = f"/app/results_{test_name}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"Results saved to {output_file}")

        return results

    except zmq.error.Again:
        print("ERROR: Connection timeout")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None
    finally:
        socket.close()
        context.term()

def main():
    # Get test configuration from environment
    server_endpoint = os.getenv('SERVER_ENDPOINT', 'tcp://server:5555')
    samples = int(os.getenv('SAMPLES', '500'))
    test_name = os.getenv('TEST_NAME', 'minimal_docker')

    # Wait for server to be ready
    print("Waiting for server to be ready...")
    time.sleep(2)

    # Run test
    results = measure_communication_overhead(server_endpoint, samples, test_name)

    if results:
        print(f"\n✅ Test {test_name} completed successfully")
    else:
        print(f"\n❌ Test {test_name} failed")
        sys.exit(1)

if __name__ == "__main__":
    main()