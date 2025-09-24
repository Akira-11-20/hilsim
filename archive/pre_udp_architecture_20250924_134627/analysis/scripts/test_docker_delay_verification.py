#!/usr/bin/env python3
"""
Docker-based Communication Delay Verification

This script tests actual communication delays between Plant and Numeric Docker containers
with different delay configurations. It bypasses PID control and focuses on RTT measurement.
"""

import subprocess
import time
import json
import yaml
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import logging
from typing import Dict, List
import tempfile
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DockerDelayTester:
    """Test communication delays using actual Plant and Numeric Docker containers"""

    def __init__(self, docker_compose_path: str = "docker/compose.yaml"):
        self.docker_compose_path = docker_compose_path
        self.base_plant_config = None
        self.base_numeric_config = None
        self.test_results = []

        # Load original configs
        self._load_base_configs()

    def _load_base_configs(self):
        """Load the original configuration files"""
        plant_config_path = "plant/app/config.yaml"

        if os.path.exists(plant_config_path):
            with open(plant_config_path, 'r') as f:
                self.base_plant_config = yaml.safe_load(f)
        else:
            # Default config if file doesn't exist
            self.base_plant_config = {
                'plant': {
                    'bind_address': 'tcp://0.0.0.0:5555',
                    'dt': 0.02,
                    'max_steps': 1000,
                    'log_file': '/app/logs/plant_log.csv'
                },
                'communication': {
                    'processing_delay': 5.0,
                    'response_delay': 20.0,
                    'delay_variation': 3.0,
                    'enable_delay': True
                },
                'simulation': {
                    'mass': 1.0,
                    'gravity': 9.81,
                    'initial_position': 0.0,
                    'initial_velocity': 0.0
                }
            }

    def _create_test_config(self, delay_config: Dict) -> str:
        """Create a test configuration file with specified delay settings"""

        # Create modified config
        test_config = self.base_plant_config.copy()
        test_config['communication'].update(delay_config)

        # Reduce simulation time for testing
        test_config['plant']['max_steps'] = 1000  # ~20 seconds at 50Hz

        # Create temporary config file
        config_content = yaml.dump(test_config, default_flow_style=False)

        return config_content

    def _run_docker_test(self, delay_config: Dict, test_name: str, duration: int = 25) -> Dict:
        """Run a Docker test with specified delay configuration"""

        logger.info(f"Running Docker test: {test_name}")
        logger.info(f"Delay config: {delay_config}")

        # Create test configuration
        test_config_content = self._create_test_config(delay_config)

        # Backup original config
        plant_config_path = "plant/app/config.yaml"
        backup_path = f"{plant_config_path}.backup"

        if os.path.exists(plant_config_path):
            shutil.copy2(plant_config_path, backup_path)

        try:
            # Write test configuration
            with open(plant_config_path, 'w') as f:
                f.write(test_config_content)

            # Generate unique run ID
            run_id = f"delay_test_{test_name}_{int(time.time())}"

            # Set environment variables
            env = os.environ.copy()
            env['RUN_ID'] = run_id
            env['STEP_DT'] = '0.02'  # 50Hz
            env['MAX_STEPS'] = '1000'

            logger.info(f"Starting Docker containers with RUN_ID: {run_id}")

            # Start containers
            start_cmd = [
                'docker', 'compose', '-f', self.docker_compose_path, 'up', '--build'
            ]

            start_time = time.time()
            result = subprocess.run(start_cmd, env=env, capture_output=True, text=True, timeout=duration+30)
            end_time = time.time()

            if result.returncode != 0:
                logger.error(f"Docker execution failed: {result.stderr}")
                return None

            # Parse logs for RTT measurements
            log_dir = f"logs/{run_id}"
            rtt_data = self._extract_rtt_from_logs(log_dir)

            # Calculate statistics
            if rtt_data:
                stats = {
                    'test_name': test_name,
                    'run_id': run_id,
                    'config': delay_config.copy(),
                    'duration_seconds': end_time - start_time,
                    'sample_count': len(rtt_data),
                    'rtt_avg_ms': np.mean(rtt_data),
                    'rtt_std_ms': np.std(rtt_data),
                    'rtt_min_ms': np.min(rtt_data),
                    'rtt_max_ms': np.max(rtt_data),
                    'rtt_median_ms': np.median(rtt_data),
                    'rtt_data': rtt_data[:100]  # Store first 100 samples
                }

                logger.info(f"Test completed: RTT={stats['rtt_avg_ms']:.1f}±{stats['rtt_std_ms']:.1f}ms, "
                           f"Samples={stats['sample_count']}")

                return stats
            else:
                logger.error("No RTT data found in logs")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"Docker test timed out after {duration+30} seconds")
            # Force stop containers
            subprocess.run(['docker', 'compose', '-f', self.docker_compose_path, 'down', '-t', '5'])
            return None

        except Exception as e:
            logger.error(f"Test failed: {e}")
            return None

        finally:
            # Stop containers
            subprocess.run(['docker', 'compose', '-f', self.docker_compose_path, 'down', '-t', '5'],
                          capture_output=True)

            # Restore original config
            if os.path.exists(backup_path):
                shutil.move(backup_path, plant_config_path)

            # Small delay between tests
            time.sleep(2)

    def _extract_rtt_from_logs(self, log_dir: str) -> List[float]:
        """Extract RTT measurements from log files"""

        rtt_data = []

        # Try to read numeric log file
        numeric_log_path = f"{log_dir}/numeric_log.csv"

        if os.path.exists(numeric_log_path):
            try:
                df = pd.read_csv(numeric_log_path)
                if 'rtt_ms' in df.columns:
                    # Filter out invalid RTT values
                    valid_rtts = df['rtt_ms'].dropna()
                    valid_rtts = valid_rtts[valid_rtts > 0]  # Remove non-positive values
                    valid_rtts = valid_rtts[valid_rtts < 10000]  # Remove extremely high values
                    rtt_data = valid_rtts.tolist()
                    logger.info(f"Extracted {len(rtt_data)} RTT measurements from numeric log")
                else:
                    logger.warning("No rtt_ms column found in numeric log")
            except Exception as e:
                logger.error(f"Failed to read numeric log: {e}")

        # Try alternative: parse from container logs if CSV unavailable
        if not rtt_data:
            try:
                # Get container logs
                logs_cmd = ['docker', 'compose', '-f', self.docker_compose_path, 'logs', 'numeric']
                result = subprocess.run(logs_cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    # Parse RTT from log lines
                    for line in result.stdout.split('\n'):
                        if 'RTT:' in line:
                            try:
                                # Extract RTT value from log line
                                rtt_part = line.split('RTT:')[1].split('ms')[0].strip()
                                rtt_value = float(rtt_part)
                                if 0 < rtt_value < 10000:
                                    rtt_data.append(rtt_value)
                            except (ValueError, IndexError):
                                continue

                    logger.info(f"Extracted {len(rtt_data)} RTT measurements from container logs")

            except Exception as e:
                logger.error(f"Failed to extract RTT from container logs: {e}")

        return rtt_data

    def run_delay_verification_suite(self) -> pd.DataFrame:
        """Run comprehensive delay verification test suite"""

        logger.info("Starting Docker-based delay verification suite...")

        # Define test configurations
        test_configs = [
            {
                'name': 'No_Delay',
                'processing_delay': 0.0,
                'response_delay': 0.0,
                'delay_variation': 0.0,
                'enable_delay': False
            },
            {
                'name': 'Light_Delay',
                'processing_delay': 5.0,
                'response_delay': 3.0,
                'delay_variation': 2.0,
                'enable_delay': True
            },
            {
                'name': 'Medium_Delay',
                'processing_delay': 10.0,
                'response_delay': 5.0,
                'delay_variation': 3.0,
                'enable_delay': True
            },
            {
                'name': 'High_Delay',
                'processing_delay': 20.0,
                'response_delay': 10.0,
                'delay_variation': 5.0,
                'enable_delay': True
            },
            {
                'name': 'Very_High_Delay',
                'processing_delay': 50.0,
                'response_delay': 20.0,
                'delay_variation': 10.0,
                'enable_delay': True
            }
        ]

        results = []

        for config in test_configs:
            test_name = config.pop('name')
            result = self._run_docker_test(config, test_name)

            if result:
                # Add configured delay info
                result['total_config_delay_ms'] = config['processing_delay'] + config['response_delay']
                result['config_delay_enabled'] = config['enable_delay']
                results.append(result)
            else:
                logger.error(f"Test {test_name} failed")

        if results:
            results_df = pd.DataFrame(results)
            self.test_results = results
            return results_df
        else:
            logger.error("All tests failed")
            return pd.DataFrame()

    def create_analysis_report(self, results_df: pd.DataFrame, output_prefix: str = "docker_delay_verification"):
        """Create comprehensive analysis report"""

        if results_df.empty:
            logger.error("No results to analyze")
            return

        # Save raw results
        csv_filename = f"{output_prefix}_results.csv"
        results_df.to_csv(csv_filename, index=False)
        logger.info(f"Results saved to {csv_filename}")

        # Create visualization
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Docker Container Communication Delay Verification', fontsize=16)

        # 1. Configured vs Measured RTT
        config_delays = results_df['total_config_delay_ms']
        measured_rtts = results_df['rtt_avg_ms']
        measured_stds = results_df['rtt_std_ms']

        ax1.errorbar(config_delays, measured_rtts, yerr=measured_stds,
                    fmt='o', capsize=5, markersize=8, alpha=0.8, color='blue')

        # Add labels for each point
        for i, (x, y, name) in enumerate(zip(config_delays, measured_rtts, results_df['test_name'])):
            ax1.annotate(name, (x, y), xytext=(5, 5), textcoords='offset points', fontsize=9)

        # Calculate and show ideal line
        if len(config_delays) > 1:
            # Estimate Docker overhead
            docker_overhead = np.mean(measured_rtts - config_delays)
            max_delay = max(config_delays)
            ideal_x = np.linspace(0, max_delay, 100)
            ideal_y = ideal_x + docker_overhead
            ax1.plot(ideal_x, ideal_y, 'r--', alpha=0.7,
                    label=f'Ideal (config + {docker_overhead:.1f}ms Docker overhead)')

            # Add correlation
            correlation = np.corrcoef(config_delays, measured_rtts)[0, 1]
            ax1.text(0.05, 0.95, f'Correlation: {correlation:.4f}',
                    transform=ax1.transAxes, bbox=dict(boxstyle="round", facecolor='wheat'))

        ax1.set_xlabel('Configured Delay (ms)')
        ax1.set_ylabel('Measured RTT (ms)')
        ax1.set_title('Docker: Configured vs Measured Delay')
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # 2. Docker Overhead Analysis
        overheads = measured_rtts - config_delays
        test_names = results_df['test_name']

        bars = ax2.bar(range(len(test_names)), overheads, alpha=0.7, color='lightcoral')
        ax2.set_xlabel('Test Configuration')
        ax2.set_ylabel('Docker Overhead (ms)')
        ax2.set_title('Docker Communication Overhead')
        ax2.set_xticks(range(len(test_names)))
        ax2.set_xticklabels(test_names, rotation=45)
        ax2.grid(True, alpha=0.3)

        # Add average line
        avg_overhead = np.mean(overheads)
        ax2.axhline(y=avg_overhead, color='red', linestyle='--', alpha=0.7,
                   label=f'Average: {avg_overhead:.1f}ms')
        ax2.legend()

        # 3. RTT Range Comparison
        rtts_min = results_df['rtt_min_ms']
        rtts_max = results_df['rtt_max_ms']

        x_pos = range(len(test_names))
        ax3.errorbar(x_pos, measured_rtts,
                    yerr=[measured_rtts - rtts_min, rtts_max - measured_rtts],
                    fmt='o', capsize=5, markersize=8, alpha=0.8, color='green')

        ax3.set_xlabel('Test Configuration')
        ax3.set_ylabel('RTT (ms)')
        ax3.set_title('RTT Range in Docker Environment')
        ax3.set_xticks(x_pos)
        ax3.set_xticklabels(test_names, rotation=45)
        ax3.grid(True, alpha=0.3)

        # 4. Sample Count and Quality
        sample_counts = results_df['sample_count']

        bars = ax4.bar(range(len(test_names)), sample_counts, alpha=0.7, color='gold')
        ax4.set_xlabel('Test Configuration')
        ax4.set_ylabel('Number of RTT Samples')
        ax4.set_title('Data Quality (Sample Count)')
        ax4.set_xticks(range(len(test_names)))
        ax4.set_xticklabels(test_names, rotation=45)
        ax4.grid(True, alpha=0.3)

        # Add value labels on bars
        for i, (bar, count) in enumerate(zip(bars, sample_counts)):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(sample_counts)*0.01,
                    f'{int(count)}', ha='center', va='bottom', fontsize=9)

        plt.tight_layout()

        # Save plot
        plot_filename = f"{output_prefix}_analysis.png"
        plt.savefig(plot_filename, dpi=150, bbox_inches='tight')
        logger.info(f"Analysis plot saved to {plot_filename}")

        # Print summary
        self._print_docker_summary(results_df)

    def _print_docker_summary(self, results_df: pd.DataFrame):
        """Print comprehensive summary of Docker test results"""

        print("\n" + "="*80)
        print("DOCKER CONTAINER DELAY VERIFICATION SUMMARY")
        print("="*80)

        for _, row in results_df.iterrows():
            print(f"\n{row['test_name']}:")
            print(f"  Configured Delay: {row['config']['processing_delay']}ms + {row['config']['response_delay']}ms ± {row['config']['delay_variation']}ms")
            print(f"  Delay Enabled: {row['config']['enable_delay']}")
            print(f"  Measured RTT: {row['rtt_avg_ms']:.1f} ± {row['rtt_std_ms']:.1f}ms")
            print(f"  Range: {row['rtt_min_ms']:.1f} - {row['rtt_max_ms']:.1f}ms")
            print(f"  Docker Overhead: {row['rtt_avg_ms'] - row['total_config_delay_ms']:.1f}ms")
            print(f"  Samples: {row['sample_count']}")
            print(f"  Test Duration: {row['duration_seconds']:.1f}s")

        if len(results_df) > 1:
            # Overall analysis
            overheads = results_df['rtt_avg_ms'] - results_df['total_config_delay_ms']
            avg_overhead = np.mean(overheads)
            std_overhead = np.std(overheads)

            correlation = np.corrcoef(results_df['total_config_delay_ms'],
                                     results_df['rtt_avg_ms'])[0, 1]

            print(f"\nDocker Environment Analysis:")
            print(f"  Average Docker Overhead: {avg_overhead:.1f} ± {std_overhead:.1f}ms")
            print(f"  Config-Measurement Correlation: {correlation:.4f}")
            print(f"  Total Samples Collected: {results_df['sample_count'].sum()}")

            if correlation > 0.95:
                print("  ✅ Excellent correlation - Docker delay implementation works perfectly")
            elif correlation > 0.8:
                print("  ✅ Good correlation - Docker delay implementation works well")
            else:
                print("  ⚠️ Poor correlation - Docker environment may affect delay implementation")


def main():
    """Main execution function"""

    logger.info("Starting Docker-based communication delay verification...")

    # Check if Docker is available
    try:
        subprocess.run(['docker', '--version'], check=True, capture_output=True)
        subprocess.run(['docker', 'compose', '--version'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Docker or Docker Compose not available")
        return

    # Initialize tester
    tester = DockerDelayTester()

    # Run test suite
    results_df = tester.run_delay_verification_suite()

    if not results_df.empty:
        # Generate analysis report
        tester.create_analysis_report(results_df)
        logger.info("Docker delay verification completed successfully!")
    else:
        logger.error("Docker delay verification failed - no results obtained")


if __name__ == "__main__":
    main()