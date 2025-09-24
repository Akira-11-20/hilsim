#!/usr/bin/env python3
"""
RTTと推力クリッピング分析
各遅延パターンでの実際のRTT値と推力クリッピングの影響を調査
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os

# 日本語フォント設定
plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial']
plt.style.use('seaborn-v0_8')

def analyze_rtt_and_clipping():
    """RTTと推力クリッピングの包括分析"""

    # テストケース定義
    test_cases = {
        'no_delay_20250923_191436': {
            'name': 'No Delay (Baseline)',
            'expected_rtt': 0,  # 遅延なし
            'config': 'enable_delay: false'
        },
        'light_delay_20250923_191646': {
            'name': 'Light Delay',
            'expected_rtt': 7,  # 2ms proc + 5ms response + 1ms jitter = ~7ms
            'config': 'proc=2ms + response=5ms + jitter=1ms'
        },
        'medium_delay_20250923_191914': {
            'name': 'Medium Delay',
            'expected_rtt': 28,  # 5ms + 20ms + 3ms = ~28ms
            'config': 'proc=5ms + response=20ms + jitter=3ms'
        },
        'heavy_delay_20250923_192151': {
            'name': 'Heavy Delay',
            'expected_rtt': 65,  # 10ms + 50ms + 5ms = ~65ms
            'config': 'proc=10ms + response=50ms + jitter=5ms'
        },
        'jitter_delay_20250923_192425': {
            'name': 'High Jitter',
            'expected_rtt': 40,  # 5ms + 15ms + 20ms variation = ~40ms average
            'config': 'proc=5ms + response=15ms + jitter=20ms'
        }
    }

    results = []

    print("="*80)
    print("🔍 RTT AND THRUST CLIPPING ANALYSIS")
    print("="*80)

    for run_id, test_info in test_cases.items():
        print(f"\n📊 Analyzing: {test_info['name']}")
        print(f"Config: {test_info['config']}")
        print(f"Expected RTT: ~{test_info['expected_rtt']}ms")

        # データ読み込み
        try:
            numeric_data = pd.read_csv(f'logs/{run_id}/realtime_numeric_log.csv')

            # RTT分析
            rtt_data = numeric_data[numeric_data['rtt_ms'] > 0]['rtt_ms']

            rtt_stats = {
                'test_name': test_info['name'],
                'expected_rtt': test_info['expected_rtt'],
                'measurements': len(rtt_data),
                'mean_rtt': rtt_data.mean() if len(rtt_data) > 0 else 0,
                'std_rtt': rtt_data.std() if len(rtt_data) > 0 else 0,
                'min_rtt': rtt_data.min() if len(rtt_data) > 0 else 0,
                'max_rtt': rtt_data.max() if len(rtt_data) > 0 else 0,
                'median_rtt': rtt_data.median() if len(rtt_data) > 0 else 0
            }

            # 推力クリッピング分析
            thrust_data = numeric_data['thrust_cmd']

            # PID出力の推定（推力 - 重力補償）
            gravity_compensation = 9.81  # mass=1.0 * gravity=9.81
            estimated_pid_output = thrust_data - gravity_compensation

            clipping_stats = {
                'total_steps': len(numeric_data),
                'zero_thrust_count': len(thrust_data[thrust_data == 0]),
                'zero_thrust_percentage': (len(thrust_data[thrust_data == 0]) / len(thrust_data)) * 100,
                'max_thrust_count': len(thrust_data[thrust_data == 1000.0]),
                'negative_pid_count': len(estimated_pid_output[estimated_pid_output < 0]),
                'negative_pid_percentage': (len(estimated_pid_output[estimated_pid_output < 0]) / len(estimated_pid_output)) * 100,
                'mean_thrust': thrust_data.mean(),
                'std_thrust': thrust_data.std(),
                'mean_pid_output': estimated_pid_output.mean(),
                'min_pid_output': estimated_pid_output.min()
            }

            # 時系列での推力クリッピング発生タイミング
            first_zero_thrust = thrust_data[thrust_data == 0]
            if len(first_zero_thrust) > 0:
                first_zero_idx = thrust_data[thrust_data == 0].index[0]
                first_zero_time = numeric_data.iloc[first_zero_idx]['sim_time']
            else:
                first_zero_time = None

            # 結果表示
            print(f"\n🎯 RTT Results:")
            print(f"  Expected: {rtt_stats['expected_rtt']}ms")
            print(f"  Actual Mean: {rtt_stats['mean_rtt']:.1f}ms")
            print(f"  Actual Range: {rtt_stats['min_rtt']:.1f} - {rtt_stats['max_rtt']:.1f}ms")
            print(f"  Measurements: {rtt_stats['measurements']}/{numeric_data.shape[0]}")

            if rtt_stats['expected_rtt'] > 0:
                rtt_ratio = rtt_stats['mean_rtt'] / rtt_stats['expected_rtt']
                print(f"  Ratio (Actual/Expected): {rtt_ratio:.1f}x")

            print(f"\n⚡ Thrust Clipping Results:")
            print(f"  Zero thrust steps: {clipping_stats['zero_thrust_count']}/{clipping_stats['total_steps']} ({clipping_stats['zero_thrust_percentage']:.1f}%)")
            print(f"  Max thrust steps: {clipping_stats['max_thrust_count']}")
            print(f"  Negative PID output: {clipping_stats['negative_pid_count']}/{clipping_stats['total_steps']} ({clipping_stats['negative_pid_percentage']:.1f}%)")
            print(f"  Mean thrust: {clipping_stats['mean_thrust']:.1f}N")
            print(f"  Min PID output: {clipping_stats['min_pid_output']:.1f}N")

            if first_zero_time is not None:
                print(f"  First zero thrust at: t={first_zero_time:.2f}s")

            # 早期の推力クリッピング確認（最初の10秒）
            early_data = numeric_data[numeric_data['sim_time'] <= 10]
            early_zero_count = len(early_data[early_data['thrust_cmd'] == 0])
            print(f"  Zero thrust in first 10s: {early_zero_count}/{len(early_data)} ({(early_zero_count/len(early_data)*100):.1f}%)")

            # 統計データを保存
            combined_stats = {**rtt_stats, **clipping_stats, 'first_zero_time': first_zero_time}
            results.append(combined_stats)

        except Exception as e:
            print(f"❌ Error loading {run_id}: {e}")

    # 結果の比較可視化
    create_comparison_plots(results, test_cases)

    # サマリーテーブル
    print_summary_table(results)

    return results

def create_comparison_plots(results, test_cases):
    """比較プロット作成"""

    if not results:
        print("No data to plot")
        return

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('RTT and Thrust Clipping Analysis Across Delay Patterns', fontsize=16, fontweight='bold')

    test_names = [r['test_name'] for r in results]
    colors = ['blue', 'green', 'orange', 'red', 'purple']

    # 1. Expected vs Actual RTT
    ax1 = axes[0, 0]
    expected_rtt = [r['expected_rtt'] for r in results]
    actual_rtt = [r['mean_rtt'] for r in results]

    x = range(len(test_names))
    width = 0.35
    ax1.bar([i - width/2 for i in x], expected_rtt, width, label='Expected RTT', alpha=0.7, color='lightblue')
    ax1.bar([i + width/2 for i in x], actual_rtt, width, label='Actual RTT', alpha=0.7, color='darkblue')

    ax1.set_xlabel('Delay Configuration')
    ax1.set_ylabel('RTT [ms]')
    ax1.set_title('Expected vs Actual RTT')
    ax1.set_xticks(x)
    ax1.set_xticklabels([name.replace(' ', '\n') for name in test_names], fontsize=9)
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 2. Zero Thrust Percentage
    ax2 = axes[0, 1]
    zero_thrust_pct = [r['zero_thrust_percentage'] for r in results]
    bars = ax2.bar(x, zero_thrust_pct, color=colors, alpha=0.7)
    ax2.set_xlabel('Delay Configuration')
    ax2.set_ylabel('Zero Thrust Percentage [%]')
    ax2.set_title('Thrust Clipping to Zero')
    ax2.set_xticks(x)
    ax2.set_xticklabels([name.replace(' ', '\n') for name in test_names], fontsize=9)
    ax2.grid(True, alpha=0.3)

    # 数値表示
    for bar, pct in zip(bars, zero_thrust_pct):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{pct:.1f}%', ha='center', va='bottom', fontweight='bold')

    # 3. Negative PID Output Percentage
    ax3 = axes[0, 2]
    negative_pid_pct = [r['negative_pid_percentage'] for r in results]
    bars = ax3.bar(x, negative_pid_pct, color=colors, alpha=0.7)
    ax3.set_xlabel('Delay Configuration')
    ax3.set_ylabel('Negative PID Output [%]')
    ax3.set_title('PID Output Going Negative')
    ax3.set_xticks(x)
    ax3.set_xticklabels([name.replace(' ', '\n') for name in test_names], fontsize=9)
    ax3.grid(True, alpha=0.3)

    # 数値表示
    for bar, pct in zip(bars, negative_pid_pct):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{pct:.1f}%', ha='center', va='bottom', fontweight='bold')

    # 4. First Zero Thrust Time
    ax4 = axes[1, 0]
    first_zero_times = [r['first_zero_time'] if r['first_zero_time'] is not None else 0 for r in results]
    bars = ax4.bar(x, first_zero_times, color=colors, alpha=0.7)
    ax4.set_xlabel('Delay Configuration')
    ax4.set_ylabel('Time [s]')
    ax4.set_title('First Zero Thrust Occurrence')
    ax4.set_xticks(x)
    ax4.set_xticklabels([name.replace(' ', '\n') for name in test_names], fontsize=9)
    ax4.grid(True, alpha=0.3)

    # 数値表示
    for bar, time_val in zip(bars, first_zero_times):
        height = bar.get_height()
        if height > 0:
            ax4.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                    f'{time_val:.1f}s', ha='center', va='bottom', fontweight='bold')

    # 5. RTT Distribution Box Plot
    ax5 = axes[1, 1]

    # 各ケースのRTTデータを収集
    rtt_distributions = []
    labels = []

    for run_id, test_info in test_cases.items():
        try:
            numeric_data = pd.read_csv(f'logs/{run_id}/realtime_numeric_log.csv')
            rtt_data = numeric_data[numeric_data['rtt_ms'] > 0]['rtt_ms']
            if len(rtt_data) > 0:
                rtt_distributions.append(rtt_data.values)
                labels.append(test_info['name'].replace(' ', '\n'))
        except:
            pass

    if rtt_distributions:
        ax5.boxplot(rtt_distributions, labels=labels)
        ax5.set_ylabel('RTT [ms]')
        ax5.set_title('RTT Distribution')
        ax5.grid(True, alpha=0.3)
        ax5.tick_params(axis='x', rotation=45)

    # 6. Mean Thrust vs RTT Scatter
    ax6 = axes[1, 2]
    mean_thrust_values = [r['mean_thrust'] for r in results]
    ax6.scatter(actual_rtt, mean_thrust_values, c=colors, s=100, alpha=0.7)

    for i, name in enumerate(test_names):
        ax6.annotate(name.replace(' ', '\n'), (actual_rtt[i], mean_thrust_values[i]),
                    xytext=(5, 5), textcoords='offset points', fontsize=8)

    ax6.set_xlabel('Actual RTT [ms]')
    ax6.set_ylabel('Mean Thrust [N]')
    ax6.set_title('Mean Thrust vs RTT')
    ax6.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('rtt_and_clipping_analysis.png', dpi=300, bbox_inches='tight', facecolor='white')
    print(f"\n✅ Analysis saved: rtt_and_clipping_analysis.png")

def print_summary_table(results):
    """結果サマリーテーブル"""

    print(f"\n" + "="*100)
    print(f"📋 SUMMARY TABLE")
    print(f"="*100)

    header = f"{'Test Case':<15} {'Expected RTT':<12} {'Actual RTT':<11} {'Zero Thrust %':<13} {'Negative PID %':<15} {'First Zero Time':<15}"
    print(header)
    print("-" * len(header))

    for r in results:
        first_zero_str = f"{r['first_zero_time']:.1f}s" if r['first_zero_time'] is not None else "N/A"
        row = f"{r['test_name']:<15} {r['expected_rtt']:<12} {r['mean_rtt']:<11.1f} {r['zero_thrust_percentage']:<13.1f} {r['negative_pid_percentage']:<15.1f} {first_zero_str:<15}"
        print(row)

if __name__ == "__main__":
    results = analyze_rtt_and_clipping()