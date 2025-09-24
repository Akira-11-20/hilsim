#!/usr/bin/env python3
"""
遅延影響分析スクリプト

5つの遅延パターンの実行結果を比較分析し、
通信遅延が制御性能に与える影響を可視化します。
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import os
from pathlib import Path

# 日本語フォント設定
plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial']
plt.style.use('seaborn-v0_8')

def load_run_data(run_id):
    """指定されたRUN_IDのデータを読み込み"""
    log_dir = f"logs/{run_id}"

    try:
        # Plant データ
        plant_file = f"{log_dir}/plant_log.csv"
        plant_data = pd.read_csv(plant_file)

        # Numeric データ
        numeric_file = f"{log_dir}/realtime_numeric_log.csv"
        numeric_data = pd.read_csv(numeric_file)

        return plant_data, numeric_data
    except Exception as e:
        print(f"Error loading {run_id}: {e}")
        return None, None

def analyze_control_performance(plant_data, numeric_data, delay_name):
    """制御性能を分析"""
    results = {
        'delay_type': delay_name,
        'final_altitude_plant': plant_data['altitude'].iloc[-1],
        'final_altitude_numeric': numeric_data['altitude'].iloc[-1],
        'max_altitude_plant': plant_data['altitude'].max(),
        'altitude_deviation': abs(plant_data['altitude'].iloc[-1] - 10.0),  # 目標は10m
        'overshoot': max(0, plant_data['altitude'].max() - 10.0),
        'settling_time': None,
        'steady_state_error': abs(plant_data['altitude'].iloc[-1] - 10.0),
        'total_steps': len(plant_data),
        'communication_loss': max(0, len(plant_data) - len(numeric_data))
    }

    # 整定時間の概算（目標値±10%に収束する時間）
    target_range = [9.0, 11.0]
    for i in range(len(plant_data)-500, len(plant_data)):
        if i > 100:
            window = plant_data['altitude'].iloc[i-100:i]
            if all(target_range[0] <= alt <= target_range[1] for alt in window):
                results['settling_time'] = plant_data['t'].iloc[i]
                break

    return results

def create_comparison_plots():
    """比較プロット作成"""

    # テストケース定義
    test_cases = {
        'no_delay_20250923_191436': 'No Delay (Baseline)',
        'light_delay_20250923_191646': 'Light Delay (5ms+2ms+1ms)',
        'medium_delay_20250923_191914': 'Medium Delay (20ms+5ms+3ms)',
        'heavy_delay_20250923_192151': 'Heavy Delay (50ms+10ms+5ms)',
        'jitter_delay_20250923_192425': 'High Jitter (15ms+5ms+20ms)'
    }

    all_results = []
    plot_data = {}

    print("Loading and analyzing delay test results...")

    for run_id, delay_name in test_cases.items():
        print(f"Processing: {delay_name}")
        plant_data, numeric_data = load_run_data(run_id)

        if plant_data is not None and numeric_data is not None:
            results = analyze_control_performance(plant_data, numeric_data, delay_name)
            all_results.append(results)

            # プロット用データ保存
            plot_data[delay_name] = {
                'plant': plant_data,
                'numeric': numeric_data
            }

    # 結果をDataFrameに変換
    results_df = pd.DataFrame(all_results)

    # プロット作成
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('Communication Delay Impact Analysis on HILS Control Performance', fontsize=16, fontweight='bold')

    # 1. 高度軌道比較
    ax1 = axes[0, 0]
    colors = ['blue', 'green', 'orange', 'red', 'purple']

    for i, (delay_name, data) in enumerate(plot_data.items()):
        time_plant = data['plant']['t']
        alt_plant = data['plant']['altitude']

        # 最初の30秒のみプロット（詳細確認用）
        mask = time_plant <= 30
        ax1.plot(time_plant[mask], alt_plant[mask], color=colors[i], linewidth=2, label=delay_name, alpha=0.8)

    ax1.axhline(y=10, color='black', linestyle='--', alpha=0.5, label='Target (10m)')
    ax1.set_xlabel('Time [s]')
    ax1.set_ylabel('Altitude [m]')
    ax1.set_title('Altitude Response (First 30s)')
    ax1.grid(True, alpha=0.3)
    ax1.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

    # 2. 最終高度比較
    ax2 = axes[0, 1]
    final_alts = results_df['final_altitude_plant']
    delay_types = results_df['delay_type']

    bars = ax2.bar(range(len(delay_types)), final_alts, color=colors[:len(delay_types)], alpha=0.7)
    ax2.axhline(y=10, color='red', linestyle='--', linewidth=2, label='Target (10m)')
    ax2.set_xlabel('Delay Configuration')
    ax2.set_ylabel('Final Altitude [m]')
    ax2.set_title('Final Altitude by Delay Type')
    ax2.set_xticks(range(len(delay_types)))
    ax2.set_xticklabels([dt.replace(' ', '\\n') for dt in delay_types], rotation=0, fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    # 数値表示
    for bar, alt in zip(bars, final_alts):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height + max(final_alts)*0.01,
                f'{alt:.1f}m', ha='center', va='bottom', fontweight='bold')

    # 3. オーバーシュート比較
    ax3 = axes[0, 2]
    overshoots = results_df['overshoot']

    bars = ax3.bar(range(len(delay_types)), overshoots, color=colors[:len(delay_types)], alpha=0.7)
    ax3.set_xlabel('Delay Configuration')
    ax3.set_ylabel('Overshoot [m]')
    ax3.set_title('Overshoot by Delay Type')
    ax3.set_xticks(range(len(delay_types)))
    ax3.set_xticklabels([dt.replace(' ', '\\n') for dt in delay_types], rotation=0, fontsize=9)
    ax3.grid(True, alpha=0.3)

    # 数値表示
    for bar, overshoot in zip(bars, overshoots):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height + max(overshoots)*0.01,
                f'{overshoot:.1f}m', ha='center', va='bottom', fontweight='bold')

    # 4. 定常偏差比較
    ax4 = axes[1, 0]
    steady_errors = results_df['steady_state_error']

    bars = ax4.bar(range(len(delay_types)), steady_errors, color=colors[:len(delay_types)], alpha=0.7)
    ax4.set_xlabel('Delay Configuration')
    ax4.set_ylabel('Steady State Error [m]')
    ax4.set_title('Steady State Error by Delay Type')
    ax4.set_xticks(range(len(delay_types)))
    ax4.set_xticklabels([dt.replace(' ', '\\n') for dt in delay_types], rotation=0, fontsize=9)
    ax4.grid(True, alpha=0.3)

    # 数値表示
    for bar, error in zip(bars, steady_errors):
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height + max(steady_errors)*0.01,
                f'{error:.1f}m', ha='center', va='bottom', fontweight='bold')

    # 5. 全期間高度軌道
    ax5 = axes[1, 1]

    for i, (delay_name, data) in enumerate(plot_data.items()):
        time_plant = data['plant']['t']
        alt_plant = data['plant']['altitude']
        ax5.plot(time_plant, alt_plant, color=colors[i], linewidth=1.5, label=delay_name, alpha=0.8)

    ax5.axhline(y=10, color='black', linestyle='--', alpha=0.5, label='Target (10m)')
    ax5.set_xlabel('Time [s]')
    ax5.set_ylabel('Altitude [m]')
    ax5.set_title('Complete Altitude Trajectory (80s)')
    ax5.grid(True, alpha=0.3)
    ax5.legend(bbox_to_anchor=(1.05, 1), loc='upper left')

    # 6. パフォーマンス統計表
    ax6 = axes[1, 2]
    ax6.axis('off')

    # 統計テーブル作成
    table_data = []
    for _, row in results_df.iterrows():
        table_data.append([
            row['delay_type'].replace(' ', '\\n'),
            f"{row['final_altitude_plant']:.1f}m",
            f"{row['overshoot']:.1f}m",
            f"{row['steady_state_error']:.1f}m"
        ])

    table = ax6.table(cellText=table_data,
                     colLabels=['Delay Type', 'Final Alt', 'Overshoot', 'SS Error'],
                     cellLoc='center',
                     loc='center',
                     bbox=[0, 0, 1, 1])

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 2)

    # ヘッダーをハイライト
    for i in range(4):
        table[(0, i)].set_facecolor('#4CAF50')
        table[(0, i)].set_text_props(weight='bold', color='white')

    ax6.set_title('Performance Summary', fontweight='bold')

    plt.tight_layout()

    # 保存
    output_file = 'delay_impact_analysis.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    print(f"\\n✅ Analysis complete! Saved: {output_file}")

    # 結果サマリー出力
    print("\\n" + "="*60)
    print("🔍 DELAY IMPACT ANALYSIS SUMMARY")
    print("="*60)

    for _, row in results_df.iterrows():
        print(f"\\n📊 {row['delay_type']}:")
        print(f"   Final Altitude: {row['final_altitude_plant']:.1f}m (Target: 10.0m)")
        print(f"   Overshoot: {row['overshoot']:.1f}m")
        print(f"   Steady State Error: {row['steady_state_error']:.1f}m")
        print(f"   Max Altitude: {row['max_altitude_plant']:.1f}m")

    # 最良・最悪ケース分析
    best_case = results_df.loc[results_df['steady_state_error'].idxmin()]
    worst_case = results_df.loc[results_df['steady_state_error'].idxmax()]

    print(f"\\n🏆 Best Performance: {best_case['delay_type']}")
    print(f"   Steady State Error: {best_case['steady_state_error']:.1f}m")

    print(f"\\n⚠️  Worst Performance: {worst_case['delay_type']}")
    print(f"   Steady State Error: {worst_case['steady_state_error']:.1f}m")

    print("\\n" + "="*60)

    return results_df

if __name__ == "__main__":
    results = create_comparison_plots()