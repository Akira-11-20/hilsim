#!/usr/bin/env python3
"""
リアルタイム制御シミュレーター（Numeric側）
固定dt周期で動作し、通信遅延に関係なく一定周期で制御を実行
HILSシステムの制御部分を担当し、Plantシミュレーションと非同期で通信する
"""

# 外部ライブラリのインポート
import yaml         # YAML設定ファイル読み込み
import numpy as np  # 数値計算（制御計算、配列操作）
import pandas as pd # データ分析（未使用だが将来拡張用）
import os           # 環境変数とファイルシステム操作
import sys          # システム関数
import time         # 時間計測とスリープ
import csv          # CSV形式でのログ出力
import logging      # ログ出力
import threading    # マルチスレッド（将来拡張用）
from queue import Queue, Empty  # キューデータ構造（将来拡張用）
from typing import Dict, List, Optional  # 型ヒント

# 通信モジュールをインポート
from numeric_communication import NumericCommunicationManager

# ログ設定：INFO レベル以上のメッセージを時刻付きで出力
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AltitudePIDController:
    """
    高度制御用PID制御器クラス

    PID制御：比例(P) + 積分(I) + 微分(D)制御
    - P項：現在の誤差に比例した制御
    - I項：過去の誤差の累積に基づく制御（定常偏差を除去）
    - D項：誤差の変化率に基づく制御（オーバーシュートを抑制）
    """

    def __init__(self, kp: float, ki: float, kd: float, setpoint: float):
        """
        PID制御器の初期化

        Args:
            kp: 比例ゲイン（大きいほど応答が速いが振動しやすい）
            ki: 積分ゲイン（定常偏差を除去、大きすぎると不安定）
            kd: 微分ゲイン（ダンピング効果、ノイズに敏感）
            setpoint: 目標値（目標高度[m]）
        """
        self.kp = kp                    # 比例ゲイン
        self.ki = ki                    # 積分ゲイン
        self.kd = kd                    # 微分ゲイン
        self.setpoint = float(setpoint) # 目標高度

        # 制御器の内部状態
        self.error_sum = 0.0      # 誤差の積分値（I項計算用）
        self.prev_error = None    # 前回の誤差（D項計算用）
        self.prev_time = None     # 前回の時刻（将来拡張用）

        # 積分項のwindup防止（積分値が無限に大きくなることを防ぐ）
        self.integral_limit = 300.0  # 積分値の上下限

    def reset(self):
        """
        制御器状態をリセット
        シミュレーション開始時や異常時に内部状態をクリア
        """
        self.error_sum = 0.0    # 積分値をリセット
        self.prev_error = None  # 前回誤差をリセット
        self.prev_time = None   # 前回時刻をリセット

    def update(self, measurement: float, dt: float) -> float:
        """
        PID制御器の更新（制御出力計算）

        Args:
            measurement: 現在の測定値（現在高度[m]）
            dt: 制御周期[s]（通常0.01s = 10ms）

        Returns:
            制御出力（推力補正値[N]）
        """
        # 制御誤差 = 目標値 - 現在値
        error = self.setpoint - measurement

        # 初回呼び出し時の初期化
        if self.prev_error is None:
            self.prev_error = error

        # P項（比例項）：現在の誤差に比例
        p_term = self.kp * error

        # I項（積分項）：過去の誤差の蓄積に比例（定常偏差除去）
        self.error_sum += error * dt  # 誤差を時間積分
        # Windup防止：積分値を制限範囲にクリップ
        self.error_sum = np.clip(self.error_sum, -self.integral_limit, self.integral_limit)
        i_term = self.ki * self.error_sum

        # D項（微分項）：誤差の変化率に比例（振動抑制）
        if dt > 0:
            d_term = self.kd * (error - self.prev_error) / dt
        else:
            d_term = 0.0  # ゼロ除算回避

        # PID出力 = P項 + I項 + D項
        output = p_term + i_term + d_term

        # 次回計算のために現在値を保存
        self.prev_error = error

        return output


class RealtimeNumericSimulator:
    """
    リアルタイム制御シミュレーターメインクラス

    固定周期（通常10ms）でPID制御を実行し、Plantシミュレーションと
    非同期通信を行うHILSシステムの制御部分。

    主要機能：
    - 固定周期制御ループ（リアルタイム性確保）
    - PID高度制御
    - 非同期Plant通信
    - 通信障害時のフォールバック制御
    - 詳細ログ記録・分析
    """

    def __init__(self, config_file: str = "config.yaml"):
        """
        シミュレーター初期化

        Args:
            config_file: 設定ファイルパス（YAML形式）
        """
        self.load_config(config_file)       # 設定読み込み
        self.setup_controller()             # PID制御器設定
        self.setup_logging()                # ログシステム設定
        self.setup_communication()          # 通信システム設定

        # ===== 制御状態変数 =====
        self.current_altitude = 0.0         # 現在高度[m]
        self.current_velocity = 0.0         # 現在速度[m/s]
        self.current_acceleration = 0.0     # 現在加速度[m/s²]
        self.sim_time = 0.0                 # シミュレーション時刻[s]
        self.step_count = 0                 # ステップカウンタ

        # ===== フォールバック制御（通信失敗時）=====
        self.last_valid_altitude = 0.0      # 最後の有効高度値
        self.consecutive_failures = 0       # 連続通信失敗回数
        self.max_consecutive_failures = 10  # 最大許容連続失敗数
        
    def load_config(self, config_file: str):
        """
        設定ファイル読み込み・環境変数による上書き

        Args:
            config_file: YAML設定ファイルパス
        """
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        # 環境変数による設定上書き（Docker環境での動的設定用）
        self.plant_endpoint = os.getenv('PLANT_ENDPOINT', self.config['numeric']['plant_endpoint'])
        self.dt = float(os.getenv('STEP_DT', self.config['numeric']['dt']))  # 制御周期[s]
        self.max_steps = int(os.getenv('MAX_STEPS', self.config['numeric']['max_steps']))  # 最大ステップ数
        self.timeout_ms = self.config['numeric']['timeout_ms']  # 通信タイムアウト[ms]

        # タイムスタンプ付きログディレクトリ作成
        run_id = os.getenv('RUN_ID', time.strftime('%Y%m%d_%H%M%S'))
        log_dir = f"/app/logs/{run_id}"
        self.log_file = f"{log_dir}/realtime_numeric_log.csv"

    def setup_controller(self):
        """
        PID制御器セットアップ

        設定ファイルからPIDパラメータを読み込んで制御器を初期化
        """
        ctrl_config = self.config['controller']
        self.controller = AltitudePIDController(
            kp=ctrl_config['kp'],       # 比例ゲイン
            ki=ctrl_config['ki'],       # 積分ゲイン
            kd=ctrl_config['kd'],       # 微分ゲイン
            setpoint=ctrl_config['setpoint']  # 目標高度[m]
        )

    def setup_logging(self):
        """
        ログシステムセットアップ

        CSV形式でのデータログを設定。制御性能解析のために
        詳細なタイミング情報と制御データを記録。
        """
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self.log_fp = open(self.log_file, 'w', newline='')
        self.csv_writer = csv.writer(self.log_fp)

        # CSVヘッダー（分析用に豊富なメタデータを含む）
        self.csv_writer.writerow(['seq', 'sim_time', 'actual_time', 'control_dt',
                                 'thrust_cmd', 'altitude', 'velocity', 'acceleration',
                                 'altitude_error', 'setpoint', 'communication_status',
                                 'rtt_ms', 'consecutive_failures',
                                 'step_start_sync', 'cmd_send_sync', 'response_recv_sync',
                                 'cmd_send_to_recv', 'step_start_wall', 'cmd_send_wall', 'response_recv_wall'])

    def setup_communication(self):
        """
        通信システムセットアップ

        通信モジュールを使用してPlant側との非同期通信を初期化
        """
        self.comm_manager = NumericCommunicationManager(self.config)
        self.communicator = self.comm_manager.setup_communication(self.plant_endpoint)
        
    def get_command(self, step: int, current_altitude: float) -> List[float]:
        """
        制御コマンド生成

        PID制御器の出力に重力補償を加えて推力コマンドを生成

        Args:
            step: ステップ番号（未使用）
            current_altitude: 現在高度[m]

        Returns:
            制御力ベクトル [fx, fy, fz] [N]
        """
        # ===== 物理パラメータ =====
        mass = 1.0      # 機体質量[kg]
        gravity = 9.81  # 重力加速度[m/s²]

        # ===== PID制御計算 =====
        # PID制御器で高度誤差に基づく補正推力を計算
        pid_output = self.controller.update(current_altitude, self.dt)

        # ===== 重力補償付き推力計算 =====
        # 基本推力（重力釣り合い）+ PID補正推力
        thrust = pid_output + mass * gravity

        # ===== 推力制限 =====
        max_thrust = 1000.0  # 最大推力[N]
        thrust = np.clip(thrust, 0, max_thrust)  # 0以上、max_thrust以下に制限

        # 制御力ベクトル [fx=0, fy=0, fz=thrust]
        return [0.0, 0.0, thrust]
        
    def run_realtime(self):
        """
        リアルタイム制御メインループ

        固定周期でPID制御を実行し、Plant側と非同期通信を行う。
        制御周期は設定ファイルのdt値で決まり、通常10ms（100Hz）。

        制御ループの流れ：
        1. Plant状態データ受信（ノンブロッキング）
        2. PID制御計算
        3. 制御コマンド送信（ノンブロッキング）
        4. ログ記録
        5. 次ステップまで待機（固定周期維持）
        """
        logger.info(f"Realtime simulator started, will run {self.max_steps} steps at {1/self.dt:.0f} Hz")
        logger.info(f"Control period: {self.dt*1000:.1f}ms")

        # ===== 通信初期化（同期プロトコル実行）=====
        self.communicator.start_communication()

        # ===== リアルタイム制御ループ準備 =====
        start_time = time.perf_counter()  # 高精度時間測定開始
        next_step_time = start_time       # 次ステップ実行時刻

        # 統計カウンタ
        successful_steps = 0  # 成功ステップ数
        failed_steps = 0      # 失敗ステップ数

        try:
            # ===== メイン制御ループ =====
            for step in range(self.max_steps):
                # ===== 詳細タイミング追跡 =====
                step_start_time = time.perf_counter()  # ステップ開始時刻（高精度）
                step_start_sync = self.communicator.get_sync_timestamp()  # 同期タイムスタンプ
                step_start_wall = time.time()  # 壁時計時刻

                # ===== 1. Plant状態データ受信 =====
                latest_response = self.communicator.get_latest_response()

                # Response timing
                response_recv_sync = self.communicator.get_sync_timestamp()
                response_recv_wall = time.time()

                if latest_response and latest_response.get('valid', False):
                    # ===== 有効な応答データを受信した場合 =====
                    plant_data = latest_response['plant_response']['y']
                    self.current_altitude = plant_data['position'][2]     # Z軸位置（高度）
                    self.current_velocity = plant_data['velocity'][2]     # Z軸速度
                    self.current_acceleration = plant_data['acc'][2]      # Z軸加速度
                    self.last_valid_altitude = self.current_altitude      # フォールバック用保存
                    self.consecutive_failures = 0                        # 失敗カウンタリセット
                    communication_status = "OK"
                    rtt_ms = latest_response.get('rtt_ms', 0)
                    successful_steps += 1
                else:
                    # ===== 応答がない場合（通信遅延・タイムアウト）=====
                    self.consecutive_failures += 1
                    communication_status = "TIMEOUT"
                    rtt_ms = 0
                    failed_steps += 1

                    # フォールバック制御（最後の有効値を使用）
                    if self.consecutive_failures > self.max_consecutive_failures:
                        logger.error(f"Too many consecutive failures ({self.consecutive_failures}), using fallback")
                        # 緊急時：最後の有効高度値で制御継続
                        self.current_altitude = self.last_valid_altitude

                # ===== 2. PID制御コマンド生成 =====
                command = self.get_command(step, self.current_altitude)

                # Command send timing
                cmd_send_sync = self.communicator.get_sync_timestamp()
                cmd_send_wall = time.time()

                # ===== 3. 非同期でPlantにコマンド送信 =====
                self.communicator.send_command_async(step, self.sim_time, command)
                
                # ===== 4. ログ記録・分析データ保存 =====
                actual_time = time.perf_counter() - start_time  # 実際の経過時間
                control_dt = actual_time - self.sim_time if step > 0 else self.dt  # 制御周期偏差
                altitude_error = self.controller.setpoint - self.current_altitude  # 高度誤差

                # 追加タイミング解析用メトリクス
                cmd_send_to_recv = response_recv_sync - cmd_send_sync if latest_response else 0

                if self.csv_writer:
                    self.csv_writer.writerow([
                        step, self.sim_time, actual_time, control_dt,
                        command[2], self.current_altitude, self.current_velocity,
                        self.current_acceleration, altitude_error, self.controller.setpoint,
                        communication_status, rtt_ms, self.consecutive_failures,
                        step_start_sync, cmd_send_sync, response_recv_sync,
                        cmd_send_to_recv, step_start_wall, cmd_send_wall, response_recv_wall
                    ])
                    self.log_fp.flush()  # リアルタイムログ出力

                # ===== 進捗表示（100ステップ毎）=====
                if (step + 1) % 100 == 0:
                    logger.info(f"Step {step + 1}/{self.max_steps}, Alt: {self.current_altitude:.2f}m, "
                              f"Status: {communication_status}, RTT: {rtt_ms:.1f}ms")

                # ===== 5. 固定周期制御：次ステップまで待機 =====
                self.sim_time += self.dt        # シミュレーション時刻更新
                next_step_time += self.dt       # 次ステップ目標時刻更新

                # リアルタイム性確保：指定時刻まで正確に待機
                sleep_time = next_step_time - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)  # 次ステップまで待機
                else:
                    # 制御周期を逃した場合の警告（パフォーマンス問題検出）
                    logger.warning(f"Missed control deadline by {-sleep_time*1000:.1f}ms at step {step}")
                    
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Error in realtime loop: {e}")
        finally:
            # 必ずリソース解放を実行
            self.cleanup()

        # ===== 実行結果統計・レポート =====
        total_time = time.perf_counter() - start_time
        logger.info(f"Realtime simulation completed: {successful_steps} successful, {failed_steps} failed")
        logger.info(f"Total time: {total_time:.2f}s, Average period: {total_time/self.max_steps*1000:.1f}ms")

        # 通信統計取得
        comm_stats = self.communicator.get_communication_stats()
        logger.info(f"Communication stats: Sent={comm_stats['sent_count']}, "
                   f"Received={comm_stats['received_count']}, Timeouts={comm_stats['timeout_count']}")

        # Dockerログに表示される完了通知（視認性向上）
        import sys
        completion_msg = f"""
{'='*60}
🚀 HILS SIMULATION COMPLETED 🚀
{'='*60}
Steps: {successful_steps}/{self.max_steps} successful ({successful_steps/self.max_steps*100:.1f}%)
Runtime: {total_time:.2f}s (Target: {self.max_steps*self.dt:.2f}s)
Real-time factor: {total_time/(self.max_steps*self.dt):.2f}x
Communication: {comm_stats['timeout_count']} timeouts
{'='*60}
📊 Run 'make analyze' to view results
{'='*60}
"""
        print(completion_msg, flush=True)
        sys.stdout.flush()

    def cleanup(self):
        """
        リソース解放・クリーンアップ

        ログファイルと通信リソースを適切に終了
        """
        if hasattr(self, 'log_fp'):
            self.log_fp.close()  # CSVログファイル終了
        if hasattr(self, 'comm_manager'):
            self.comm_manager.cleanup()  # 通信マネージャー終了
        logger.info("Realtime simulator stopped")


if __name__ == "__main__":
    """
    メインエントリポイント

    スクリプトが直接実行された場合のみリアルタイムシミュレーターを起動
    Docker環境では config.yaml 設定を使用して実行される
    """
    simulator = RealtimeNumericSimulator()  # シミュレーター初期化
    simulator.run_realtime()                # リアルタイム制御開始