#!/usr/bin/env python3
"""
Enhanced ZMQ Server with Configurable Delay and Jitter Simulation - 詳細注釈版

Features:
- Configurable processing delay (処理遅延制御)
- Configurable network simulation delay (ネットワーク遅延シミュレーション)
- Jitter simulation (random variation) (ジッター制御)
- Real-time delay statistics (リアルタイム統計)
- Multiple delay distribution types (複数の分布タイプ)
"""

import zmq
import time
import json
import sys
import os
import numpy as np
import threading
from queue import Queue
import argparse

class DelaySimulationServer:
    """Enhanced server with delay and jitter simulation capabilities

    遅延・ジッター制御機能付きサーバー：
    HILSシステムで現実的なネットワーク条件をシミュレートするため、
    アプリケーションレベルで精密な遅延制御を実現
    """

    def __init__(self, port=5555):
        """初期化

        Args:
            port: ZeroMQ REPソケットのポート番号
        """
        self.port = port
        self.context = zmq.Context()                    # ZeroMQコンテキスト作成
        self.socket = self.context.socket(zmq.REP)      # REQ-REPパターンのサーバーソケット

        # ===== 遅延設定パラメータ =====
        self.base_delay_ms = 0.0        # 基本処理遅延[ms] (サーバー処理時間をシミュレート)
        self.network_delay_ms = 0.0     # ネットワーク遅延[ms] (ネットワーク伝搬遅延をシミュレート)
        self.jitter_ms = 0.0           # ジッター振幅[ms] (遅延の変動をシミュレート)
        self.jitter_type = "uniform"   # ジッター分布タイプ (uniform/gaussian/exponential)

        # ===== 統計情報管理 =====
        self.message_count = 0          # 処理メッセージ数
        self.total_delay_applied = 0.0  # 累積適用遅延時間
        self.delay_history = []         # 遅延履歴（最新1000件）

        # ===== 制御フラグ =====
        self.running = True             # サーバー実行状態
        self.stats_interval = 100       # 統計表示間隔（100メッセージごと）

    def configure_delay(self, base_delay_ms=0.0, network_delay_ms=0.0,
                       jitter_ms=0.0, jitter_type="uniform"):
        """遅延シミュレーションパラメータ設定

        Args:
            base_delay_ms: 基本処理遅延[ms] - サーバー側の計算処理時間をシミュレート
            network_delay_ms: ネットワーク遅延[ms] - 通信経路の伝搬遅延をシミュレート
            jitter_ms: ジッター振幅[ms] - 遅延の変動幅（ネットワーク不安定性をシミュレート）
            jitter_type: ジッター分布タイプ
                - "uniform": 一様分布 [-jitter_ms, +jitter_ms]
                - "gaussian": ガウス分布 (σ = jitter_ms/3)
                - "exponential": 指数分布 [0, jitter_ms]

        実際のHILSシステムでの使用例:
        - base_delay_ms=10: 制御計算に10ms必要
        - network_delay_ms=20: ネットワーク経由で20ms必要
        - jitter_ms=5: ±5msの変動
        """
        self.base_delay_ms = base_delay_ms
        self.network_delay_ms = network_delay_ms
        self.jitter_ms = jitter_ms
        self.jitter_type = jitter_type

        total_fixed_delay = base_delay_ms + network_delay_ms

        print(f"Delay Configuration:")
        print(f"  Base Processing: {base_delay_ms:.1f}ms")      # サーバー処理遅延
        print(f"  Network Simulation: {network_delay_ms:.1f}ms") # ネットワーク遅延
        print(f"  Jitter: {jitter_ms:.1f}ms ({jitter_type})")    # ジッター設定
        print(f"  Total Fixed: {total_fixed_delay:.1f}ms")       # 固定遅延合計

    def generate_jitter(self):
        """設定に基づいてジッター値を生成

        Returns:
            float: 生成されたジッター値[ms]

        ジッタータイプ別の実装:
        - uniform: 均等に分散した変動（最も一般的）
        - gaussian: 正規分布変動（自然なネットワーク変動に近い）
        - exponential: 非対称変動（時々大きく遅延する状況）
        """
        if self.jitter_ms <= 0:
            return 0.0

        if self.jitter_type == "uniform":
            # 一様分布: -jitter_ms から +jitter_ms の範囲で均等に分布
            return np.random.uniform(-self.jitter_ms, self.jitter_ms)

        elif self.jitter_type == "gaussian":
            # ガウス分布: 平均0、標準偏差=jitter_ms/3 (99.7%が±jitter_ms内)
            return np.random.normal(0, self.jitter_ms / 3.0)  # 3σ = jitter_ms

        elif self.jitter_type == "exponential":
            # 指数分布: 0から始まり、稀に大きな値（バースト遅延をシミュレート）
            # 平均 = jitter_ms/2, 最大値 = jitter_ms にクリップ
            return np.clip(np.random.exponential(self.jitter_ms / 2.0), 0, self.jitter_ms)
        else:
            return 0.0

    def apply_delay(self, delay_ms):
        """高精度遅延適用

        Args:
            delay_ms: 適用する遅延時間[ms]

        実装詳細:
        - time.sleep()を使用した単純だが効果的な遅延
        - ミリ秒→秒変換 (sleep()は秒単位)
        - OSスケジューラーにより±1ms程度の誤差あり
        """
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)  # ms → s変換してsleep実行

    def process_message(self, message):
        """メッセージ処理（遅延制御込み）

        これが遅延シミュレーションのメインロジック：
        1. ジッター計算
        2. 基本処理遅延適用
        3. 応答データ準備
        4. 残りのネットワーク遅延適用
        5. 応答返却

        Args:
            message: 受信したメッセージ文字列

        Returns:
            str: 遅延情報を含む応答JSON文字列
        """
        # ===== 処理開始時刻記録（統計用）=====
        start_time = time.perf_counter()

        # ===== 受信メッセージ解析 =====
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            # JSONでない場合はエコーメッセージとして処理
            data = {"echo": message}

        # ===== 総遅延時間計算 =====
        jitter = self.generate_jitter()                    # 現在のサンプル用ジッター生成
        total_delay_ms = self.base_delay_ms + self.network_delay_ms + jitter

        # ===== 第1段階: 基本処理遅延適用 ⭐ =====
        # サーバー側の計算処理時間をシミュレート
        # （制御アルゴリズム実行、データベースアクセス等）
        if self.base_delay_ms > 0:
            self.apply_delay(self.base_delay_ms)    # ← 実際の遅延実行箇所1

        # ===== 応答データ準備 =====
        # クライアントが分析で使用する詳細情報を付加
        data.update({
            'server_timestamp': time.time(),                                        # サーバー時刻
            'message_id': self.message_count,                                       # メッセージ通番
            'applied_delay_ms': total_delay_ms,                                     # 適用総遅延 ⭐
            'base_delay_ms': self.base_delay_ms,                                    # 基本遅延成分
            'network_delay_ms': self.network_delay_ms,                              # ネットワーク遅延成分
            'jitter_ms': jitter,                                                    # 今回適用ジッター値 ⭐
            'server_processing_time_ms': (time.perf_counter() - start_time) * 1000 # 実処理時間
        })

        # JSON応答文字列作成
        response = json.dumps(data)

        # ===== 第2段階: 残りネットワーク遅延適用 ⭐ =====
        # 既に base_delay を適用済みなので、残りの遅延のみ適用
        # この分割アプローチにより、処理と通信の遅延を分離してシミュレート
        if self.network_delay_ms + jitter > self.base_delay_ms:
            remaining_delay = (self.network_delay_ms + jitter) - self.base_delay_ms
            if remaining_delay > 0:
                self.apply_delay(remaining_delay)   # ← 実際の遅延実行箇所2

        # ===== 統計情報更新 =====
        self.delay_history.append(total_delay_ms)
        self.total_delay_applied += total_delay_ms

        # メモリ管理：履歴が長くなりすぎた場合は古いデータを削除
        if len(self.delay_history) > 1000:
            self.delay_history = self.delay_history[-500:]  # 最新500件を保持

        return response

    def print_statistics(self):
        """遅延統計情報表示

        最新の統計情報をコンソール出力：
        - 平均遅延とばらつき
        - 最小・最大遅延
        - 処理メッセージ数
        """
        if len(self.delay_history) > 0:
            # 最新100メッセージ分の統計を計算
            recent_delays = self.delay_history[-self.stats_interval:]
            avg_delay = np.mean(recent_delays)
            std_delay = np.std(recent_delays)
            min_delay = np.min(recent_delays)
            max_delay = np.max(recent_delays)

            print(f"Messages: {self.message_count}, "
                  f"Recent Delay: {avg_delay:.2f}±{std_delay:.2f}ms "
                  f"[{min_delay:.2f}-{max_delay:.2f}ms]")

    def run_server(self):
        """メインサーバーループ

        ZeroMQ REQ-REPパターンでクライアントからのメッセージを処理：
        1. メッセージ受信
        2. 遅延制御付き処理実行
        3. 応答送信
        4. 統計情報更新・表示
        """
        # ===== サーバーソケット起動 =====
        self.socket.bind(f"tcp://*:{self.port}")
        print(f"Enhanced Echo Server with Delay Simulation started on port {self.port}")
        print("Ready to receive messages...")

        try:
            while self.running:
                # ===== メッセージ受信 =====
                # ZeroMQ REPソケット：1つのメッセージを受信するまでブロック
                message = self.socket.recv_string()

                # ===== 遅延制御付きメッセージ処理 ⭐ =====
                response = self.process_message(message)

                # ===== 応答送信 =====
                # 遅延適用後に応答を送信（クライアントのRTT測定終了）
                self.socket.send_string(response)

                # ===== メッセージカウンタ・統計更新 =====
                self.message_count += 1

                # 定期的な統計表示（100メッセージごと）
                if self.message_count % self.stats_interval == 0:
                    self.print_statistics()

        except KeyboardInterrupt:
            print("Server stopping...")
        finally:
            # ===== リソースクリーンアップ =====
            self.socket.close()
            self.context.term()
            print("Server stopped")

def main():
    """メイン実行関数

    コマンドライン引数と環境変数から設定を読み込み、
    遅延シミュレーションサーバーを起動
    """
    # ===== コマンドライン引数解析 =====
    parser = argparse.ArgumentParser(description='Enhanced ZMQ Server with Delay Simulation')
    parser.add_argument('--port', type=int, default=5555, help='Server port')
    parser.add_argument('--base-delay', type=float, default=0.0, help='Base processing delay [ms]')
    parser.add_argument('--network-delay', type=float, default=0.0, help='Network delay [ms]')
    parser.add_argument('--jitter', type=float, default=0.0, help='Jitter amplitude [ms]')
    parser.add_argument('--jitter-type', choices=['uniform', 'gaussian', 'exponential'],
                       default='uniform', help='Jitter distribution type')

    args = parser.parse_args()

    # ===== サーバーインスタンス作成・基本設定 =====
    server = DelaySimulationServer(port=args.port)
    server.configure_delay(
        base_delay_ms=args.base_delay,
        network_delay_ms=args.network_delay,
        jitter_ms=args.jitter,
        jitter_type=args.jitter_type
    )

    # ===== 環境変数による設定オーバーライド（Docker使用時）=====
    # Docker Composeから環境変数で設定値を注入可能
    if 'DELAY_BASE_MS' in os.environ:
        args.base_delay = float(os.environ['DELAY_BASE_MS'])
    if 'DELAY_NETWORK_MS' in os.environ:
        args.network_delay = float(os.environ['DELAY_NETWORK_MS'])
    if 'DELAY_JITTER_MS' in os.environ:
        args.jitter = float(os.environ['DELAY_JITTER_MS'])
    if 'DELAY_JITTER_TYPE' in os.environ:
        args.jitter_type = os.environ['DELAY_JITTER_TYPE']

    # 環境変数での再設定
    server.configure_delay(
        base_delay_ms=args.base_delay,
        network_delay_ms=args.network_delay,
        jitter_ms=args.jitter,
        jitter_type=args.jitter_type
    )

    # ===== サーバー実行 =====
    server.run_server()

if __name__ == "__main__":
    main()

"""
=== 使用例 ===

# 基本使用
python delay_server.py --base-delay 10 --network-delay 20 --jitter 5

# Docker環境変数使用
DELAY_BASE_MS=10.0 DELAY_NETWORK_MS=20.0 DELAY_JITTER_MS=5.0 python delay_server.py

=== 遅延制御の流れ ===

1. メッセージ受信
2. ジッター値計算（例：+3ms）
3. base_delay適用（10ms sleep）
4. 応答データ準備（~0.5ms）
5. remaining_delay適用（13ms sleep）
6. 応答送信

総遅延：10 + 0.5 + 13 = 23.5ms
報告値：10 + 20 + 3 = 33ms
差分：応答準備時間とsleep精度による誤差

=== HILSシステムでの活用 ===

このサーバーをPlant側で使用することで：
- 現実的なセンサー応答遅延をシミュレート
- ネットワーク不安定性（ジッター）を再現
- 制御系の遅延耐性をテスト
"""