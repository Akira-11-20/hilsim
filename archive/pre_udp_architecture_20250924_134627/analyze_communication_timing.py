#!/usr/bin/env python3
"""
通信タイミング詳細分析
no_delayケースでの通信パターンと推力停止の原因を特定
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def analyze_communication_timing():
    """通信タイミングの詳細分析"""

    # no_delayデータを読み込み
    plant_data = pd.read_csv('logs/no_delay_20250923_191436/plant_log.csv')
    numeric_data = pd.read_csv('logs/no_delay_20250923_191436/realtime_numeric_log.csv')

    print("="*60)
    print("🔍 COMMUNICATION TIMING ANALYSIS")
    print("="*60)

    # 基本統計
    print(f"\n📊 Dataset Overview:")
    print(f"Plant steps: {len(plant_data)}")
    print(f"Numeric steps: {len(numeric_data)}")
    print(f"Plant final time: {plant_data['t'].iloc[-1]:.1f}s")
    print(f"Numeric final time: {numeric_data['sim_time'].iloc[-1]:.1f}s")

    # 推力が0になる時点を特定
    print(f"\n🔍 Thrust Behavior Analysis:")

    # Plant側の推力データ
    non_zero_thrust = plant_data[plant_data['thrust'] != 0]
    zero_thrust = plant_data[plant_data['thrust'] == 0]

    if len(non_zero_thrust) > 0 and len(zero_thrust) > 0:
        last_non_zero_time = non_zero_thrust['t'].iloc[-1]
        first_zero_time = zero_thrust['t'].iloc[0]

        print(f"Last non-zero thrust: t={last_non_zero_time:.2f}s, thrust={non_zero_thrust['thrust'].iloc[-1]:.2f}N")
        print(f"First zero thrust: t={first_zero_time:.2f}s")
        print(f"Thrust transition at: t={last_non_zero_time:.2f}s → t={first_zero_time:.2f}s")

    # 通信状態の詳細分析
    print(f"\n📡 Communication Status Analysis:")

    comm_status_counts = numeric_data['communication_status'].value_counts()
    print(f"Communication status distribution:")
    for status, count in comm_status_counts.items():
        percentage = (count / len(numeric_data)) * 100
        print(f"  {status}: {count} ({percentage:.1f}%)")

    # RTT分析
    rtt_data = numeric_data[numeric_data['rtt_ms'] > 0]
    if len(rtt_data) > 0:
        print(f"\nRTT Analysis:")
        print(f"  Valid RTT measurements: {len(rtt_data)}")
        print(f"  Mean RTT: {rtt_data['rtt_ms'].mean():.1f}ms")
        print(f"  Std RTT: {rtt_data['rtt_ms'].std():.1f}ms")
        print(f"  Max RTT: {rtt_data['rtt_ms'].max():.1f}ms")
        print(f"  Min RTT: {rtt_data['rtt_ms'].min():.1f}ms")

    # タイムアウトの発生パターン
    timeout_data = numeric_data[numeric_data['communication_status'] == 'TIMEOUT']
    if len(timeout_data) > 0:
        print(f"\n⏱️ Timeout Analysis:")
        print(f"Total timeouts: {len(timeout_data)}")
        print(f"First timeout at: t={timeout_data['sim_time'].iloc[0]:.2f}s")
        if len(timeout_data) > 1:
            print(f"Last timeout at: t={timeout_data['sim_time'].iloc[-1]:.2f}s")

    # 制御周期の分析
    print(f"\n⏰ Control Period Analysis:")
    dt_stats = numeric_data['control_dt'].describe()
    print(f"Control period stats (ms):")
    print(f"  Mean: {dt_stats['mean']*1000:.1f}ms")
    print(f"  Std:  {dt_stats['std']*1000:.1f}ms")
    print(f"  Min:  {dt_stats['min']*1000:.1f}ms")
    print(f"  Max:  {dt_stats['max']*1000:.1f}ms")

    # 異常に長い制御周期を特定
    long_periods = numeric_data[numeric_data['control_dt'] > 0.015]  # 15ms以上
    if len(long_periods) > 0:
        print(f"\nLong control periods (>15ms): {len(long_periods)}")
        for _, row in long_periods.head(5).iterrows():
            print(f"  Step {row['seq']}: t={row['sim_time']:.2f}s, dt={row['control_dt']*1000:.1f}ms")

    # 連続失敗の分析
    max_failures = numeric_data['consecutive_failures'].max()
    if max_failures > 0:
        print(f"\n❌ Consecutive Failures Analysis:")
        print(f"Max consecutive failures: {max_failures}")

        failure_data = numeric_data[numeric_data['consecutive_failures'] > 0]
        if len(failure_data) > 0:
            print(f"Steps with failures: {len(failure_data)}")
            print(f"First failure at: t={failure_data['sim_time'].iloc[0]:.2f}s")

    # 推力コマンドの変化パターン
    print(f"\n🚀 Thrust Command Pattern:")
    thrust_stats = numeric_data['thrust_cmd'].describe()
    print(f"Thrust command stats:")
    print(f"  Mean: {thrust_stats['mean']:.1f}N")
    print(f"  Std:  {thrust_stats['std']:.1f}N")
    print(f"  Min:  {thrust_stats['min']:.1f}N")
    print(f"  Max:  {thrust_stats['max']:.1f}N")

    # 時系列での推力変化
    print(f"\nThrust evolution over time:")
    time_points = [1, 5, 10, 15, 20, 30]
    for t in time_points:
        mask = numeric_data['sim_time'] >= t
        if np.any(mask):
            idx = numeric_data[mask].index[0]
            row = numeric_data.iloc[idx]
            print(f"  t={t:2d}s: thrust={row['thrust_cmd']:6.1f}N, alt={row['altitude']:8.1f}m, status={row['communication_status']}")

    # Plant側とNumeric側の時刻同期確認
    print(f"\n⏲️ Time Synchronization Analysis:")

    # 同じステップでの時刻比較（最初の100ステップ）
    sync_analysis = []
    for i in range(min(100, len(plant_data), len(numeric_data))):
        plant_time = plant_data['t'].iloc[i]
        numeric_time = numeric_data['sim_time'].iloc[i]
        time_diff = abs(plant_time - numeric_time)
        sync_analysis.append(time_diff)

    if sync_analysis:
        avg_sync_error = np.mean(sync_analysis)
        max_sync_error = np.max(sync_analysis)
        print(f"Time sync error - Mean: {avg_sync_error*1000:.2f}ms, Max: {max_sync_error*1000:.2f}ms")

    # 可視化
    create_timing_plots(plant_data, numeric_data)

    return plant_data, numeric_data

def create_timing_plots(plant_data, numeric_data):
    """タイミング分析の可視化"""

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Communication Timing Analysis - No Delay Case', fontsize=16, fontweight='bold')

    # 1. 推力の時系列（詳細）
    ax1 = axes[0, 0]
    mask_60s = plant_data['t'] <= 60
    ax1.plot(plant_data['t'][mask_60s], plant_data['thrust'][mask_60s], 'b-', linewidth=2, label='Plant Thrust')

    # Numeric側の推力コマンドも重ねる
    mask_60s_num = numeric_data['sim_time'] <= 60
    ax1.plot(numeric_data['sim_time'][mask_60s_num], numeric_data['thrust_cmd'][mask_60s_num],
             'r--', linewidth=1, alpha=0.7, label='Numeric Command')

    ax1.set_xlabel('Time [s]')
    ax1.set_ylabel('Thrust [N]')
    ax1.set_title('Thrust Commands vs Plant Thrust (First 60s)')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # 2. 通信状態とRTT
    ax2 = axes[0, 1]

    # RTTデータ
    rtt_data = numeric_data[numeric_data['rtt_ms'] > 0]
    ax2.scatter(rtt_data['sim_time'], rtt_data['rtt_ms'], c='green', s=1, alpha=0.6, label='RTT')

    # タイムアウト
    timeout_data = numeric_data[numeric_data['communication_status'] == 'TIMEOUT']
    if len(timeout_data) > 0:
        ax2.scatter(timeout_data['sim_time'], [2000]*len(timeout_data), c='red', s=10, marker='x', label='Timeout')

    ax2.set_xlabel('Time [s]')
    ax2.set_ylabel('RTT [ms]')
    ax2.set_title('Communication RTT and Timeouts')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    ax2.set_ylim(0, 2100)

    # 3. 制御周期の変動
    ax3 = axes[0, 2]
    ax3.plot(numeric_data['sim_time'], numeric_data['control_dt']*1000, 'purple', linewidth=1, alpha=0.7)
    ax3.axhline(y=20, color='red', linestyle='--', alpha=0.8, label='Target (20ms)')
    ax3.set_xlabel('Time [s]')
    ax3.set_ylabel('Control Period [ms]')
    ax3.set_title('Control Period Variation')
    ax3.grid(True, alpha=0.3)
    ax3.legend()

    # 4. 高度と推力の相関
    ax4 = axes[1, 0]
    mask_30s = numeric_data['sim_time'] <= 30
    ax4_twin = ax4.twinx()

    line1 = ax4.plot(numeric_data['sim_time'][mask_30s], numeric_data['altitude'][mask_30s], 'b-', linewidth=2, label='Altitude')
    line2 = ax4_twin.plot(numeric_data['sim_time'][mask_30s], numeric_data['thrust_cmd'][mask_30s], 'r-', linewidth=2, label='Thrust')

    ax4.set_xlabel('Time [s]')
    ax4.set_ylabel('Altitude [m]', color='b')
    ax4_twin.set_ylabel('Thrust [N]', color='r')
    ax4.set_title('Altitude vs Thrust Command (First 30s)')
    ax4.grid(True, alpha=0.3)

    # 両方の凡例を表示
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax4.legend(lines, labels, loc='upper left')

    # 5. 連続失敗カウント
    ax5 = axes[1, 1]
    ax5.plot(numeric_data['sim_time'], numeric_data['consecutive_failures'], 'orange', linewidth=2)
    ax5.set_xlabel('Time [s]')
    ax5.set_ylabel('Consecutive Failures')
    ax5.set_title('Communication Failure Count')
    ax5.grid(True, alpha=0.3)

    # 6. 推力分布（初期 vs 後期）
    ax6 = axes[1, 2]

    # 初期30秒と後期30秒での推力分布比較
    early_thrust = numeric_data[numeric_data['sim_time'] <= 30]['thrust_cmd']
    late_thrust = numeric_data[numeric_data['sim_time'] >= 50]['thrust_cmd']

    ax6.hist(early_thrust, bins=30, alpha=0.6, label=f'Early (0-30s)\nMean: {early_thrust.mean():.1f}N', color='blue')
    ax6.hist(late_thrust, bins=30, alpha=0.6, label=f'Late (50-80s)\nMean: {late_thrust.mean():.1f}N', color='red')

    ax6.set_xlabel('Thrust Command [N]')
    ax6.set_ylabel('Frequency')
    ax6.set_title('Thrust Distribution: Early vs Late')
    ax6.legend()
    ax6.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('communication_timing_analysis.png', dpi=300, bbox_inches='tight', facecolor='white')
    print(f"\n✅ Timing analysis saved: communication_timing_analysis.png")

if __name__ == "__main__":
    analyze_communication_timing()