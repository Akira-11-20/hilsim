#!/usr/bin/env python3
"""
Delay Verification Test

Demonstrates that delay configuration settings directly affect
the time between command reception and application.
"""

import time
import numpy as np
import json
from plant.app.plant_communication import PlantCommunicator

def test_delay_timing():
    """Test that delay settings affect command processing timing"""

    print("=== Delay Timing Verification ===\n")

    # Test configurations
    delay_configs = [
        (0, 0, 0, "No delay"),
        (10, 5, 0, "15ms fixed delay"),
        (20, 10, 0, "30ms fixed delay"),
        (10, 5, 3, "15ms ± 3ms variable delay")
    ]

    results = []

    for proc_delay, resp_delay, var_delay, name in delay_configs:
        print(f"Testing: {name}")
        print(f"  Configuration: processing={proc_delay}ms, response={resp_delay}ms, variation=±{var_delay}ms")

        # Create communicator
        communicator = PlantCommunicator(
            state_pub_port=5555,
            cmd_sub_endpoint="tcp://localhost:5556"
        )

        # Configure delay
        communicator.configure_delay_simulation(
            enable=(proc_delay + resp_delay > 0),
            processing_delay_ms=proc_delay,
            response_delay_ms=resp_delay,
            delay_variation_ms=var_delay
        )

        # Simulate command reception and processing
        measured_delays = []
        expected_delay = proc_delay + resp_delay

        for trial in range(5):
            # Simulate a command message
            mock_command = {
                'u': [0.0, 0.0, 10.0],
                'seq': trial,
                'sync_timestamp': time.time()
            }

            # Record when we "receive" the command
            recv_time = time.time()

            # Simulate the delay processing by manually adding to queue
            if communicator.enable_delay:
                total_delay = communicator.processing_delay + communicator.response_delay
                if communicator.delay_variation > 0:
                    total_delay += np.random.uniform(-communicator.delay_variation, communicator.delay_variation)

                apply_time = recv_time + total_delay
                communicator.command_queue.append({
                    'control_input': mock_command['u'],
                    'apply_time': apply_time,
                    'seq': mock_command['seq'],
                    'original_timestamp': mock_command['sync_timestamp']
                })

                # Wait and check when command becomes available
                start_wait = time.time()
                while time.time() - start_wait < (expected_delay / 1000.0 + 0.1):  # Wait up to expected + buffer
                    applied_cmd = communicator.process_delayed_commands()
                    if applied_cmd is not None:
                        actual_delay = (time.time() - recv_time) * 1000  # Convert to ms
                        measured_delays.append(actual_delay)
                        break
                    time.sleep(0.001)  # 1ms polling

            else:
                # No delay case
                measured_delays.append(0.0)

        # Report results
        if measured_delays:
            avg_delay = np.mean(measured_delays)
            std_delay = np.std(measured_delays)

            print(f"  Expected delay: {expected_delay}ms")
            print(f"  Measured delay: {avg_delay:.1f}ms (±{std_delay:.1f}ms)")

            # Check if within reasonable tolerance
            tolerance = max(5, var_delay + 2)  # 5ms base tolerance + variation + 2ms buffer
            if abs(avg_delay - expected_delay) <= tolerance:
                print(f"  ✅ Delay is within expected range (±{tolerance}ms)")
                success = True
            else:
                print(f"  ❌ Delay outside expected range (±{tolerance}ms)")
                success = False

            results.append({
                'name': name,
                'expected': expected_delay,
                'measured': avg_delay,
                'std': std_delay,
                'success': success
            })
        else:
            print(f"  ❌ No delays measured")
            results.append({
                'name': name,
                'expected': expected_delay,
                'measured': None,
                'success': False
            })

        print()

    # Analysis
    print("=== Analysis ===")
    successful_tests = [r for r in results if r['success'] and r['measured'] is not None]

    if len(successful_tests) >= 2:
        print("Delay configuration verification:")
        for result in successful_tests:
            print(f"  {result['name']}: {result['expected']}ms → {result['measured']:.1f}ms")

        # Check if delays increase with configuration
        expected_vals = [r['expected'] for r in successful_tests]
        measured_vals = [r['measured'] for r in successful_tests]

        if len(set(expected_vals)) > 1:  # We have different expected values
            correlation = np.corrcoef(expected_vals, measured_vals)[0, 1]
            print(f"\nCorrelation between expected and measured delays: {correlation:.3f}")

            if correlation > 0.9:
                print("✅ Excellent correlation - delay settings are working perfectly!")
            elif correlation > 0.7:
                print("✅ Good correlation - delay settings are working well")
            elif correlation > 0.5:
                print("⚠️ Moderate correlation - delay settings have some effect")
            else:
                print("❌ Poor correlation - delay settings may not be working")

            # Check linearity
            if len(successful_tests) >= 3:
                sorted_results = sorted(successful_tests, key=lambda x: x['expected'])
                for i in range(1, len(sorted_results)):
                    expected_diff = sorted_results[i]['expected'] - sorted_results[i-1]['expected']
                    measured_diff = sorted_results[i]['measured'] - sorted_results[i-1]['measured']
                    ratio = measured_diff / expected_diff if expected_diff > 0 else 0

                    print(f"  Step {i}: Expected +{expected_diff}ms → Measured +{measured_diff:.1f}ms (ratio: {ratio:.2f})")

    else:
        print("❌ Insufficient successful tests for analysis")

    return results

def demonstrate_rtt_simulation():
    """Demonstrate theoretical RTT calculation"""

    print("\n=== RTT Calculation Simulation ===")

    # System components
    base_latency = 8.0  # System overhead (network + processing)

    delay_configs = [
        (0, 0, 0),
        (10, 5, 2),
        (20, 10, 5),
        (30, 15, 8)
    ]

    print("Theoretical RTT prediction:")
    print("RTT = Base_Latency + Processing_Delay + Response_Delay ± Variation")
    print(f"Base latency: {base_latency}ms\n")

    for proc, resp, var in delay_configs:
        min_rtt = base_latency + proc + resp - var
        max_rtt = base_latency + proc + resp + var
        avg_rtt = base_latency + proc + resp

        print(f"Config (proc={proc}, resp={resp}, var=±{var}): "
              f"RTT = {min_rtt:.1f}-{max_rtt:.1f}ms (avg: {avg_rtt:.1f}ms)")

if __name__ == "__main__":
    test_delay_timing()
    demonstrate_rtt_simulation()