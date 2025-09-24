#!/usr/bin/env python3
"""
RTT監視スクリプト

通信テストを実行しながら、RTTの詳細な変化をリアルタイムで監視・記録する。
"""

import time
import subprocess
import threading
import queue
import matplotlib.pyplot as plt
import numpy as np
import sys
import json

def parse_rtt_from_log(log_line):
    """ログ行からRTT値を抽出"""
    if "RTT=" in log_line and "ms" in log_line:
        try:
            # "RTT=123.4ms" の形式からRTT値を抽出
            rtt_start = log_line.find("RTT=") + 4
            rtt_end = log_line.find("ms", rtt_start)
            rtt_str = log_line[rtt_start:rtt_end]
            return float(rtt_str)
        except:
            return None
    return None

def monitor_rtt_realtime():
    """リアルタイムRTT監視"""
    print("Starting RTT monitoring...")

    # 統合テストを開始
    process = subprocess.Popen(
        ["uv", "run", "python", "test_communication_integration.py", "--duration", "30", "--verbose"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    rtts = []
    times = []
    start_time = time.time()

    print("Monitoring RTT changes...")
    print("Time(s)\tRTT(ms)\tStatus")
    print("-" * 40)

    try:
        for line in iter(process.stderr.readline, ''):
            if line.strip():
                current_time = time.time() - start_time
                rtt = parse_rtt_from_log(line)

                if rtt is not None:
                    rtts.append(rtt)
                    times.append(current_time)

                    # リアルタイム表示（10回に1回）
                    if len(rtts) % 10 == 0:
                        print(f"{current_time:.1f}\t{rtt:.1f}\t{'Normal' if rtt < 100 else 'High'}")

                # プロセス終了チェック
                if process.poll() is not None:
                    break

    except KeyboardInterrupt:
        print("\nMonitoring interrupted")
        process.terminate()

    # プロセス終了待ち
    process.wait()

    if len(rtts) == 0:
        print("No RTT data collected")
        return

    # 統計表示
    print(f"\n=== RTT Statistics ===")
    print(f"Samples collected: {len(rtts)}")
    print(f"Time range: {times[-1]:.1f} seconds")
    print(f"RTT range: {min(rtts):.1f} - {max(rtts):.1f} ms")
    print(f"Average RTT: {np.mean(rtts):.1f} ms")
    print(f"RTT std dev: {np.std(rtts):.1f} ms")

    # RTT変化の傾向分析
    if len(rtts) > 10:
        first_10 = np.mean(rtts[:10])
        last_10 = np.mean(rtts[-10:])
        trend = "increasing" if last_10 > first_10 else "decreasing"
        print(f"RTT trend: {trend} ({first_10:.1f} -> {last_10:.1f} ms)")

    # 簡単なプロット作成
    try:
        plt.figure(figsize=(12, 6))

        # RTT時系列プロット
        plt.subplot(1, 2, 1)
        plt.plot(times, rtts, 'b.-', alpha=0.7, markersize=2)
        plt.xlabel('Time (s)')
        plt.ylabel('RTT (ms)')
        plt.title('RTT vs Time')
        plt.grid(True, alpha=0.3)

        # RTTヒストグラム
        plt.subplot(1, 2, 2)
        plt.hist(rtts, bins=20, alpha=0.7, edgecolor='black')
        plt.xlabel('RTT (ms)')
        plt.ylabel('Frequency')
        plt.title('RTT Distribution')
        plt.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig('rtt_analysis.png', dpi=150, bbox_inches='tight')
        print(f"\nRTT analysis plot saved as 'rtt_analysis.png'")

    except ImportError:
        print("Matplotlib not available, skipping plot")
    except Exception as e:
        print(f"Plot generation failed: {e}")

    # CSVデータ保存
    try:
        with open('rtt_data.csv', 'w') as f:
            f.write('time_s,rtt_ms\n')
            for t, r in zip(times, rtts):
                f.write(f'{t:.3f},{r:.1f}\n')
        print(f"RTT data saved as 'rtt_data.csv'")
    except Exception as e:
        print(f"Data save failed: {e}")

if __name__ == "__main__":
    monitor_rtt_realtime()