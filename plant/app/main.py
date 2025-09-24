#!/usr/bin/env python3
"""
Plant シミュレーターメインファイル（新アーキテクチャ版）

参考構造に基づくUDPサーバー実装。
物理シミュレーション（高度制御対象）を実行し、
Numeric側からのUDPリクエストに状態データで応答。

主要機能：
- SimpleAltitudePlant: 1次元高度物理モデル
- UDP Echo Server: リクエスト・レスポンス通信
- RTT測定・統計
- ログ記録・分析
"""

import socket
import yaml
import numpy as np
import os
import sys
import time
import csv
import logging
from typing import Dict, List, Tuple, Optional

# 新プロトコルをインポート
sys.path.append('/app')
from shared.protocol import ProtocolHandler, RequestPacket, ResponsePacket, create_response_packet

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SimpleAltitudePlant:
    """
    シンプルな高度植物モデル（質点の1次元運動）- 動作確認済みモデル

    ニュートンの運動方程式に基づく基本的な物理シミュレーション：
    F = ma → a = (F_thrust - mg) / m

    状態変数：
    - position: 高度[m]
    - velocity: 速度[m/s]
    - acceleration: 加速度[m/s²]
    """

    def __init__(self, mass: float = 1.0, gravity: float = 9.81):
        """
        物理モデル初期化

        Args:
            mass: 機体質量[kg]
            gravity: 重力加速度[m/s²]
        """
        self.mass = mass        # 機体質量
        self.gravity = gravity  # 重力加速度

        # ===== 状態変数 =====
        self.position = 0.0     # 高度[m]
        self.velocity = 0.0     # 速度[m/s]
        self.acceleration = 0.0 # 加速度[m/s²]

    def reset(self, initial_position: float = 0.0, initial_velocity: float = 0.0):
        """
        植物状態をリセット

        Args:
            initial_position: 初期高度[m]
            initial_velocity: 初期速度[m/s]
        """
        self.position = initial_position
        self.velocity = initial_velocity
        self.acceleration = 0.0

    def update(self, thrust: float, dt: float) -> Tuple[float, float, float]:
        """
        物理モデルの時間更新

        Args:
            thrust: 推力[N]（上向き正）
            dt: 時間ステップ[s]

        Returns:
            (測定高度, 測定速度, 加速度) - センサーノイズ付き
        """
        # ===== 力の計算: F_net = F_thrust - mg =====
        net_force = thrust - self.mass * self.gravity

        # ===== 加速度計算: a = F_net / m =====
        self.acceleration = net_force / self.mass

        # ===== オイラー積分による状態更新 =====
        self.velocity += self.acceleration * dt    # v = v0 + a*dt
        self.position += self.velocity * dt        # x = x0 + v*dt

        # ===== センサーノイズを追加（現実的なシミュレーション）=====
        position_noise = np.random.normal(0, 0.005)  # 位置：0.5cm標準偏差
        velocity_noise = np.random.normal(0, 0.005)  # 速度：0.5cm/s標準偏差

        return (
            self.position + position_noise,    # 測定高度
            self.velocity + velocity_noise,    # 測定速度
            self.acceleration                  # 加速度（ノイズなし）
        )


class PlantServer:
    """
    Plant UDP サーバークラス（新アーキテクチャ版）

    参考構造に基づくUDPエコーサーバー実装。
    Numeric側からのリクエストを受信し、
    現在の物理シミュレーション状態を応答。

    主要機能：
    - UDP Echo Server（リクエスト・レスポンス）
    - 物理シミュレーション（SimpleAltitudePlant）
    - RTT測定・統計
    - ログ記録・分析
    """

    def __init__(self, config_file: str = "config.yaml"):
        """
        サーバー初期化

        Args:
            config_file: 設定ファイルパス（YAML形式）
        """
        self.load_config(config_file)       # 設定読み込み
        self.setup_simulation()             # 物理シミュレーション設定
        self.setup_logging()                # ログシステム設定
        self.setup_udp_server()             # UDPサーバー設定

        # ===== サーバー状態 =====
        self.current_thrust = [0.0, 0.0, 0.0]  # 現在の推力[N] [fx, fy, fz]
        self.request_count = 0             # リクエスト処理数
        self.start_time = time.time()      # サーバー開始時刻

    def load_config(self, config_file: str):
        """
        設定ファイル読み込み・環境変数による上書き

        Args:
            config_file: YAML設定ファイルパス
        """
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        # UDPサーバー設定
        self.host = os.getenv('PLANT_HOST', '0.0.0.0')  # バインドアドレス
        self.port = int(os.getenv('PLANT_PORT', 5005))  # UDPポート
        self.dt = float(os.getenv('STEP_DT', self.config['plant']['dt']))  # シミュレーション周期[s]

        # 新しい日付ベースログディレクトリ設定
        log_date_dir = os.getenv('LOG_DATE_DIR')
        log_description = os.getenv('LOG_DESCRIPTION', 'test')

        if log_date_dir:
            # 環境変数からのパス（Docker内）
            log_dir = f"/app/logs/{log_date_dir}"
        else:
            # フォールバック: 従来形式
            date_str = time.strftime('%Y-%m-%d')
            time_str = time.strftime('%H%M%S')
            log_dir = f"/app/logs/{date_str}/{time_str}_{log_description}"

        print(f"Plant log directory: {log_dir}")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = f"{log_dir}/plant_log.csv"

    def setup_udp_server(self):
        """
        UDPサーバーセットアップ
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, self.port))
        logger.info(f"Plant UDP server bound to {self.host}:{self.port}")

    def setup_simulation(self):
        """
        物理シミュレーションセットアップ

        設定ファイルから物理パラメータを読み込んで物理モデルを初期化
        """
        sim_config = self.config['simulation']
        mass = sim_config['mass']         # 機体質量[kg]
        gravity = abs(sim_config['gravity'])  # 重力加速度[m/s²]（正の値として使用）

        # 動作確認済みの物理モデルを使用
        self.plant = SimpleAltitudePlant(mass=mass, gravity=gravity)

        # 初期状態設定
        initial_position = float(sim_config['initial_position'])  # 初期高度[m]
        initial_velocity = float(sim_config['initial_velocity'])  # 初期速度[m/s]
        self.plant.reset(initial_position, initial_velocity)

        # シミュレーション時間初期化
        self.sim_time = 0.0
        self.step_count = 0

    def setup_logging(self):
        """
        ログシステムセットアップ

        CSV形式でのデータログを設定。物理状態とタイミング情報を記録。
        """
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self.log_fp = open(self.log_file, 'w', newline='')
        self.csv_writer = csv.writer(self.log_fp)

        # CSVヘッダー（新アーキテクチャ版）
        self.csv_writer.writerow(['seq', 'recv_time', 'send_time', 'rtt_ms',
                                 'fx', 'fy', 'fz', 'altitude', 'velocity', 'acceleration',
                                 'client_addr', 'packet_size'])

    def get_current_state(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
        """
        現在の物理状態を取得

        Returns:
            (position, velocity, acceleration) タプル
        """
        # センサーノイズを追加
        pos_noise = np.random.normal(0, 0.005)
        vel_noise = np.random.normal(0, 0.005)
        acc_noise = np.random.normal(0, 0.01)

        position = (0.0, 0.0, self.plant.position + pos_noise)
        velocity = (0.0, 0.0, self.plant.velocity + vel_noise)
        acceleration = (0.0, 0.0, self.plant.acceleration + acc_noise)

        return position, velocity, acceleration

    def process_request(self, data: bytes, addr: Tuple[str, int]) -> Optional[bytes]:
        """
        リクエストパケット処理

        Args:
            data: 受信データ
            addr: クライアントアドレス

        Returns:
            応答データ or None（エラー時）
        """
        # リクエストパケット解析
        request = ProtocolHandler.unpack_request(data)
        if not request:
            logger.warning(f"Invalid packet from {addr}")
            return None

        # 制御入力を物理シミュレーションに適用
        self.current_thrust = [request.fx, request.fy, request.fz]

        # 物理シミュレーション更新
        self.plant.update(request.fz, self.dt)

        # 現在の状態を取得
        position, velocity, acceleration = self.get_current_state()

        # 応答パケット生成
        response = create_response_packet(
            request.sequence_number, position, velocity, acceleration
        )

        # バイナリパケットにパック
        return ProtocolHandler.pack_response(response)

    def run(self):
        """
        UDP エコーサーバーメイン実行

        参考構造に基づくリクエスト・レスポンス方式。
        Numeric側からのUDPリクエストを受信し、
        現在の物理状態を応答として返す。

        実行フロー：
        1. UDPリクエスト受信待機
        2. リクエストパケット解析
        3. 制御入力適用・物理更新
        4. 状態データ応答
        5. ログ記録
        """
        logger.info(f"Plant UDP server started on {self.host}:{self.port}")
        logger.info(f"Physics simulation: dt={self.dt}s")

        # 物理シミュレーション初期化
        sim_config = self.config['simulation']
        initial_position = float(sim_config['initial_position'])
        initial_velocity = float(sim_config['initial_velocity'])
        self.plant.reset(initial_position, initial_velocity)

        try:
            while True:
                # ===== UDPリクエスト受信 =====
                data, addr = self.socket.recvfrom(1024)  # 最大1KB
                recv_time = time.time()

                # ===== リクエスト処理・応答生成 =====
                response_data = self.process_request(data, addr)

                if response_data:
                    # ===== レスポンス送信 =====
                    send_time = time.time()
                    self.socket.sendto(response_data, addr)
                    rtt_ms = (send_time - recv_time) * 1000

                    self.request_count += 1

                    # ===== ログ記録 =====
                    if self.csv_writer:
                        request = ProtocolHandler.unpack_request(data)
                        if request:
                            position, velocity, acceleration = self.get_current_state()
                            self.csv_writer.writerow([
                                request.sequence_number, recv_time, send_time, rtt_ms,
                                request.fx, request.fy, request.fz,
                                position[2], velocity[2], acceleration[2],  # Z軸のみ
                                f"{addr[0]}:{addr[1]}", len(data)
                            ])
                            self.log_fp.flush()

                    # 進捗表示（100リクエスト毎）
                    if self.request_count % 100 == 0:
                        uptime = time.time() - self.start_time
                        rate = self.request_count / uptime if uptime > 0 else 0
                        logger.info(f"Plant processed {self.request_count} requests, Rate: {rate:.1f} req/s, Alt: {self.plant.position:.2f}m")
                else:
                    logger.warning(f"Failed to process request from {addr}")

        except KeyboardInterrupt:
            logger.info("Plant server interrupted")
        except Exception as e:
            logger.error(f"Error in plant server: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """
        リソース解放・クリーンアップ
        """
        if hasattr(self, 'csv_writer') and self.csv_writer:
            self.log_fp.close()
        if hasattr(self, 'socket'):
            self.socket.close()

        # 統計表示
        uptime = time.time() - self.start_time
        rate = self.request_count / uptime if uptime > 0 else 0
        logger.info(f"Plant server stopped: {self.request_count} requests in {uptime:.1f}s ({rate:.1f} req/s)")


if __name__ == "__main__":
    """
    メインエントリポイント

    新アーキテクチャ版：UDP Echo Serverとして動作
    """
    server = PlantServer()  # サーバー初期化
    server.run()           # サーバー開始