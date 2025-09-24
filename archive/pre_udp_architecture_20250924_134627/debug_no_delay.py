#!/usr/bin/env python3
"""
no_delay発散原因の詳細分析
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# 日本語フォント対応
plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial']
plt.style.use('seaborn-v0_8')

def analyze_no_delay_divergence():
    """no_delay発散の詳細分析"""

    # データ読み込み
    plant_data = pd.read_csv('logs/no_delay_20250923_191436/plant_log.csv')
    numeric_data = pd.read_csv('logs/no_delay_20250923_191436/realtime_numeric_log.csv')

    print("="*60)
    print("🔍 NO_DELAY DIVERGENCE ANALYSIS")
    print("="*60)

    # 基本統計
    print(f"\n📊 Dataset Summary:")
    print(f"Plant data points: {len(plant_data)}")
    print(f"Numeric data points: {len(numeric_data)}")
    print(f"Simulation time: {plant_data['t'].iloc[-1]:.1f}s")

    # 初期動作の詳細分析（最初の100ステップ）
    print(f"\n🚀 Initial Behavior Analysis (First 100 steps):")

    plant_start = plant_data.head(100)
    numeric_start = numeric_data.head(100)

    print(f"Initial thrust commands:")
    for i in range(min(10, len(numeric_start))):
        row = numeric_start.iloc[i]
        print(f"  Step {i}: t={row['sim_time']:.3f}s, thrust={row['thrust_cmd']:.2f}N, "
              f"altitude_error={row['altitude_error']:.3f}m, altitude={row['altitude']:.3f}m")

    # PID制御パラメータ推定
    print(f"\n⚙️  PID Control Analysis:")
    print(f"Target setpoint: {numeric_start['setpoint'].iloc[0]:.1f}m")

    # 初期のerror-thrust関係から推定ゲイン計算
    initial_errors = numeric_start['altitude_error'].head(5)
    initial_thrusts = numeric_start['thrust_cmd'].head(5)

    # 重力補償を除いた制御入力
    gravity_compensation = 1.0 * 9.81  # mass * gravity
    control_thrusts = initial_thrusts - gravity_compensation

    print(f"First few error->thrust mappings (excluding gravity compensation {gravity_compensation:.1f}N):")
    for i in range(min(5, len(initial_errors))):
        print(f"  Error: {initial_errors.iloc[i]:.3f}m -> Control thrust: {control_thrusts.iloc[i]:.2f}N")

    # 推定比例ゲイン
    if len(initial_errors) > 1 and initial_errors.iloc[1] != 0:
        estimated_kp = control_thrusts.iloc[1] / initial_errors.iloc[1]
        print(f"Estimated Kp from step 1: {estimated_kp:.1f}")

    # 発散パターン分析
    print(f"\n📈 Divergence Pattern:")
    divergence_times = [10, 20, 30, 40, 50]

    for t_check in divergence_times:
        t_idx = plant_data[plant_data['t'] <= t_check].index[-1] if len(plant_data[plant_data['t'] <= t_check]) > 0 else 0
        if t_idx < len(plant_data):
            alt = plant_data['altitude'].iloc[t_idx]
            vel = plant_data['velocity'].iloc[t_idx]
            thrust = plant_data['thrust'].iloc[t_idx]
            print(f"  t={t_check}s: Alt={alt:.1f}m, Vel={vel:.1f}m/s, Thrust={thrust:.1f}N")

    # 制御ループの問題分析
    print(f"\n🔧 Control Loop Issues:")

    # 通信状況
    comm_timeouts = len(numeric_data[numeric_data['communication_status'] == 'TIMEOUT'])
    comm_ok = len(numeric_data[numeric_data['communication_status'] == 'OK'])
    print(f"Communication - OK: {comm_ok}, TIMEOUT: {comm_timeouts}")

    # RTT分析
    rtt_data = numeric_data[numeric_data['rtt_ms'] > 0]['rtt_ms']
    if len(rtt_data) > 0:
        print(f"RTT stats - Mean: {rtt_data.mean():.1f}ms, Max: {rtt_data.max():.1f}ms")

    # 制御周期の確認
    dt_values = numeric_data['control_dt'].describe()
    print(f"Control period stats:")
    print(f"  Mean: {dt_values['mean']*1000:.1f}ms")
    print(f"  Std:  {dt_values['std']*1000:.1f}ms")
    print(f"  Max:  {dt_values['max']*1000:.1f}ms")

    # 可視化
    create_detailed_plots(plant_data, numeric_data)

    return plant_data, numeric_data

def create_detailed_plots(plant_data, numeric_data):
    """詳細プロット作成"""

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('No Delay Divergence Analysis - Detailed Breakdown', fontsize=16, fontweight='bold')

    # 1. 初期30秒の高度応答
    ax1 = axes[0, 0]
    mask_30s = plant_data['t'] <= 30
    ax1.plot(plant_data['t'][mask_30s], plant_data['altitude'][mask_30s], 'b-', linewidth=2, label='Plant Altitude')

    # Numericの高度データもプロット
    mask_30s_num = numeric_data['sim_time'] <= 30
    ax1.plot(numeric_data['sim_time'][mask_30s_num], numeric_data['altitude'][mask_30s_num], 'r--', linewidth=1, alpha=0.7, label='Numeric Altitude')

    ax1.axhline(y=10, color='green', linestyle='--', alpha=0.8, label='Target (10m)')
    ax1.set_xlabel('Time [s]')
    ax1.set_ylabel('Altitude [m]')
    ax1.set_title('Altitude Response (First 30s)')
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    # 2. 推力コマンドの時系列
    ax2 = axes[0, 1]
    mask_30s = plant_data['t'] <= 30
    ax2.plot(plant_data['t'][mask_30s], plant_data['thrust'][mask_30s], 'g-', linewidth=2, label='Thrust Command')
    ax2.axhline(y=9.81, color='red', linestyle='--', alpha=0.8, label='Gravity (9.81N)')
    ax2.set_xlabel('Time [s]')
    ax2.set_ylabel('Thrust [N]')
    ax2.set_title('Thrust Command (First 30s)')
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    # 3. 速度の変化
    ax3 = axes[0, 2]
    mask_30s = plant_data['t'] <= 30
    ax3.plot(plant_data['t'][mask_30s], plant_data['velocity'][mask_30s], 'purple', linewidth=2)
    ax3.set_xlabel('Time [s]')
    ax3.set_ylabel('Velocity [m/s]')
    ax3.set_title('Velocity (First 30s)')
    ax3.grid(True, alpha=0.3)

    # 4. 制御エラーの変化
    ax4 = axes[1, 0]
    mask_30s_num = numeric_data['sim_time'] <= 30
    ax4.plot(numeric_data['sim_time'][mask_30s_num], numeric_data['altitude_error'][mask_30s_num], 'orange', linewidth=2)
    ax4.set_xlabel('Time [s]')
    ax4.set_ylabel('Altitude Error [m]')
    ax4.set_title('Control Error (First 30s)')
    ax4.grid(True, alpha=0.3)

    # 5. 制御周期の変化
    ax5 = axes[1, 1]
    ax5.plot(numeric_data['sim_time'], numeric_data['control_dt']*1000, 'brown', linewidth=1, alpha=0.7)
    ax5.axhline(y=20, color='red', linestyle='--', alpha=0.8, label='Target (20ms)')
    ax5.set_xlabel('Time [s]')
    ax5.set_ylabel('Control Period [ms]')
    ax5.set_title('Control Period Variation')
    ax5.grid(True, alpha=0.3)
    ax5.legend()

    # 6. 通信状態
    ax6 = axes[1, 2]
    comm_status = numeric_data['communication_status'].value_counts()
    colors = ['green', 'red'] if 'OK' in comm_status.index else ['red']
    ax6.pie(comm_status.values, labels=comm_status.index, autopct='%1.1f%%', colors=colors, startangle=90)
    ax6.set_title('Communication Status Distribution')

    plt.tight_layout()
    plt.savefig('no_delay_debug_analysis.png', dpi=300, bbox_inches='tight', facecolor='white')
    print(f"\n✅ Detailed analysis saved: no_delay_debug_analysis.png")

def compare_with_config():
    """設定ファイルと実際の動作を比較"""
    print(f"\n🔧 Configuration vs Actual Behavior:")

    # Numeric設定確認
    try:
        with open('numeric/app/config.yaml', 'r') as f:
            config_content = f.read()
        print("Current Numeric config:")
        print(config_content)
    except Exception as e:
        print(f"Could not read config: {e}")

if __name__ == "__main__":
    plant_data, numeric_data = analyze_no_delay_divergence()
    compare_with_config()