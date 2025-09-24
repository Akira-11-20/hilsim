#!/usr/bin/env python3
"""
Create comprehensive graphs from RTT measurement CSV data
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from datetime import datetime
import os
import glob

# Set style for better looking plots
plt.style.use('seaborn-v0_8')
sns.set_palette("husl")

def find_csv_files():
    """Find all RTT CSV files in results directory"""
    csv_pattern = "results/rtt_detailed_*.csv"
    csv_files = glob.glob(csv_pattern)

    if not csv_files:
        print("No RTT CSV files found. Run generate_csv_results.py first.")
        return []

    print(f"Found {len(csv_files)} CSV files:")
    for f in csv_files:
        print(f"  {f}")

    return csv_files

def load_and_prepare_data(csv_files):
    """Load all CSV files and prepare combined dataset"""

    all_data = []

    for csv_file in csv_files:
        print(f"Loading: {csv_file}")
        df = pd.read_csv(csv_file)
        all_data.append(df)

    # Combine all datasets
    combined_df = pd.concat(all_data, ignore_index=True)

    # Add relative timestamp for time series analysis
    for config in combined_df['test_config'].unique():
        mask = combined_df['test_config'] == config
        config_data = combined_df[mask].copy()
        start_time = config_data['timestamp'].min()
        combined_df.loc[mask, 'relative_time_sec'] = config_data['timestamp'] - start_time

    print(f"Combined dataset: {len(combined_df)} measurements across {len(combined_df['test_config'].unique())} configurations")

    return combined_df

def create_rtt_comparison_plot(df):
    """Create RTT comparison box plot and histogram"""

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle('RTT Measurement Analysis', fontsize=16, fontweight='bold')

    # 1. Box plot comparison
    ax1 = axes[0, 0]
    df.boxplot(column='client_rtt_ms', by='test_config', ax=ax1)
    ax1.set_title('RTT Distribution by Configuration')
    ax1.set_xlabel('Configuration')
    ax1.set_ylabel('RTT (ms)')
    ax1.tick_params(axis='x', rotation=45)

    # 2. Histogram overlay
    ax2 = axes[0, 1]
    for config in df['test_config'].unique():
        config_data = df[df['test_config'] == config]['client_rtt_ms']
        ax2.hist(config_data, alpha=0.7, label=config, bins=30, density=True)
    ax2.set_title('RTT Distribution Histograms')
    ax2.set_xlabel('RTT (ms)')
    ax2.set_ylabel('Density')
    ax2.legend()

    # 3. Time series plot
    ax3 = axes[1, 0]
    for config in df['test_config'].unique():
        config_data = df[df['test_config'] == config]
        ax3.plot(config_data['sequence'], config_data['client_rtt_ms'],
                label=config, alpha=0.8, linewidth=1)
    ax3.set_title('RTT Time Series')
    ax3.set_xlabel('Sequence Number')
    ax3.set_ylabel('RTT (ms)')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 4. RTT vs Server Delay scatter
    ax4 = axes[1, 1]
    for config in df['test_config'].unique():
        config_data = df[df['test_config'] == config]
        ax4.scatter(config_data['server_applied_delay_ms'], config_data['client_rtt_ms'],
                   label=config, alpha=0.6, s=20)
    ax4.set_title('Client RTT vs Server Applied Delay')
    ax4.set_xlabel('Server Applied Delay (ms)')
    ax4.set_ylabel('Client RTT (ms)')
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    # Add ideal line (y=x) if there's delay data
    max_delay = df['server_applied_delay_ms'].max()
    if max_delay > 0:
        ax4.plot([0, max_delay], [0, max_delay], 'r--', alpha=0.5, label='Ideal (RTT=Delay)')

    plt.tight_layout()

    # Save plot
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"results/rtt_analysis_{timestamp}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"Saved: {filename}")

    return filename

def create_detailed_statistics_plot(df):
    """Create detailed statistical analysis plots"""

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle('Detailed RTT Statistics Analysis', fontsize=16, fontweight='bold')

    # Calculate statistics for each configuration
    stats_data = []
    for config in df['test_config'].unique():
        config_data = df[df['test_config'] == config]['client_rtt_ms']
        stats_data.append({
            'config': config,
            'mean': config_data.mean(),
            'std': config_data.std(),
            'min': config_data.min(),
            'max': config_data.max(),
            'p95': config_data.quantile(0.95),
            'p99': config_data.quantile(0.99),
            'samples': len(config_data)
        })

    stats_df = pd.DataFrame(stats_data)

    # 1. Mean ± Std comparison
    ax1 = axes[0, 0]
    x_pos = np.arange(len(stats_df))
    ax1.bar(x_pos, stats_df['mean'], yerr=stats_df['std'],
           capsize=5, alpha=0.7, color='skyblue')
    ax1.set_title('Mean RTT ± Standard Deviation')
    ax1.set_xlabel('Configuration')
    ax1.set_ylabel('RTT (ms)')
    ax1.set_xticks(x_pos)
    ax1.set_xticklabels(stats_df['config'], rotation=45)
    ax1.grid(True, alpha=0.3)

    # 2. Min/Max range
    ax2 = axes[0, 1]
    ax2.bar(x_pos, stats_df['max'] - stats_df['min'],
           bottom=stats_df['min'], alpha=0.7, color='lightcoral')
    ax2.set_title('RTT Range (Min to Max)')
    ax2.set_xlabel('Configuration')
    ax2.set_ylabel('RTT (ms)')
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(stats_df['config'], rotation=45)
    ax2.grid(True, alpha=0.3)

    # 3. Percentiles comparison
    ax3 = axes[0, 2]
    width = 0.35
    ax3.bar(x_pos - width/2, stats_df['p95'], width, label='P95', alpha=0.7)
    ax3.bar(x_pos + width/2, stats_df['p99'], width, label='P99', alpha=0.7)
    ax3.set_title('RTT Percentiles (P95, P99)')
    ax3.set_xlabel('Configuration')
    ax3.set_ylabel('RTT (ms)')
    ax3.set_xticks(x_pos)
    ax3.set_xticklabels(stats_df['config'], rotation=45)
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 4. Network overhead analysis
    ax4 = axes[1, 0]
    if 'estimated_network_overhead_ms' in df.columns:
        for config in df['test_config'].unique():
            config_data = df[df['test_config'] == config]['estimated_network_overhead_ms']
            ax4.hist(config_data, alpha=0.7, label=config, bins=20, density=True)
        ax4.set_title('Network Overhead Distribution')
        ax4.set_xlabel('Network Overhead (ms)')
        ax4.set_ylabel('Density')
        ax4.legend()
        ax4.grid(True, alpha=0.3)

    # 5. Jitter analysis (if available)
    ax5 = axes[1, 1]
    jitter_configs = df[df['server_jitter_ms'].abs() > 0]['test_config'].unique()
    if len(jitter_configs) > 0:
        for config in jitter_configs:
            config_data = df[df['test_config'] == config]['server_jitter_ms']
            ax5.hist(config_data, alpha=0.7, label=config, bins=20, density=True)
        ax5.set_title('Applied Jitter Distribution')
        ax5.set_xlabel('Jitter (ms)')
        ax5.set_ylabel('Density')
        ax5.legend()
    else:
        ax5.text(0.5, 0.5, 'No Jitter Data Available',
                ha='center', va='center', transform=ax5.transAxes, fontsize=12)
        ax5.set_title('Applied Jitter Distribution')
    ax5.grid(True, alpha=0.3)

    # 6. Rolling statistics
    ax6 = axes[1, 2]
    for config in df['test_config'].unique():
        config_data = df[df['test_config'] == config].sort_values('sequence')
        rolling_mean = config_data['client_rtt_ms'].rolling(window=20, center=True).mean()
        rolling_std = config_data['client_rtt_ms'].rolling(window=20, center=True).std()

        ax6.plot(config_data['sequence'], rolling_mean, label=f'{config} (mean)', linewidth=2)
        ax6.fill_between(config_data['sequence'],
                        rolling_mean - rolling_std,
                        rolling_mean + rolling_std,
                        alpha=0.2)

    ax6.set_title('Rolling Statistics (20-sample window)')
    ax6.set_xlabel('Sequence Number')
    ax6.set_ylabel('RTT (ms)')
    ax6.legend()
    ax6.grid(True, alpha=0.3)

    plt.tight_layout()

    # Save plot
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"results/rtt_statistics_{timestamp}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"Saved: {filename}")

    return filename

def create_performance_summary_table(df):
    """Create and save performance summary table"""

    summary_data = []

    for config in df['test_config'].unique():
        config_data = df[df['test_config'] == config]

        summary = {
            'Configuration': config,
            'Samples': len(config_data),
            'RTT Mean (ms)': f"{config_data['client_rtt_ms'].mean():.3f}",
            'RTT Std (ms)': f"{config_data['client_rtt_ms'].std():.3f}",
            'RTT Min (ms)': f"{config_data['client_rtt_ms'].min():.3f}",
            'RTT Max (ms)': f"{config_data['client_rtt_ms'].max():.3f}",
            'RTT P95 (ms)': f"{config_data['client_rtt_ms'].quantile(0.95):.3f}",
            'RTT P99 (ms)': f"{config_data['client_rtt_ms'].quantile(0.99):.3f}",
            'Server Delay (ms)': f"{config_data['server_applied_delay_ms'].mean():.1f}",
            'Network Overhead (ms)': f"{config_data['estimated_network_overhead_ms'].mean():.3f}" if 'estimated_network_overhead_ms' in config_data.columns else 'N/A'
        }
        summary_data.append(summary)

    summary_df = pd.DataFrame(summary_data)

    # Save as CSV
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"results/performance_summary_{timestamp}.csv"
    summary_df.to_csv(filename, index=False)
    print(f"Saved performance summary: {filename}")

    # Print to console
    print("\nPERFORMANCE SUMMARY:")
    print("=" * 80)
    print(summary_df.to_string(index=False))

    return filename

def main():
    """Create all graphs and analysis"""

    print("=== RTT Measurement Graph Generation ===")
    print(f"Time: {datetime.now()}")

    # Find and load CSV files
    csv_files = find_csv_files()
    if not csv_files:
        return

    df = load_and_prepare_data(csv_files)

    print(f"\nCreating graphs and analysis...")

    # Create plots
    plot1 = create_rtt_comparison_plot(df)
    plot2 = create_detailed_statistics_plot(df)

    # Create summary table
    summary_file = create_performance_summary_table(df)

    print(f"\n{'='*60}")
    print("GRAPH GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"📊 RTT Analysis Plot: {plot1}")
    print(f"📈 Statistics Plot: {plot2}")
    print(f"📋 Summary Table: {summary_file}")

    print(f"\n✅ Generated comprehensive RTT analysis graphs")
    print(f"Use these plots for presentation, documentation, or further analysis")

if __name__ == "__main__":
    main()