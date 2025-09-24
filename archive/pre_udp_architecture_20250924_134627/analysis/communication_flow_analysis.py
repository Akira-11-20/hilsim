#!/usr/bin/env python3
"""
通信フロー分析スクリプト

HILSシステムの通信構造とRTT変動の原因を詳細に分析する
"""

import time
import matplotlib.pyplot as plt
import numpy as np

def analyze_communication_structure():
    """通信構造の詳細分析"""

    print("=== HILS通信構造分析 ===\n")

    print("1. 通信アーキテクチャ:")
    print("   Plant ←→ Numeric 間の ZeroMQ PUB/SUB 通信")
    print("   Plant:  PUB (状態データ配信) + SUB (制御コマンド受信)")
    print("   Numeric: SUB (状態データ受信) + PUB (制御コマンド送信)")
    print()

    print("2. RTT測定の仕組み:")
    print("   ┌─────────────────────────────────────────────────────────┐")
    print("   │ Numeric → Plant: 制御コマンド送信                        │")
    print("   │   - sync_timestamp記録                                 │")
    print("   │   - seq番号付与                                        │")
    print("   │ ↓                                                       │")
    print("   │ Plant: コマンド処理                                     │")
    print("   │   - 遅延シミュレーション適用 (enable_delay=True時)        │")
    print("   │   - 物理状態更新                                        │")
    print("   │ ↓                                                       │")
    print("   │ Plant → Numeric: 状態データ配信                          │")
    print("   │   - latest_cmd_seq含む                                 │")
    print("   │ ↓                                                       │")
    print("   │ Numeric: RTT計算                                       │")
    print("   │   - recv_sync_timestamp - send_sync_timestamp         │")
    print("   └─────────────────────────────────────────────────────────┘")
    print()

    print("3. 遅延の構成要素:")
    print("   RTT = ネットワーク遅延 + 処理遅延 + シミュレーション遅延")
    print("   ・ネットワーク遅延: ZeroMQ + TCP/IP stack (~1-5ms)")
    print("   ・処理遅延: Plant物理計算 + JSON処理 (~1-3ms)")
    print("   ・シミュレーション遅延: 設定値 (processing + response)")
    print()

def analyze_rtt_variation_causes():
    """RTT変動の原因分析"""

    print("4. RTT変動の原因:")
    print()

    causes = [
        {
            'name': 'OS スケジューラ干渉',
            'typical_impact': '5-20ms',
            'description': 'プロセス切り替えによる遅延変動',
            'mitigation': 'プロセス優先度設定、CPU親和性'
        },
        {
            'name': 'ZeroMQ メッセージキューイング',
            'typical_impact': '1-10ms',
            'description': 'PUB/SUBの非同期キューイング',
            'mitigation': 'HWM設定、バッファサイズ調整'
        },
        {
            'name': 'ガベージコレクション (Python)',
            'typical_impact': '10-100ms',
            'description': 'メモリ管理による一時停止',
            'mitigation': 'GC調整、メモリプール使用'
        },
        {
            'name': '同期タイムスタンプのずれ',
            'typical_impact': '0-5ms',
            'description': 'time.time()の精度・同期誤差',
            'mitigation': '高精度タイマー使用'
        },
        {
            'name': '遅延シミュレーションの変動',
            'typical_impact': '設定値±変動幅',
            'description': 'np.random.uniform()による意図的変動',
            'mitigation': '設定調整'
        }
    ]

    for i, cause in enumerate(causes, 1):
        print(f"   {i}. {cause['name']}")
        print(f"      影響: {cause['typical_impact']}")
        print(f"      説明: {cause['description']}")
        print(f"      対策: {cause['mitigation']}")
        print()

def create_rtt_simulation():
    """RTT変動シミュレーション"""

    print("5. RTT変動のシミュレーション:")

    # シミュレーションパラメータ
    duration = 30  # 秒
    dt = 0.01  # 10ms周期
    steps = int(duration / dt)

    time_points = np.linspace(0, duration, steps)

    # 各成分をシミュレート
    base_latency = 10.0  # ベース遅延 [ms]

    # 1. ネットワーク遅延 (安定)
    network_delay = np.random.normal(2.0, 0.5, steps)

    # 2. 処理遅延 (軽微な変動)
    processing_delay = np.random.normal(3.0, 1.0, steps)

    # 3. システム負荷による変動 (時々大きなスパイク)
    system_load = np.zeros(steps)
    for i in range(steps):
        if np.random.random() < 0.005:  # 0.5%の確率でスパイク
            system_load[i] = np.random.exponential(15.0)

    # 4. 同期ずれによる変動
    sync_drift = np.random.normal(0, 1.0, steps)

    # 5. 遅延シミュレーション (設定に応じた遅延)
    sim_delay_base = 8.0  # processing(5) + response(3)
    sim_delay_variation = np.random.uniform(-2.0, 2.0, steps)  # ±2ms変動
    simulated_delay = sim_delay_base + sim_delay_variation

    # 総RTT計算
    total_rtt = (base_latency + network_delay + processing_delay +
                system_load + sync_drift + simulated_delay)

    # 負の値を0にクリップ
    total_rtt = np.maximum(total_rtt, 0)

    # プロット作成
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))

    # 1. 総RTT時系列
    ax1.plot(time_points, total_rtt, 'b-', alpha=0.7, linewidth=1)
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('RTT (ms)')
    ax1.set_title('Total RTT Time Series')
    ax1.grid(True, alpha=0.3)

    # 2. RTTヒストグラム
    ax2.hist(total_rtt, bins=50, alpha=0.7, edgecolor='black')
    ax2.axvline(np.mean(total_rtt), color='red', linestyle='--',
                label=f'Mean: {np.mean(total_rtt):.1f}ms')
    ax2.set_xlabel('RTT (ms)')
    ax2.set_ylabel('Frequency')
    ax2.set_title('RTT Distribution')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 3. 成分分解
    ax3.plot(time_points[:1000], network_delay[:1000], label='Network')
    ax3.plot(time_points[:1000], processing_delay[:1000], label='Processing')
    ax3.plot(time_points[:1000], system_load[:1000], label='System Load')
    ax3.plot(time_points[:1000], simulated_delay[:1000], label='Simulated')
    ax3.set_xlabel('Time (s)')
    ax3.set_ylabel('Delay (ms)')
    ax3.set_title('RTT Components (First 10s)')
    ax3.legend()
    ax3.grid(True, alpha=0.3)

    # 4. 移動平均とスパイク
    window = 100
    moving_avg = np.convolve(total_rtt, np.ones(window)/window, mode='valid')
    ax4.plot(time_points[window-1:], moving_avg, 'r-', label='Moving Average', linewidth=2)
    ax4.plot(time_points, total_rtt, 'b-', alpha=0.3, label='Raw RTT')
    ax4.set_xlabel('Time (s)')
    ax4.set_ylabel('RTT (ms)')
    ax4.set_title('RTT with Moving Average')
    ax4.legend()
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('rtt_variation_analysis.png', dpi=150, bbox_inches='tight')
    print(f"   RTTシミュレーションを 'rtt_variation_analysis.png' に保存しました")

    # 統計情報
    print(f"   シミュレーション統計:")
    print(f"   - 平均RTT: {np.mean(total_rtt):.1f}ms")
    print(f"   - 標準偏差: {np.std(total_rtt):.1f}ms")
    print(f"   - 最小/最大: {np.min(total_rtt):.1f}/{np.max(total_rtt):.1f}ms")
    print(f"   - 99%ile: {np.percentile(total_rtt, 99):.1f}ms")
    print()

def analyze_delay_configuration():
    """遅延設定の影響分析"""

    print("6. 遅延設定と実測RTTの関係:")
    print()

    # 理論的な遅延構成
    configs = [
        {'name': '遅延なし', 'proc': 0, 'resp': 0, 'var': 0, 'expected_rtt': '10-15ms'},
        {'name': '軽微遅延', 'proc': 5, 'resp': 3, 'var': 2, 'expected_rtt': '18-22ms'},
        {'name': '中程度遅延', 'proc': 10, 'resp': 5, 'var': 3, 'expected_rtt': '25-30ms'},
        {'name': '高遅延', 'proc': 20, 'resp': 10, 'var': 5, 'expected_rtt': '40-50ms'},
    ]

    for config in configs:
        total_sim_delay = config['proc'] + config['resp']
        base_overhead = 10  # システム基本オーバーヘッド

        print(f"   {config['name']}:")
        print(f"     設定: processing={config['proc']}ms, response={config['resp']}ms, variation=±{config['var']}ms")
        print(f"     計算: {base_overhead}ms(base) + {total_sim_delay}ms(sim) ± {config['var']}ms(var)")
        print(f"     期待RTT: {config['expected_rtt']}")
        print()

if __name__ == "__main__":
    analyze_communication_structure()
    analyze_rtt_variation_causes()
    create_rtt_simulation()
    analyze_delay_configuration()

    print("=== 結論 ===")
    print("RTTの振れ幅の主要因:")
    print("1. システムレベルの変動 (OS、ガベージコレクション)")
    print("2. ZeroMQの非同期キューイング")
    print("3. 意図的な遅延シミュレーション変動")
    print("4. 同期タイムスタンプの微小誤差")
    print()
    print("遅延設定は確実にRTTに反映されますが、")
    print("システム固有のオーバーヘッドが常に存在します。")