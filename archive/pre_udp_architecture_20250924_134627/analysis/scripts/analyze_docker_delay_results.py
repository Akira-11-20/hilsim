#!/usr/bin/env python3
"""
Analyze Docker Delay Test Results

Extract and analyze RTT measurements from actual Docker test logs
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def extract_rtt_from_log(log_dir: str) -> dict:
    """Extract RTT data from a specific test log directory"""

    log_path = f"{log_dir}/realtime_numeric_log.csv"

    if not os.path.exists(log_path):
        logger.warning(f"Log file not found: {log_path}")
        return None

    try:
        df = pd.read_csv(log_path)

        # Filter valid RTT measurements
        valid_data = df[df['communication_status'] == 'OK'].copy()

        if len(valid_data) == 0:
            logger.warning(f"No valid RTT data in {log_dir}")
            return None

        rtt_values = valid_data['rtt_ms'].dropna()
        rtt_values = rtt_values[rtt_values > 0]  # Remove non-positive
        rtt_values = rtt_values[rtt_values < 10000]  # Remove extreme outliers

        if len(rtt_values) == 0:
            logger.warning(f"No usable RTT data in {log_dir}")
            return None

        result = {
            'log_dir': log_dir,
            'test_name': os.path.basename(log_dir).replace('delay_test_', '').split('_')[0] + '_' + os.path.basename(log_dir).replace('delay_test_', '').split('_')[1],
            'sample_count': len(rtt_values),
            'rtt_avg_ms': np.mean(rtt_values),
            'rtt_std_ms': np.std(rtt_values),
            'rtt_min_ms': np.min(rtt_values),
            'rtt_max_ms': np.max(rtt_values),
            'rtt_median_ms': np.median(rtt_values),
            'rtt_values': rtt_values.tolist()
        }

        logger.info(f"Extracted {len(rtt_values)} RTT samples from {log_dir}")
        return result

    except Exception as e:
        logger.error(f"Failed to process {log_path}: {e}")
        return None


def analyze_all_docker_tests():
    """Analyze all Docker delay test results"""

    logs_dir = "logs"
    test_dirs = [d for d in os.listdir(logs_dir) if d.startswith('delay_test_')]

    if not test_dirs:
        logger.error("No delay test directories found")
        return

    logger.info(f"Found {len(test_dirs)} test directories")

    # Define delay configurations for each test
    delay_configs = {
        'No_Delay': {'processing': 0, 'response': 0, 'variation': 0, 'total': 0},
        'Light_Delay': {'processing': 5, 'response': 3, 'variation': 2, 'total': 8},
        'Medium_Delay': {'processing': 10, 'response': 5, 'variation': 3, 'total': 15},
        'High_Delay': {'processing': 20, 'response': 10, 'variation': 5, 'total': 30},
        'Very_High_Delay': {'processing': 50, 'response': 20, 'variation': 10, 'total': 70},
    }

    results = []

    for test_dir in sorted(test_dirs):
        full_path = f"{logs_dir}/{test_dir}"
        result = extract_rtt_from_log(full_path)

        if result:
            # Extract test type from directory name
            test_type = None
            for config_name in delay_configs.keys():
                if config_name in test_dir:
                    test_type = config_name
                    break

            if test_type:
                result.update(delay_configs[test_type])
                result['test_type'] = test_type
                results.append(result)
            else:
                logger.warning(f"Could not identify test type for {test_dir}")

    if not results:
        logger.error("No valid results found")
        return

    # Create DataFrame
    df = pd.DataFrame(results)

    # Save results to proper directory
    output_dir = 'analysis/docker_tests'
    os.makedirs(output_dir, exist_ok=True)

    csv_path = f'{output_dir}/docker_delay_verification_results.csv'
    df.to_csv(csv_path, index=False)
    logger.info(f"Results saved to {csv_path}")

    # Create visualization
    create_docker_analysis_plot(df)

    # Print summary
    print_docker_summary(df)

    return df


def create_docker_analysis_plot(df):
    """Create comprehensive analysis plot"""

    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Docker Container Communication Delay Verification Results', fontsize=16)

    # 1. Configured vs Measured RTT
    config_delays = df['total']
    measured_rtts = df['rtt_avg_ms']
    measured_stds = df['rtt_std_ms']
    test_names = df['test_type']

    ax1.errorbar(config_delays, measured_rtts, yerr=measured_stds,
                fmt='o', capsize=5, markersize=10, alpha=0.8, color='blue')

    # Add labels
    for x, y, name in zip(config_delays, measured_rtts, test_names):
        ax1.annotate(name.replace('_', ' '), (x, y), xytext=(5, 5),
                    textcoords='offset points', fontsize=9)

    # Calculate correlation and Docker overhead
    if len(config_delays) > 1:
        correlation = np.corrcoef(config_delays, measured_rtts)[0, 1]
        docker_overhead = np.mean(measured_rtts - config_delays)

        # Ideal line
        max_delay = max(config_delays)
        ideal_x = np.linspace(0, max_delay * 1.1, 100)
        ideal_y = ideal_x + docker_overhead
        ax1.plot(ideal_x, ideal_y, 'r--', alpha=0.7,
                label=f'Ideal (config + {docker_overhead:.1f}ms)')

        ax1.text(0.05, 0.95, f'Correlation: {correlation:.4f}',
                transform=ax1.transAxes, bbox=dict(boxstyle="round", facecolor='wheat'))

    ax1.set_xlabel('Configured Delay (ms)')
    ax1.set_ylabel('Measured RTT (ms)')
    ax1.set_title('Docker: Configured vs Measured Delay')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # 2. Docker Overhead by Configuration
    overheads = measured_rtts - config_delays
    x_pos = range(len(test_names))

    bars = ax2.bar(x_pos, overheads, alpha=0.7, color='lightcoral')
    ax2.set_xlabel('Configuration')
    ax2.set_ylabel('Docker Overhead (ms)')
    ax2.set_title('Docker Communication Overhead')
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels([name.replace('_', ' ') for name in test_names], rotation=45)
    ax2.grid(True, alpha=0.3)

    # Average line
    avg_overhead = np.mean(overheads)
    ax2.axhline(y=avg_overhead, color='red', linestyle='--', alpha=0.7,
               label=f'Avg: {avg_overhead:.1f}ms')
    ax2.legend()

    # 3. RTT Distribution (Box plot style)
    rtts_min = df['rtt_min_ms']
    rtts_max = df['rtt_max_ms']

    ax3.errorbar(x_pos, measured_rtts,
                yerr=[measured_rtts - rtts_min, rtts_max - measured_rtts],
                fmt='o', capsize=5, markersize=10, alpha=0.8, color='green')

    ax3.set_xlabel('Configuration')
    ax3.set_ylabel('RTT (ms)')
    ax3.set_title('RTT Range in Docker Environment')
    ax3.set_xticks(x_pos)
    ax3.set_xticklabels([name.replace('_', ' ') for name in test_names], rotation=45)
    ax3.grid(True, alpha=0.3)

    # 4. Implementation Accuracy
    expected_rtts = config_delays + avg_overhead
    accuracy_errors = measured_rtts - expected_rtts

    colors = ['green' if abs(x) < 10 else 'orange' if abs(x) < 20 else 'red' for x in accuracy_errors]
    bars = ax4.bar(x_pos, accuracy_errors, alpha=0.7, color=colors)

    ax4.set_xlabel('Configuration')
    ax4.set_ylabel('Error (Measured - Expected) ms')
    ax4.set_title('Delay Implementation Accuracy')
    ax4.set_xticks(x_pos)
    ax4.set_xticklabels([name.replace('_', ' ') for name in test_names], rotation=45)
    ax4.grid(True, alpha=0.3)
    ax4.axhline(y=0, color='black', linestyle='-', alpha=0.3)

    # Add value labels
    for bar, error in zip(bars, accuracy_errors):
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2, height + (1 if height >= 0 else -3),
                f'{error:.1f}', ha='center', va='bottom' if height >= 0 else 'top', fontsize=9)

    plt.tight_layout()

    # Save to proper directory
    output_dir = 'analysis/docker_tests'
    os.makedirs(output_dir, exist_ok=True)

    plot_path = f'{output_dir}/docker_delay_verification_analysis.png'
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    logger.info(f"Analysis plot saved to {plot_path}")


def print_docker_summary(df):
    """Print comprehensive summary"""

    print("\n" + "="*80)
    print("DOCKER CONTAINER DELAY VERIFICATION RESULTS")
    print("="*80)

    for _, row in df.iterrows():
        print(f"\n{row['test_type'].replace('_', ' ')}:")
        print(f"  Configured: {row['processing']}ms + {row['response']}ms ± {row['variation']}ms (Total: {row['total']}ms)")
        print(f"  Measured RTT: {row['rtt_avg_ms']:.1f} ± {row['rtt_std_ms']:.1f}ms")
        print(f"  Range: {row['rtt_min_ms']:.1f} - {row['rtt_max_ms']:.1f}ms")
        print(f"  Docker Overhead: {row['rtt_avg_ms'] - row['total']:.1f}ms")
        print(f"  Sample Count: {row['sample_count']}")

    # Overall analysis
    if len(df) > 1:
        config_delays = df['total']
        measured_rtts = df['rtt_avg_ms']
        overheads = measured_rtts - config_delays

        correlation = np.corrcoef(config_delays, measured_rtts)[0, 1]
        avg_overhead = np.mean(overheads)
        std_overhead = np.std(overheads)

        print(f"\nOverall Analysis:")
        print(f"  Average Docker Overhead: {avg_overhead:.1f} ± {std_overhead:.1f}ms")
        print(f"  Config-Measurement Correlation: {correlation:.4f}")
        print(f"  Total RTT Samples: {df['sample_count'].sum()}")

        if correlation > 0.95:
            print("  ✅ Excellent correlation - Docker delay implementation is highly accurate")
        elif correlation > 0.8:
            print("  ✅ Good correlation - Docker delay implementation works well")
        elif correlation > 0.5:
            print("  ⚠️ Moderate correlation - Docker environment affects delay implementation")
        else:
            print("  ❌ Poor correlation - Significant issues with delay implementation")

        # Compare with localhost results (if available)
        print(f"\nDocker vs Localhost Comparison:")
        print(f"  Docker Overhead: {avg_overhead:.1f}ms")
        print(f"  Localhost Overhead (from previous test): ~1.3ms")
        print(f"  Additional Docker Network Cost: {avg_overhead - 1.3:.1f}ms")


if __name__ == "__main__":
    analyze_all_docker_tests()