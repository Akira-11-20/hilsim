#!/usr/bin/env python3
"""
遅延設定の影響分析スクリプト

異なる遅延設定でのRTT変化を測定・比較し、通信構造の理解を深める
"""

import subprocess
import time
import json
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Dict, Tuple
import re

def run_delay_test(processing_delay: float, response_delay: float,
                  delay_variation: float, duration: int = 15) -> Dict:
    """
    指定した遅延設定でテストを実行し、RTT統計を取得

    Args:
        processing_delay: 処理遅延[ms]
        response_delay: 応答遅延[ms]
        delay_variation: 遅延変動[ms]
        duration: テスト時間[秒]

    Returns:
        RTT統計辞書
    """
    print(f"Testing: proc={processing_delay}ms, resp={response_delay}ms, var={delay_variation}ms")

    # まず遅延設定を更新
    modify_delay_settings(processing_delay, response_delay, delay_variation)

    # 統合テスト実行
    process = subprocess.Popen(
        ["uv", "run", "python", "test_communication_integration.py",
         "--duration", str(duration), "--delay"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout, stderr = process.communicate()

    # RTT統計を抽出
    rtt_stats = extract_rtt_stats(stderr)
    rtt_stats['config'] = {
        'processing_delay': processing_delay,
        'response_delay': response_delay,
        'delay_variation': delay_variation
    }

    return rtt_stats

def modify_delay_settings(proc_delay: float, resp_delay: float, var_delay: float):
    """Plant通信テストファイルの遅延設定を動的に変更"""

    file_path = "plant/app/test_plant_communication.py"

    # ファイルを読み込み
    with open(file_path, 'r') as f:
        content = f.read()

    # 遅延設定部分を置換
    new_settings = f"""            communicator.configure_delay_simulation(
                enable=True,
                processing_delay_ms={proc_delay},   # {proc_delay}ms処理遅延
                response_delay_ms={resp_delay},     # {resp_delay}ms応答遅延
                delay_variation_ms={var_delay}     # ±{var_delay}ms変動
            )"""

    # 正規表現で既存の設定を置換
    pattern = r'communicator\.configure_delay_simulation\(\s*enable=True,\s*processing_delay_ms=[\d.]+,.*?delay_variation_ms=[\d.]+\s*\)'
    content = re.sub(pattern, new_settings.strip(), content, flags=re.DOTALL)

    # ファイルに書き戻し
    with open(file_path, 'w') as f:
        f.write(content)

def extract_rtt_stats(stderr_text: str) -> Dict:
    """テスト出力からRTT統計を抽出"""

    stats = {
        'min_rtt': None,
        'max_rtt': None,
        'avg_rtt': None,
        'count': None,
        'successful': False
    }

    lines = stderr_text.split('\n')

    for line in lines:
        if "Min:" in line and "ms" in line:
            try:
                stats['min_rtt'] = float(re.search(r'Min: ([\d.]+)ms', line).group(1))
            except:
                pass

        elif "Max:" in line and "ms" in line:
            try:
                stats['max_rtt'] = float(re.search(r'Max: ([\d.]+)ms', line).group(1))
            except:
                pass

        elif "Avg:" in line and "ms" in line:
            try:
                stats['avg_rtt'] = float(re.search(r'Avg: ([\d.]+)ms', line).group(1))
            except:
                pass

        elif "Count:" in line:
            try:
                stats['count'] = int(re.search(r'Count: (\d+)', line).group(1))
            except:
                pass

        elif "RTT Measurement: PASSED" in line:
            stats['successful'] = True

    return stats

def analyze_delay_impacts():
    """複数の遅延設定でテストし、影響を分析"""

    print("=== 遅延設定の影響分析 ===")

    # テスト設定の組み合わせ
    test_configs = [
        # (processing_delay, response_delay, delay_variation)
        (0.0, 0.0, 0.0),      # ベースライン（遅延なし）
        (5.0, 3.0, 1.0),      # 軽微な遅延
        (10.0, 5.0, 2.0),     # 中程度の遅延
        (20.0, 10.0, 5.0),    # 高い遅延
        (50.0, 20.0, 10.0),   # 非常に高い遅延
    ]

    results = []

    for i, (proc, resp, var) in enumerate(test_configs):
        print(f"\n--- Test {i+1}/{len(test_configs)} ---")

        try:
            stats = run_delay_test(proc, resp, var, duration=12)
            results.append(stats)

            if stats['successful'] and stats['avg_rtt'] is not None:
                total_expected = proc + resp  # 期待される最小遅延
                print(f"✅ Expected RTT: ~{total_expected:.1f}ms, Measured: {stats['avg_rtt']:.1f}ms")
            else:
                print("❌ Test failed or no RTT data")

        except Exception as e:
            print(f"❌ Error: {e}")
            results.append({'successful': False, 'error': str(e)})

        # テスト間の待機
        time.sleep(2)

    # 結果を可視化
    plot_delay_analysis(results)

    return results

def plot_delay_analysis(results: List[Dict]):
    """遅延分析結果をプロット"""

    # 成功したテスト結果のみを抽出
    successful_results = [r for r in results if r.get('successful', False) and r.get('avg_rtt') is not None]

    if len(successful_results) < 2:
        print("十分なデータが取得できませんでした")
        return

    # データ準備
    expected_delays = []
    measured_rtts = []
    min_rtts = []
    max_rtts = []
    labels = []

    for result in successful_results:
        config = result['config']
        expected = config['processing_delay'] + config['response_delay']
        expected_delays.append(expected)
        measured_rtts.append(result['avg_rtt'])
        min_rtts.append(result['min_rtt'])
        max_rtts.append(result['max_rtt'])
        labels.append(f"{config['processing_delay']:.0f}+{config['response_delay']:.0f}ms")

    # プロット作成
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    # 期待遅延 vs 測定RTT
    ax1.plot(expected_delays, measured_rtts, 'ro-', label='Average RTT', markersize=8)
    ax1.plot(expected_delays, min_rtts, 'g^-', label='Min RTT', markersize=6)
    ax1.plot(expected_delays, max_rtts, 'bv-', label='Max RTT', markersize=6)
    ax1.plot([0, max(expected_delays)], [0, max(expected_delays)], 'k--', alpha=0.5, label='Perfect correlation')

    ax1.set_xlabel('Expected Delay (ms)')
    ax1.set_ylabel('Measured RTT (ms)')
    ax1.set_title('Expected vs Measured RTT')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 設定別RTT分布
    x_positions = range(len(successful_results))
    ax2.bar(x_positions, measured_rtts, alpha=0.7, color='skyblue')
    ax2.errorbar(x_positions, measured_rtts,
                yerr=[np.array(measured_rtts) - np.array(min_rtts),
                      np.array(max_rtts) - np.array(measured_rtts)],
                fmt='none', color='red', capsize=5)

    ax2.set_xlabel('Configuration')
    ax2.set_ylabel('RTT (ms)')
    ax2.set_title('RTT by Configuration')
    ax2.set_xticks(x_positions)
    ax2.set_xticklabels(labels, rotation=45)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('delay_impact_analysis.png', dpi=150, bbox_inches='tight')
    print(f"\n分析結果を 'delay_impact_analysis.png' に保存しました")

    # 数値分析
    print(f"\n=== 数値分析結果 ===")
    for i, result in enumerate(successful_results):
        config = result['config']
        expected = config['processing_delay'] + config['response_delay']
        measured = result['avg_rtt']
        overhead = measured - expected

        print(f"設定 {i+1}: 期待{expected:.1f}ms → 測定{measured:.1f}ms (オーバーヘッド: {overhead:.1f}ms)")

if __name__ == "__main__":
    analyze_delay_impacts()