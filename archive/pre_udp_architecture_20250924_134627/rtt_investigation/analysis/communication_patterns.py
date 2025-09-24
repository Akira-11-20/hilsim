#!/usr/bin/env python3
"""
Communication Patterns Visualization

PUB/SUB vs REQ/REP の違いを時系列で可視化
"""

import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

def create_comparison_chart():
    """通信パターン比較チャート作成"""

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    # Time axis
    time_points = np.arange(0, 100, 20)  # 0, 20, 40, 60, 80 ms

    # REQ/REP Pattern (上のグラフ)
    ax1.set_title('REQ/REP Pattern - Synchronous Communication', fontsize=14, fontweight='bold')

    # Request-Response pairs
    for i, t in enumerate(time_points):
        # Request
        ax1.arrow(t, 1, 0, -0.3, head_width=2, head_length=0.05, fc='blue', ec='blue')
        ax1.text(t-1, 1.1, f'REQ{i+1}', fontsize=10, ha='center')

        # Response (small delay)
        response_time = t + 1.7  # 1.7ms RTT from our test
        ax1.arrow(response_time, 0.3, 0, 0.3, head_width=2, head_length=0.05, fc='green', ec='green')
        ax1.text(response_time-1, 0.1, f'REP{i+1}', fontsize=10, ha='center')

        # RTT measurement
        ax1.annotate('', xy=(response_time, 0.8), xytext=(t, 0.8),
                    arrowprops=dict(arrowstyle='<->', color='red', lw=2))
        ax1.text((t + response_time)/2, 0.85, '1.7ms', ha='center', color='red', fontweight='bold')

    ax1.set_xlim(-10, 110)
    ax1.set_ylim(0, 1.3)
    ax1.set_ylabel('Numeric ← → Plant')
    ax1.set_xlabel('Time (ms)')
    ax1.grid(True, alpha=0.3)
    ax1.text(50, 0.5, '✅ Predictable RTT\n✅ No buffering\n✅ Synchronous',
             ha='center', va='center', bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen"))

    # PUB/SUB Pattern (下のグラフ)
    ax2.set_title('PUB/SUB Pattern - Asynchronous Communication', fontsize=14, fontweight='bold')

    # Commands (PUB)
    for i, t in enumerate(time_points):
        ax2.arrow(t, 1, 0, -0.2, head_width=2, head_length=0.05, fc='blue', ec='blue')
        ax2.text(t-1, 1.1, f'CMD{i+1}', fontsize=10, ha='center')

    # States (SUB) with increasing delay
    base_delay = 50  # Start with 50ms delay
    for i, t in enumerate(time_points):
        # Increasing delay due to buffering
        state_time = t + base_delay + (i * 200)  # Exponentially increasing delay
        if state_time < 110:  # Only draw if within chart
            ax2.arrow(state_time, 0.3, 0, 0.2, head_width=2, head_length=0.05, fc='orange', ec='orange')
            ax2.text(state_time-1, 0.1, f'STATE{i+1}', fontsize=10, ha='center')

            # RTT measurement (uncertain)
            ax2.annotate('', xy=(state_time, 0.8), xytext=(t, 0.8),
                        arrowprops=dict(arrowstyle='<->', color='red', lw=2, linestyle='--'))
            rtt_value = state_time - t
            ax2.text((t + state_time)/2, 0.85, f'{rtt_value:.0f}ms?', ha='center', color='red')

    ax2.set_xlim(-10, 110)
    ax2.set_ylim(0, 1.3)
    ax2.set_ylabel('Numeric ← → Plant')
    ax2.set_xlabel('Time (ms)')
    ax2.grid(True, alpha=0.3)
    ax2.text(50, 0.5, '⚠️ Unpredictable RTT\n⚠️ Message buffering\n⚠️ Asynchronous',
             ha='center', va='center', bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow"))

    plt.tight_layout()

    # Save chart
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'communication_patterns_{timestamp}.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"Communication patterns chart saved: {filename}")

    plt.show()

def create_rtt_comparison():
    """RTT比較チャート作成"""

    # Sample data points
    time_steps = np.arange(0, 500, 10)

    # REQ/REP RTT (stable around 1.7ms)
    reqrep_rtt = 1.7 + 0.1 * np.random.randn(len(time_steps))
    reqrep_rtt = np.clip(reqrep_rtt, 1.4, 2.4)  # Based on our test results

    # PUB/SUB RTT (increasing trend)
    pubsub_base = 1000  # Start at 1000ms
    pubsub_growth = np.linspace(0, 200, len(time_steps))  # Linear growth
    pubsub_noise = 30 * np.random.randn(len(time_steps))
    pubsub_rtt = pubsub_base + pubsub_growth + pubsub_noise

    plt.figure(figsize=(12, 6))

    plt.plot(time_steps, reqrep_rtt, 'g-', label='REQ/REP Pattern', linewidth=2)
    plt.plot(time_steps, pubsub_rtt, 'r-', label='PUB/SUB Pattern', linewidth=2)

    plt.xlabel('Message Number', fontsize=12)
    plt.ylabel('RTT (ms)', fontsize=12)
    plt.title('RTT Comparison: REQ/REP vs PUB/SUB', fontsize=14, fontweight='bold')

    plt.grid(True, alpha=0.3)
    plt.legend(fontsize=12)

    # Add annotations
    plt.annotate('Stable ~1.7ms', xy=(250, 1.7), xytext=(150, 5),
                arrowprops=dict(arrowstyle='->', color='green'),
                fontsize=12, color='green', fontweight='bold')

    plt.annotate('Growing 1000→1200ms', xy=(400, 1180), xytext=(300, 800),
                arrowprops=dict(arrowstyle='->', color='red'),
                fontsize=12, color='red', fontweight='bold')

    plt.ylim(0, 1300)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'rtt_comparison_{timestamp}.png'
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"RTT comparison chart saved: {filename}")

    plt.show()

if __name__ == "__main__":
    print("Creating communication patterns visualization...")
    create_comparison_chart()
    create_rtt_comparison()