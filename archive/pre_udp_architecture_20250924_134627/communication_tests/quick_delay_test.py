#!/usr/bin/env python3
"""
Quick delay verification test

Test delay simulation functionality directly without full integration
"""

import time
import numpy as np
import re
from plant.app.plant_communication import PlantCommunicator

def test_delay_simulation_directly():
    """Test delay simulation functionality directly"""

    print("=== Direct Delay Simulation Test ===\n")

    # Create communicator with localhost settings
    communicator = PlantCommunicator(
        state_pub_port=5555,
        cmd_sub_endpoint="tcp://localhost:5556"
    )

    # Test different delay configurations
    delay_configs = [
        (0, 0, 0, "No delay"),
        (5, 3, 1, "Light delay"),
        (15, 10, 3, "High delay"),
    ]

    results = []

    for proc_delay, resp_delay, var_delay, name in delay_configs:
        print(f"Testing: {name}")
        print(f"  Processing: {proc_delay}ms, Response: {resp_delay}ms, Variation: ±{var_delay}ms")

        # Configure delay
        communicator.configure_delay_simulation(
            enable=True,
            processing_delay_ms=proc_delay,
            response_delay_ms=resp_delay,
            delay_variation_ms=var_delay
        )

        # Test the delay function multiple times
        measured_delays = []

        for i in range(10):
            start_time = time.time()

            # Simulate command processing with delay
            test_command = [0, 0, 10.0]  # Mock command
            communicator._add_command_to_delay_queue(test_command)

            # Process the delayed command
            time.sleep(0.001)  # Small wait to ensure processing
            delayed_cmd = communicator.process_delayed_commands()

            if delayed_cmd is not None:
                elapsed = (time.time() - start_time) * 1000  # Convert to ms
                measured_delays.append(elapsed)

        if measured_delays:
            avg_delay = np.mean(measured_delays)
            expected_delay = proc_delay + resp_delay

            print(f"  Expected delay: ~{expected_delay}ms")
            print(f"  Measured delay: {avg_delay:.1f}ms (±{np.std(measured_delays):.1f}ms)")

            # Check if delay is in expected range
            if abs(avg_delay - expected_delay) < (expected_delay * 0.5 + 5):  # Allow 50% tolerance + 5ms
                print(f"  ✅ Delay simulation working correctly")
            else:
                print(f"  ❌ Delay simulation may have issues")

            results.append((name, expected_delay, avg_delay))
        else:
            print(f"  ❌ No delays measured")
            results.append((name, proc_delay + resp_delay, None))

        print()

    # Summary
    print("=== Summary ===")
    valid_results = [(name, expected, actual) for name, expected, actual in results if actual is not None]

    if len(valid_results) >= 2:
        print("Delay configuration impact:")
        for name, expected, actual in valid_results:
            difference = actual - expected if expected > 0 else actual
            print(f"  {name}: Expected {expected}ms → Measured {actual:.1f}ms (Diff: {difference:.1f}ms)")

        # Check linearity
        if len(valid_results) >= 3:
            expected_vals = [r[1] for r in valid_results]
            actual_vals = [r[2] for r in valid_results]

            # Calculate correlation
            if len(set(expected_vals)) > 1:  # Check if we have variation
                correlation = np.corrcoef(expected_vals, actual_vals)[0, 1]
                print(f"\nCorrelation between expected and measured delays: {correlation:.3f}")

                if correlation > 0.8:
                    print("✅ Strong positive correlation - delay settings are working!")
                elif correlation > 0.5:
                    print("⚠️ Moderate correlation - delay settings have some effect")
                else:
                    print("❌ Weak correlation - delay settings may not be working properly")

def check_delay_config_in_files():
    """Check current delay configuration in test files"""

    print("\n=== Current Delay Configuration ===")

    try:
        with open("plant/app/test_plant_communication.py", 'r') as f:
            content = f.read()

        # Extract delay configuration
        pattern = r'processing_delay_ms=([0-9.]+).*?response_delay_ms=([0-9.]+).*?delay_variation_ms=([0-9.]+)'
        match = re.search(pattern, content, re.DOTALL)

        if match:
            proc_delay = float(match.group(1))
            resp_delay = float(match.group(2))
            var_delay = float(match.group(3))

            print(f"Current settings in test_plant_communication.py:")
            print(f"  Processing delay: {proc_delay}ms")
            print(f"  Response delay: {resp_delay}ms")
            print(f"  Delay variation: ±{var_delay}ms")
            print(f"  Total expected delay: {proc_delay + resp_delay}ms")
        else:
            print("Could not parse delay configuration from file")

    except Exception as e:
        print(f"Error reading delay configuration: {e}")

if __name__ == "__main__":
    check_delay_config_in_files()
    test_delay_simulation_directly()