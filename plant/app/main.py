#!/usr/bin/env python3
"""
Plant シミュレーターメインファイル

物理シミュレーション（高度制御対象）を実行し、
Numeric側との通信を通信モジュールに委譲。

主要機能：
- SimpleAltitudePlant: 1次元高度物理モデル
- 独立シミュレーションループ（固定周期実行）
- 通信モジュールとの連携
- ログ記録・分析
"""

import yaml
import numpy as np
import os
import sys
import time
import csv
import logging
from typing import Dict, List, Tuple

# 通信モジュールをインポート
from plant_communication import PlantCommunicationManager

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


class PlantSimulator:
    """
    Plantシミュレーターメインクラス

    物理シミュレーションを実行し、通信モジュールを通じて
    Numeric側とのデータ交換を行う。

    主要機能：
    - 独立したシミュレーションループ
    - 通信モジュールとの連携
    - ログ記録・分析
    - 設定管理
    """

    def __init__(self, config_file: str = "config.yaml"):
        """
        シミュレーター初期化

        Args:
            config_file: 設定ファイルパス（YAML形式）
        """
        self.load_config(config_file)       # 設定読み込み
        self.setup_communication()          # 通信システム設定
        self.setup_simulation()             # 物理シミュレーション設定
        self.setup_logging()                # ログシステム設定

        # ===== シミュレーション状態 =====
        self.current_thrust = 0.0      # 現在の推力[N]
        self.step_count = 0            # ステップカウンタ
        self.sim_time = 0.0            # シミュレーション時刻[s]
        self.max_steps = int(os.getenv('MAX_STEPS', 4000))  # 最大ステップ数

    def load_config(self, config_file: str):
        """
        設定ファイル読み込み・環境変数による上書き

        Args:
            config_file: YAML設定ファイルパス
        """
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        # 環境変数による設定上書き（Docker環境での動的設定用）
        self.bind_address = os.getenv('PLANT_BIND', self.config['plant']['bind_address'])
        self.dt = float(os.getenv('STEP_DT', self.config['plant']['dt']))  # シミュレーション周期[s]

        # タイムスタンプ付きログディレクトリ作成
        run_id = os.getenv('RUN_ID', time.strftime('%Y%m%d_%H%M%S'))
        log_dir = f"/app/logs/{run_id}"
        self.log_file = f"{log_dir}/plant_log.csv"

    def setup_communication(self):
        """
        通信システムセットアップ

        通信モジュールを使用してNumeric側との通信を初期化
        """
        self.comm_manager = PlantCommunicationManager(self.config)
        self.communicator = self.comm_manager.setup_communication()

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

        # CSVヘッダー（分析用データ）
        self.csv_writer.writerow(['seq', 't', 'recv_time', 'send_time', 'thrust',
                                 'altitude', 'velocity', 'acceleration',
                                 'step_start_sync', 'step_start_wall', 'sync_base_time'])

    def get_state_data(self) -> Dict:
        """
        現在の状態データを構築

        Returns:
            標準的なセンサーデータフォーマットの状態辞書
        """
        return {
            "acc": [0.0, 0.0, self.plant.acceleration + np.random.normal(0, 0.01)],  # Z軸加速度計
            "gyro": [0.0, 0.0, 0.0],                                                 # 回転なし
            "position": [0.0, 0.0, self.plant.position],                           # 高度のみ
            "velocity": [0.0, 0.0, self.plant.velocity]                            # Z軸速度のみ
        }

    def wait_for_synchronization(self):
        """
        Numeric側からの同期プロトコル待機

        通信モジュールの同期機能を使用
        """
        self.communicator.wait_for_synchronization()

    def run(self):
        """
        独立シミュレーションループメイン実行

        固定周期でPlant物理シミュレーションを実行し、
        通信モジュールを通じてNumeric側とデータ交換。

        実行フロー：
        1. 同期プロトコル実行
        2. 固定周期ループ開始
        3. 遅延コマンド処理
        4. 新コマンド受信
        5. 物理更新
        6. 状態配信
        7. ログ記録
        """
        logger.info(f"Plant independent simulation started: {self.max_steps} steps at {1/self.dt:.0f} Hz")

        # ===== 1. Numeric側との同期プロトコル実行 =====
        self.wait_for_synchronization()

        # シミュレーション再初期化（同期後に状態リセット）
        sim_config = self.config['simulation']
        initial_position = float(sim_config['initial_position'])
        initial_velocity = float(sim_config['initial_velocity'])
        self.plant.reset(initial_position, initial_velocity)

        try:
            start_time = time.perf_counter()

            # ===== 2. 固定周期メインループ =====
            for step in range(self.max_steps):
                step_start = time.perf_counter()
                step_start_sync = self.communicator.get_sync_timestamp()
                step_start_wall = time.time()

                self.step_count = step
                self.sim_time = step * self.dt

                # ===== 3. 遅延コマンド処理（遅延シミュレーション有効時）=====
                delayed_command = self.communicator.process_delayed_commands()
                if delayed_command is not None:
                    self.current_thrust = delayed_command[2] if len(delayed_command) >= 3 else 0.0

                # ===== 4. 新コマンド受信（ノンブロッキング）=====
                new_command = self.communicator.receive_commands()
                if new_command is not None:
                    self.current_thrust = new_command[2] if len(new_command) >= 3 else 0.0

                # ===== 5. 物理モデル更新 =====
                position, velocity, acceleration = self.plant.update(self.current_thrust, self.dt)

                # ===== 6. 状態データをNumeric側に配信 =====
                state_data = self.get_state_data()
                self.communicator.broadcast_state(step, self.sim_time, state_data)

                # ===== 7. ログ記録 =====
                if self.csv_writer:
                    current_time = time.time()
                    self.csv_writer.writerow([
                        step, self.sim_time, current_time, current_time,
                        self.current_thrust, position, velocity, acceleration,
                        step_start_sync, step_start_wall, self.communicator.sync_base_time
                    ])
                    self.log_fp.flush()

                # 進捗表示（500ステップ毎）
                if (step + 1) % 500 == 0:
                    logger.info(f"Plant step {step + 1}/{self.max_steps}, Alt: {position:.2f}m, Thrust: {self.current_thrust:.1f}N")

                # ===== 固定周期制御：次ステップまで待機 =====
                elapsed = time.perf_counter() - step_start
                sleep_time = self.dt - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # 周期を逃した場合の警告
                    logger.warning(f"Plant missed timestep by {-sleep_time*1000:.1f}ms at step {step}")

            # ===== 実行結果統計 =====
            total_time = time.perf_counter() - start_time
            logger.info(f"Plant simulation completed: {self.max_steps} steps in {total_time:.2f}s")
            logger.info(f"Average step time: {total_time/self.max_steps*1000:.1f}ms")

        except KeyboardInterrupt:
            logger.info("Plant simulation interrupted")
        except Exception as e:
            logger.error(f"Error in plant simulation: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """
        リソース解放・クリーンアップ

        ログファイルと通信リソースを適切に終了
        """
        if hasattr(self, 'csv_writer') and self.csv_writer:
            self.log_fp.close()
        if hasattr(self, 'comm_manager'):
            self.comm_manager.cleanup()
        logger.info("Plant simulator stopped")


if __name__ == "__main__":
    """
    メインエントリポイント

    スクリプトが直接実行された場合のみPlantシミュレーターを起動
    Docker環境では config.yaml 設定を使用して実行される
    """
    simulator = PlantSimulator()  # シミュレーター初期化
    simulator.run()               # シミュレーション開始