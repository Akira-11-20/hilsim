#!/usr/bin/env python3
"""
Enhanced ZMQ Client for Delay and Jitter Testing - 詳細注釈版

Features:
- Comprehensive delay measurement
- Jitter analysis
- Real-time statistics
- CSV output for analysis
- Configurable test parameters
"""

import zmq
import time
import json
import numpy as np
import os
import sys
import csv
import argparse
from datetime import datetime

class EnhancedCommunicationTester:
    """Enhanced client for comprehensive communication testing

    高機能通信テスター：遅延制御サーバーとの組み合わせで
    詳細なRTT測定・ジッター分析・統計データ取得を行う
    """

    def __init__(self, server_endpoint="tcp://server:5555"):
        """初期化

        Args:
            server_endpoint: サーバー接続先（例：tcp://localhost:5561）
        """
        self.server_endpoint = server_endpoint
        self.context = zmq.Context()           # ZeroMQコンテキスト作成
        self.socket = self.context.socket(zmq.REQ)  # REQ-REPパターンのクライアントソケット

        # ===== テスト設定 =====
        self.samples = 500          # 測定サンプル数（デフォルト500回）
        self.warmup_samples = 10    # ウォームアップ回数（安定化のため）
        self.timeout_ms = 5000      # 受信タイムアウト（5秒）

        # ===== データ収集用 =====
        self.measurements = []      # 全測定データを格納するリスト
        self.test_start_time = None # テスト開始時刻（相対時間計算用）

        # ===== ZeroMQソケット設定 =====
        self.socket.setsockopt(zmq.LINGER, 0)  # 終了時の待機時間なし
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)  # 受信タイムアウト設定

    def configure_test(self, samples=500, warmup=10, timeout_ms=5000):
        """テストパラメータ設定

        実行時に測定回数やタイムアウトを変更可能
        """
        self.samples = samples
        self.warmup_samples = warmup
        self.timeout_ms = timeout_ms
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)

    def connect_and_warmup(self):
        """サーバー接続とウォームアップ実行

        ウォームアップの目的：
        - TCP接続の確立
        - ZeroMQソケットの初期化
        - サーバー側の準備完了確認
        - JIT等による初回実行コストの排除
        """
        print(f"Connecting to {self.server_endpoint}")
        self.socket.connect(self.server_endpoint)  # サーバーに接続

        print("Performing warmup...")
        for i in range(self.warmup_samples):
            try:
                # ウォームアップメッセージ送信
                self.socket.send_string(json.dumps({"type": "warmup", "seq": i}))
                self.socket.recv_string()  # 応答受信（内容は無視）
            except zmq.Again:
                # タイムアウトが発生してもウォームアップは続行
                print(f"Warmup timeout on sample {i}")

        print("Warmup completed")

    def run_measurement_test(self, test_name="enhanced_test"):
        """メイン測定実行

        各サンプルで以下を実行：
        1. 高精度タイマーで送信時刻記録
        2. メッセージ送信
        3. 応答受信・受信時刻記録
        4. RTT計算
        5. サーバー側情報抽出
        6. 全データを measurements[] に保存
        """
        print(f"\nStarting measurement test: {test_name}")
        print(f"Samples: {self.samples}")

        self.test_start_time = time.time()  # テスト開始時刻記録
        self.measurements = []              # 測定データリセット

        for i in range(self.samples):
            # ===== 高精度タイミング測定開始 =====
            # time.perf_counter()：単調増加クロック（最高精度）
            client_send_time = time.perf_counter()

            # ===== 送信メッセージ構築 =====
            message = {
                "type": "ping",                        # メッセージタイプ
                "sequence": i,                         # シーケンス番号
                "client_send_time": client_send_time,  # クライアント送信時刻（高精度）
                "client_timestamp": time.time()        # 壁時計時刻（サーバーとの比較用）
            }

            try:
                # ===== メッセージ送信 =====
                self.socket.send_string(json.dumps(message))

                # ===== 応答受信 =====
                response_str = self.socket.recv_string()
                client_recv_time = time.perf_counter()  # 受信時刻記録（即座に）

                # ===== 応答パース =====
                response = json.loads(response_str)

                # ===== クライアント側RTT計算 =====
                client_rtt_ms = (client_recv_time - client_send_time) * 1000.0

                # ===== サーバー側情報抽出 =====
                # delay_server.pyから返される詳細情報を取得
                server_delay_ms = response.get('applied_delay_ms', 0.0)      # 適用された総遅延
                base_delay_ms = response.get('base_delay_ms', 0.0)           # 基本処理遅延
                network_delay_ms = response.get('network_delay_ms', 0.0)     # ネットワーク遅延
                jitter_ms = response.get('jitter_ms', 0.0)                   # 適用されたジッター
                server_processing_ms = response.get('server_processing_time_ms', 0.0)  # サーバー処理時間

                # ===== 測定データ構造体作成 =====
                measurement = {
                    'sequence': i,                          # サンプル番号
                    'client_rtt_ms': client_rtt_ms,         # クライアント測定RTT ⭐
                    'server_total_delay_ms': server_delay_ms, # サーバー報告総遅延 ⭐
                    'server_base_delay_ms': base_delay_ms,   # サーバー基本遅延
                    'server_network_delay_ms': network_delay_ms, # サーバーネットワーク遅延
                    'server_jitter_ms': jitter_ms,           # 適用ジッター値 ⭐
                    'server_processing_ms': server_processing_ms, # サーバー処理時間
                    'client_send_time': client_send_time,    # 送信時刻（生値）
                    'client_recv_time': client_recv_time,    # 受信時刻（生値）
                    'timestamp': time.time()                 # 測定時の壁時計時刻
                }

                # リストに追加（後でCSV出力・統計計算に使用）
                self.measurements.append(measurement)

                # ===== 進捗表示（100サンプルごと） =====
                if (i + 1) % 100 == 0:
                    # 最新100サンプルの平均・標準偏差を計算して表示
                    recent_rtts = [m['client_rtt_ms'] for m in self.measurements[-100:]]
                    recent_avg = np.mean(recent_rtts)
                    recent_std = np.std(recent_rtts)
                    print(f"Sample {i+1}/{self.samples}, Recent RTT: {recent_avg:.2f}±{recent_std:.2f}ms")

            except zmq.Again:
                # タイムアウトエラー：このサンプルはスキップして続行
                print(f"Timeout on sample {i}")
                continue

            except json.JSONDecodeError as e:
                # JSONパースエラー：サーバー応答が不正
                print(f"JSON decode error on sample {i}: {e}")
                continue

        print(f"Measurement completed: {len(self.measurements)}/{self.samples} successful")

    def analyze_results(self, test_name="enhanced_test"):
        """測定結果の統計分析

        収集した全測定データから包括的な統計情報を計算：
        - 基本統計（平均、標準偏差、最小・最大）
        - パーセンタイル（P95、P99）
        - サーバー側統計
        - ネットワークオーバーヘッド推定
        """
        if not self.measurements:
            print("No measurements to analyze")
            return None

        # ===== NumPy配列に変換（高速計算のため） =====
        client_rtts = np.array([m['client_rtt_ms'] for m in self.measurements])
        server_delays = np.array([m['server_total_delay_ms'] for m in self.measurements])
        server_jitters = np.array([m['server_jitter_ms'] for m in self.measurements])
        server_processing = np.array([m['server_processing_ms'] for m in self.measurements])

        # ===== 包括的統計情報計算 =====
        results = {
            'test_name': test_name,
            'sample_count': len(self.measurements),
            'timestamp': datetime.now().isoformat(),

            # ===== クライアント側RTT統計 =====
            'client_rtt_avg_ms': float(np.mean(client_rtts)),      # 平均RTT
            'client_rtt_std_ms': float(np.std(client_rtts)),       # 標準偏差
            'client_rtt_min_ms': float(np.min(client_rtts)),       # 最小RTT
            'client_rtt_max_ms': float(np.max(client_rtts)),       # 最大RTT
            'client_rtt_median_ms': float(np.median(client_rtts)), # 中央値
            'client_rtt_p95_ms': float(np.percentile(client_rtts, 95)), # 95パーセンタイル
            'client_rtt_p99_ms': float(np.percentile(client_rtts, 99)), # 99パーセンタイル

            # ===== サーバー報告遅延統計 =====
            'server_delay_avg_ms': float(np.mean(server_delays)),
            'server_delay_std_ms': float(np.std(server_delays)),
            'server_delay_min_ms': float(np.min(server_delays)),
            'server_delay_max_ms': float(np.max(server_delays)),

            # ===== ジッター分析 =====
            'server_jitter_avg_ms': float(np.mean(server_jitters)),   # ジッター平均
            'server_jitter_std_ms': float(np.std(server_jitters)),    # ジッター標準偏差
            'server_jitter_range_ms': float(np.max(server_jitters) - np.min(server_jitters)), # ジッター範囲

            # ===== サーバー処理オーバーヘッド =====
            'server_processing_avg_ms': float(np.mean(server_processing)), # 処理時間平均
            'server_processing_max_ms': float(np.max(server_processing)),  # 処理時間最大

            # ===== ネットワークオーバーヘッド推定 =====
            # クライアントRTT - サーバー遅延 = 純粋なネットワーク遅延
            'estimated_network_overhead_ms': float(np.mean(client_rtts - server_delays))
        }

        return results

    def print_results(self, results):
        """結果を整形して表示

        統計結果を見やすい形式でコンソール出力
        """
        print(f"\n{'='*60}")
        print(f"COMMUNICATION TEST RESULTS: {results['test_name']}")
        print(f"{'='*60}")
        print(f"Samples: {results['sample_count']}")
        print(f"Test Time: {results['timestamp']}")
        print()

        print("CLIENT-SIDE RTT MEASUREMENTS:")
        print(f"  Average: {results['client_rtt_avg_ms']:.3f} ± {results['client_rtt_std_ms']:.3f}ms")
        print(f"  Range: {results['client_rtt_min_ms']:.3f} - {results['client_rtt_max_ms']:.3f}ms")
        print(f"  Median: {results['client_rtt_median_ms']:.3f}ms")
        print(f"  95th percentile: {results['client_rtt_p95_ms']:.3f}ms")
        print(f"  99th percentile: {results['client_rtt_p99_ms']:.3f}ms")
        print()

        print("SERVER-REPORTED DELAYS:")
        print(f"  Average: {results['server_delay_avg_ms']:.3f} ± {results['server_delay_std_ms']:.3f}ms")
        print(f"  Range: {results['server_delay_min_ms']:.3f} - {results['server_delay_max_ms']:.3f}ms")
        print()

        print("JITTER ANALYSIS:")
        print(f"  Average: {results['server_jitter_avg_ms']:.3f} ± {results['server_jitter_std_ms']:.3f}ms")
        print(f"  Range: {results['server_jitter_range_ms']:.3f}ms")
        print()

        print("SERVER PROCESSING:")
        print(f"  Average: {results['server_processing_avg_ms']:.4f}ms")
        print(f"  Maximum: {results['server_processing_max_ms']:.4f}ms")
        print()

        print("NETWORK ANALYSIS:")
        print(f"  Estimated Overhead: {results['estimated_network_overhead_ms']:.3f}ms")

    def save_results(self, results, detailed=True):
        """結果をファイル保存

        Args:
            results: 統計結果辞書
            detailed: True=詳細CSV出力も行う

        出力ファイル：
        - JSON: 統計サマリー（グラフ生成等で使用）
        - CSV: 全サンプルの生データ（時系列分析で使用）⭐
        """
        # ===== JSON統計サマリー保存 =====
        summary_file = f"/app/results_{results['test_name']}_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Summary saved to: {summary_file}")

        if detailed and self.measurements:
            # ===== CSV詳細データ保存 ⭐ =====
            csv_file = f"/app/results_{results['test_name']}_detailed.csv"
            with open(csv_file, 'w', newline='') as f:
                if self.measurements:
                    # measurements[0]のキーをCSVヘッダーとして使用
                    fieldnames = self.measurements[0].keys()
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()  # ヘッダー行書き込み
                    writer.writerows(self.measurements)  # 全データ書き込み
            print(f"Detailed data saved to: {csv_file}")

    def cleanup(self):
        """リソースクリーンアップ

        ZeroMQソケット・コンテキストの適切な終了処理
        """
        self.socket.close()    # ソケットクローズ
        self.context.term()    # コンテキスト終了

def main():
    """メイン実行関数

    コマンドライン引数・環境変数からテスト設定を取得し、
    測定→分析→結果出力の完全なフローを実行
    """
    # ===== コマンドライン引数解析 =====
    parser = argparse.ArgumentParser(description='Enhanced Communication Tester')
    parser.add_argument('--server', default='tcp://server:5555', help='Server endpoint')
    parser.add_argument('--samples', type=int, default=500, help='Number of samples')
    parser.add_argument('--warmup', type=int, default=10, help='Warmup samples')
    parser.add_argument('--timeout', type=int, default=5000, help='Timeout in ms')
    parser.add_argument('--test-name', default='enhanced_test', help='Test name')

    args = parser.parse_args()

    # ===== 環境変数オーバーライド（Docker使用時） =====
    server_endpoint = os.getenv('SERVER_ENDPOINT', args.server)
    samples = int(os.getenv('SAMPLES', args.samples))
    test_name = os.getenv('TEST_NAME', args.test_name)

    # ===== テスターインスタンス作成・設定 =====
    tester = EnhancedCommunicationTester(server_endpoint)
    tester.configure_test(samples=samples, warmup=args.warmup, timeout_ms=args.timeout)

    try:
        # ===== 完全なテストフロー実行 =====
        tester.connect_and_warmup()        # 1. 接続・ウォームアップ
        tester.run_measurement_test(test_name)  # 2. メイン測定実行

        # ===== 結果分析・出力 =====
        results = tester.analyze_results(test_name)  # 3. 統計分析
        if results:
            tester.print_results(results)            # 4. コンソール表示
            tester.save_results(results, detailed=True)  # 5. ファイル保存
            print(f"\n✅ Test {test_name} completed successfully")
        else:
            print(f"\n❌ Test {test_name} failed - no results")
            sys.exit(1)

    except Exception as e:
        print(f"Test error: {e}")
        sys.exit(1)

    finally:
        # 必ずリソースクリーンアップ
        tester.cleanup()

if __name__ == "__main__":
    main()