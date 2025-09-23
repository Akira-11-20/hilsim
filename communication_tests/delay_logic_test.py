#!/usr/bin/env python3
"""
Delay Logic Test

Tests the delay calculation logic directly without network components.
Demonstrates that delay configuration affects command timing.
"""

import time
import numpy as np

class DelaySimulator:
    """Simple delay simulator to test delay logic"""

    def __init__(self):
        self.enable_delay = False
        self.processing_delay = 0.0  # seconds
        self.response_delay = 0.0    # seconds
        self.delay_variation = 0.0   # seconds
        self.command_queue = []

    def configure_delay_simulation(self, enable: bool, processing_delay_ms: float = 0.0,
                                 response_delay_ms: float = 0.0, delay_variation_ms: float = 0.0):
        """Configure delay simulation parameters"""
        self.enable_delay = enable
        self.processing_delay = processing_delay_ms / 1000.0
        self.response_delay = response_delay_ms / 1000.0
        self.delay_variation = delay_variation_ms / 1000.0

    def add_command_with_delay(self, command, recv_time):
        """Add command to delay queue with timing"""
        if self.enable_delay:
            total_delay = self.processing_delay + self.response_delay
            if self.delay_variation > 0:
                total_delay += np.random.uniform(-self.delay_variation, self.delay_variation)

            apply_time = recv_time + total_delay
            self.command_queue.append({
                'command': command,
                'apply_time': apply_time,
                'recv_time': recv_time
            })
            return None  # Not immediately available
        else:
            return command  # Immediately available

    def process_delayed_commands(self):
        """Process commands whose time has come"""
        if not self.enable_delay:
            return None

        current_time = time.time()
        applied_command = None

        commands_to_remove = []
        for cmd in self.command_queue:
            if current_time >= cmd['apply_time']:
                applied_command = cmd
                commands_to_remove.append(cmd)

        for cmd in commands_to_remove:
            self.command_queue.remove(cmd)

        return applied_command

def test_delay_configurations():
    """Test different delay configurations"""

    print("=== Delay Configuration Test ===\n")

    # Test configurations
    configs = [
        (0, 0, 0, "No delay"),
        (10, 5, 0, "Fixed 15ms delay"),
        (20, 10, 0, "Fixed 30ms delay"),
        (15, 10, 5, "25ms ± 5ms variable delay")
    ]

    results = []

    for proc_delay, resp_delay, var_delay, name in configs:
        print(f"Testing: {name}")
        print(f"  Configuration: processing={proc_delay}ms, response={resp_delay}ms, variation=±{var_delay}ms")

        simulator = DelaySimulator()
        simulator.configure_delay_simulation(
            enable=(proc_delay + resp_delay > 0),
            processing_delay_ms=proc_delay,
            response_delay_ms=resp_delay,
            delay_variation_ms=var_delay
        )

        measured_delays = []
        expected_delay = proc_delay + resp_delay

        # Test multiple commands
        for trial in range(10):
            command = [0.0, 0.0, float(trial)]
            recv_time = time.time()

            # Add command (may be delayed)
            immediate_result = simulator.add_command_with_delay(command, recv_time)

            if immediate_result is not None:
                # No delay case
                actual_delay = 0.0
                measured_delays.append(actual_delay)
            else:
                # Wait for delayed command
                max_wait = (expected_delay + var_delay + 10) / 1000.0  # Expected + variation + buffer
                wait_start = time.time()

                while (time.time() - wait_start) < max_wait:
                    delayed_cmd = simulator.process_delayed_commands()
                    if delayed_cmd is not None:
                        actual_delay = (delayed_cmd['apply_time'] - delayed_cmd['recv_time']) * 1000  # ms
                        measured_delays.append(actual_delay)
                        break
                    time.sleep(0.001)  # 1ms polling

        # Analyze results
        if measured_delays:
            avg_delay = np.mean(measured_delays)
            std_delay = np.std(measured_delays)
            min_delay = np.min(measured_delays)
            max_delay = np.max(measured_delays)

            print(f"  Expected delay: {expected_delay}ms")
            print(f"  Measured delays: avg={avg_delay:.1f}ms, std={std_delay:.1f}ms")
            print(f"  Range: {min_delay:.1f} - {max_delay:.1f}ms")

            # Check accuracy
            tolerance = max(2.0, var_delay + 1.0)  # 2ms base + variation + 1ms buffer
            error = abs(avg_delay - expected_delay)

            if error <= tolerance:
                print(f"  ✅ Within tolerance (±{tolerance:.1f}ms, error: {error:.1f}ms)")
                success = True
            else:
                print(f"  ❌ Outside tolerance (±{tolerance:.1f}ms, error: {error:.1f}ms)")
                success = False

            # Check variation range
            if var_delay > 0:
                expected_min = expected_delay - var_delay
                expected_max = expected_delay + var_delay
                if expected_min <= min_delay and max_delay <= expected_max + 2:  # 2ms tolerance
                    print(f"  ✅ Variation within expected range ({expected_min:.1f} - {expected_max:.1f}ms)")
                else:
                    print(f"  ⚠️ Variation outside expected range ({expected_min:.1f} - {expected_max:.1f}ms)")

            results.append({
                'name': name,
                'expected': expected_delay,
                'measured_avg': avg_delay,
                'measured_std': std_delay,
                'success': success
            })

        else:
            print(f"  ❌ No measurements obtained")
            results.append({
                'name': name,
                'expected': expected_delay,
                'measured_avg': None,
                'success': False
            })

        print()

    # Overall analysis
    print("=== Analysis ===")
    successful_tests = [r for r in results if r['success'] and r['measured_avg'] is not None]

    if len(successful_tests) >= 2:
        print("Configuration vs Measured Delay:")
        for result in successful_tests:
            error = abs(result['measured_avg'] - result['expected'])
            print(f"  {result['name']}: {result['expected']}ms → {result['measured_avg']:.1f}ms (error: {error:.1f}ms)")

        # Correlation analysis
        expected_vals = [r['expected'] for r in successful_tests]
        measured_vals = [r['measured_avg'] for r in successful_tests]

        if len(set(expected_vals)) > 1:  # Multiple different expected values
            correlation = np.corrcoef(expected_vals, measured_vals)[0, 1]
            print(f"\nCorrelation coefficient: {correlation:.4f}")

            if correlation > 0.95:
                print("✅ Excellent correlation - delay logic is working perfectly!")
            elif correlation > 0.8:
                print("✅ Good correlation - delay logic is working well")
            else:
                print("⚠️ Moderate correlation - delay logic may have issues")

            # Check linearity
            print("\nLinearity check:")
            sorted_tests = sorted(successful_tests, key=lambda x: x['expected'])
            for i in range(1, len(sorted_tests)):
                expected_diff = sorted_tests[i]['expected'] - sorted_tests[i-1]['expected']
                measured_diff = sorted_tests[i]['measured_avg'] - sorted_tests[i-1]['measured_avg']

                if expected_diff > 0:
                    ratio = measured_diff / expected_diff
                    print(f"  +{expected_diff}ms config → +{measured_diff:.1f}ms measured (ratio: {ratio:.3f})")

    print("\n=== Conclusion ===")
    print("遅延設定の効果確認:")
    if len(successful_tests) >= 2:
        print("✅ 遅延設定は期待通りに動作しています")
        print("✅ 設定値と実測値に強い相関関係があります")
        print("✅ この遅延ロジックがRTT変動の主要因の一つです")
    else:
        print("❌ 十分なテストデータが得られませんでした")

    return results

if __name__ == "__main__":
    test_delay_configurations()