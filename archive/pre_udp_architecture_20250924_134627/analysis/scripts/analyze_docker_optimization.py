#!/usr/bin/env python3
"""
Analyze Docker Communication Optimization Results

Compare minimal Docker containers vs full HILS system communication overhead
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def create_optimization_analysis():
    """Create comprehensive analysis of Docker communication optimization"""

    print("=" * 80)
    print("DOCKER COMMUNICATION OPTIMIZATION ANALYSIS")
    print("=" * 80)

    # Results from minimal Docker containers (from previous test)
    minimal_docker_results = {
        'test_name': 'Minimal Bridge Network',
        'rtt_avg_ms': 0.31,
        'rtt_std_ms': 0.07,
        'rtt_min_ms': 0.22,
        'rtt_max_ms': 0.62,
        'rtt_median_ms': 0.30,
        'rtt_p95_ms': 0.45,
        'rtt_p99_ms': 0.52,
        'sample_count': 500
    }

    # Results from full HILS system (from previous analysis)
    hils_docker_results = {
        'test_name': 'HILS Full System',
        'rtt_avg_ms': 92.5,
        'rtt_std_ms': 2.9,
        'rtt_min_ms': 91.2,
        'rtt_max_ms': 97.4,
        'sample_count': 4895
    }

    # Results from localhost testing (from previous analysis)
    localhost_results = {
        'test_name': 'Localhost ZMQ',
        'rtt_avg_ms': 1.3,
        'rtt_std_ms': 0.2,
        'rtt_min_ms': 1.0,
        'rtt_max_ms': 1.5,
        'sample_count': 250
    }

    # Create comparison DataFrame
    comparison_data = [
        {
            'Environment': 'Localhost',
            'RTT_Avg_ms': localhost_results['rtt_avg_ms'],
            'RTT_Std_ms': localhost_results['rtt_std_ms'],
            'Overhead_Category': 'Baseline',
            'Description': 'Pure ZMQ on localhost'
        },
        {
            'Environment': 'Docker Minimal',
            'RTT_Avg_ms': minimal_docker_results['rtt_avg_ms'],
            'RTT_Std_ms': minimal_docker_results['rtt_std_ms'],
            'Overhead_Category': 'Docker Network',
            'Description': 'Minimal containers with bridge network'
        },
        {
            'Environment': 'HILS Full System',
            'RTT_Avg_ms': hils_docker_results['rtt_avg_ms'],
            'RTT_Std_ms': hils_docker_results['rtt_std_ms'],
            'Overhead_Category': 'Full Application',
            'Description': 'Complete HILS with Plant/Numeric logic'
        }
    ]

    df = pd.DataFrame(comparison_data)

    # Calculate overhead breakdown
    docker_network_overhead = minimal_docker_results['rtt_avg_ms'] - localhost_results['rtt_avg_ms']
    application_overhead = hils_docker_results['rtt_avg_ms'] - minimal_docker_results['rtt_avg_ms']
    total_overhead = hils_docker_results['rtt_avg_ms'] - localhost_results['rtt_avg_ms']

    print(f"Communication Overhead Breakdown:")
    print(f"  Localhost Baseline: {localhost_results['rtt_avg_ms']:.2f}ms")
    print(f"  + Docker Network:   {docker_network_overhead:.2f}ms")
    print(f"  + Application:      {application_overhead:.2f}ms")
    print(f"  = Total Overhead:   {total_overhead:.2f}ms")
    print()

    print(f"Overhead Analysis:")
    print(f"  Docker Network Impact: {docker_network_overhead/localhost_results['rtt_avg_ms']*100:.1f}% increase")
    print(f"  Application Impact:    {application_overhead/minimal_docker_results['rtt_avg_ms']*100:.0f}x increase")
    print(f"  Total Impact:          {total_overhead/localhost_results['rtt_avg_ms']*100:.0f}x increase")
    print()

    # Create visualization
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Docker Communication Optimization Analysis', fontsize=16)

    # 1. RTT Comparison
    environments = df['Environment']
    rtts = df['RTT_Avg_ms']
    stds = df['RTT_Std_ms']

    colors = ['blue', 'green', 'red']
    bars = ax1.bar(environments, rtts, yerr=stds, capsize=5, alpha=0.7, color=colors)
    ax1.set_ylabel('RTT (ms)')
    ax1.set_title('Communication Latency Comparison')
    ax1.grid(True, alpha=0.3)

    # Add value labels
    for bar, rtt, std in zip(bars, rtts, stds):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + std + 1,
                f'{rtt:.2f}ms', ha='center', va='bottom', fontweight='bold')

    # 2. Overhead Breakdown
    overhead_labels = ['Localhost\nBaseline', 'Docker\nNetwork', 'Application\nLogic']
    overhead_values = [localhost_results['rtt_avg_ms'], docker_network_overhead, application_overhead]
    overhead_colors = ['lightblue', 'orange', 'lightcoral']

    cumulative = np.cumsum([0] + overhead_values[:-1])
    for i, (label, value, color) in enumerate(zip(overhead_labels, overhead_values, overhead_colors)):
        ax2.bar(0, value, bottom=cumulative[i], color=color, alpha=0.8, label=label)

    ax2.set_ylabel('RTT (ms)')
    ax2.set_title('Overhead Breakdown')
    ax2.set_xticks([])
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # Add total label
    ax2.text(0, hils_docker_results['rtt_avg_ms'] + 2, f'Total: {hils_docker_results["rtt_avg_ms"]:.1f}ms',
            ha='center', va='bottom', fontweight='bold', fontsize=12)

    # 3. Performance Impact
    impact_categories = ['Network\\nOverhead', 'Application\\nOverhead']
    impact_percentages = [
        docker_network_overhead/localhost_results['rtt_avg_ms']*100,
        application_overhead/localhost_results['rtt_avg_ms']*100
    ]

    bars = ax3.bar(impact_categories, impact_percentages, alpha=0.7, color=['orange', 'red'])
    ax3.set_ylabel('Performance Impact (%)')
    ax3.set_title('Overhead Impact vs Baseline')
    ax3.grid(True, alpha=0.3)

    # Add value labels
    for bar, percentage in zip(bars, impact_percentages):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 50,
                f'{percentage:.0f}%', ha='center', va='bottom', fontweight='bold')

    # 4. Optimization Recommendations
    optimization_data = {
        'Strategy': ['Use Host\\nNetwork', 'Optimize\\nApplication', 'Reduce\\nDelay Config', 'Async\\nProcessing'],
        'Potential_Improvement_ms': [
            docker_network_overhead * 0.8,  # Host network could reduce 80% of network overhead
            application_overhead * 0.3,      # App optimization could reduce 30% of app overhead
            25,                              # Reducing delay config
            15                               # Async processing improvements
        ]
    }

    opt_df = pd.DataFrame(optimization_data)
    bars = ax4.bar(opt_df['Strategy'], opt_df['Potential_Improvement_ms'], alpha=0.7, color='green')
    ax4.set_ylabel('Potential RTT Reduction (ms)')
    ax4.set_title('Optimization Strategies')
    ax4.grid(True, alpha=0.3)

    # Add value labels
    for bar, improvement in zip(bars, opt_df['Potential_Improvement_ms']):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{improvement:.1f}ms', ha='center', va='bottom', fontweight='bold')

    plt.tight_layout()

    # Save to proper directory
    output_dir = 'communication_test_containers/results'
    os.makedirs(output_dir, exist_ok=True)

    plot_path = f'{output_dir}/docker_optimization_analysis.png'
    csv_path = f'{output_dir}/docker_optimization_comparison.csv'

    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    print(f"Analysis plot saved to {plot_path}")

    # Save detailed results
    df.to_csv(csv_path, index=False)
    print(f"Results saved to {csv_path}")

    # Optimization recommendations
    print("\n" + "="*60)
    print("OPTIMIZATION RECOMMENDATIONS")
    print("="*60)

    print("\n1. Network Optimization:")
    print(f"   Current Docker network overhead: {docker_network_overhead:.2f}ms")
    print("   • Use host network mode (network_mode: host)")
    print("   • Enable jumbo frames if supported")
    print("   • Reduce MTU if needed for stability")

    print("\n2. Application Optimization:")
    print(f"   Current application overhead: {application_overhead:.2f}ms")
    print("   • Simplify message processing")
    print("   • Use binary serialization instead of JSON")
    print("   • Reduce logging verbosity")
    print("   • Optimize PID calculation frequency")

    print("\n3. Configuration Optimization:")
    print("   • Reduce artificial delay settings for testing")
    print("   • Use asynchronous communication patterns")
    print("   • Implement message queuing for burst tolerance")

    print("\n4. Expected Results:")
    current_rtt = hils_docker_results['rtt_avg_ms']
    optimized_rtt = localhost_results['rtt_avg_ms'] + (docker_network_overhead * 0.2) + (application_overhead * 0.7)
    improvement = current_rtt - optimized_rtt

    print(f"   Current RTT: {current_rtt:.1f}ms")
    print(f"   Optimized RTT: {optimized_rtt:.1f}ms")
    print(f"   Improvement: {improvement:.1f}ms ({improvement/current_rtt*100:.1f}% reduction)")

if __name__ == "__main__":
    create_optimization_analysis()