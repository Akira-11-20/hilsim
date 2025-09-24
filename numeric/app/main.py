#!/usr/bin/env python3
"""
Numeric シミュレーターメインファイル（新アーキテクチャ版）

参考構造に基づくUDPクライアント実装。
PID制御器でPlant側に制御コマンドを送信し、
状態データを受信してRTT測定・ログ記録を行う。

主要機能：
- AltitudePIDController: 高度制御PID制御器
- UDP Client: リクエスト・レスポンス通信
- RTT測定・統計
- ログ記録・分析
"""

import socket
import yaml
import numpy as np
import pandas as pd
import os
import sys
import time
import csv
import logging
from typing import Dict, List, Optional, Tuple

# 新プロトコルをインポート
sys.path.append('/app')
from shared.protocol import ProtocolHandler, RequestPacket, ResponsePacket, create_request_packet

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AltitudePIDController:
    """動作確認済みのPID制御器 - simple_pid_control/から移植"""
    
    def __init__(self, kp: float, ki: float, kd: float, setpoint: float):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = float(setpoint)  # Target altitude [m]
        
        self.error_sum = 0.0
        self.prev_error = None
        self.prev_time = None
        
        # 積分項のwindup防止
        self.integral_limit = 30.0
        
    def reset(self):
        """制御器状態をリセット"""
        self.error_sum = 0.0
        self.prev_error = None
        self.prev_time = None
        
    def update(self, measurement: float, dt: float) -> float:
        """PID制御器の更新"""
        error = self.setpoint - measurement
        
        # 初回呼び出し時の初期化
        if self.prev_error is None:
            self.prev_error = error
            
        # 比例項
        p_term = self.kp * error
        
        # 積分項（windup防止付き）
        self.error_sum += error * dt
        self.error_sum = np.clip(self.error_sum, -self.integral_limit, self.integral_limit)
        i_term = self.ki * self.error_sum
        
        # 微分項
        if dt > 0:
            d_term = self.kd * (error - self.prev_error) / dt
        else:
            d_term = 0.0
            
        # PID出力
        output = p_term + i_term + d_term
        
        # 次回のために保存
        self.prev_error = error
        
        return output

class NumericClient:
    """
    Numeric UDP クライアントクラス（新アーキテクチャ版）

    参考構造に基づくUDPクライアント実装。
    Plant側にUDPリクエストを送信し、RTT測定を行う。

    主要機能：
    - UDP Client（リクエスト・レスポンス通信）
    - PID制御器（AltitudePIDController）
    - RTT測定・統計
    - ログ記録・分析
    """

    def __init__(self, config_file: str = "config.yaml"):
        self.load_config(config_file)
        self.setup_controller()
        self.setup_logging()
        self.setup_udp_client()
        self.load_scenario()
        
    def load_config(self, config_file: str):
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        # UDP通信設定
        self.plant_host = os.getenv('PLANT_HOST', 'plant')  # Plantサーバーホスト
        self.plant_port = int(os.getenv('PLANT_PORT', 5005))  # Plantサーバーポート
        self.timeout_s = float(os.getenv('TIMEOUT_S', 1.0))  # タイムアウト[秒]

        # シミュレーション設定
        self.dt = float(os.getenv('STEP_DT', self.config['numeric']['dt']))
        self.max_steps = int(os.getenv('MAX_STEPS', self.config['numeric']['max_steps']))
        self.rate_hz = float(os.getenv('RATE_HZ', 50))  # 送信周波数[Hz]

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

        print(f"Numeric log directory: {log_dir}")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = f"{log_dir}/numeric_log.csv"
        
    def setup_udp_client(self):
        """UDPクライアント設定"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.settimeout(self.timeout_s)
        logger.info(f"UDP client configured for {self.plant_host}:{self.plant_port}")

        # 統計情報
        self.sent_count = 0
        self.received_count = 0
        self.timeout_count = 0
        self.rtt_history = []
        self.start_time = time.time()
        
    def setup_controller(self):
        ctrl_config = self.config['controller']
        self.controller = AltitudePIDController(
            kp=ctrl_config['kp'],
            ki=ctrl_config['ki'], 
            kd=ctrl_config['kd'],
            setpoint=ctrl_config['setpoint']  # Single altitude setpoint
        )
        
    def setup_logging(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self.log_fp = open(self.log_file, 'w', newline='')
        self.csv_writer = csv.writer(self.log_fp)
        self.csv_writer.writerow(['seq', 't', 'send_time', 'recv_time', 'rtt_ms',
                                 'fx', 'fy', 'fz', 'altitude', 'velocity', 'acceleration',
                                 'altitude_error', 'setpoint', 'timeout'])
    
    def load_scenario(self):
        self.scenario = None
        scenario_config = self.config.get('scenario', {})
        if scenario_config.get('enabled', False):
            scenario_file = scenario_config.get('file')
            if scenario_file and os.path.exists(scenario_file):
                self.scenario = pd.read_csv(scenario_file)
                logger.info(f"Loaded scenario from {scenario_file}")
    
    def get_command(self, step: int, current_altitude: float) -> Tuple[float, float, float]:
        """制御コマンド生成（新アーキテクチャ版）"""
        # 質量・重力定数
        mass = 1.0
        gravity = 9.81

        if self.scenario is not None:
            # シナリオベースの制御
            scenario_row = None
            for _, row in self.scenario.iterrows():
                if row['step'] <= step:
                    scenario_row = row
                else:
                    break

            if scenario_row is not None:
                cmd_type = scenario_row.get('cmd_type', 'position')
                cmd_z = scenario_row.get('cmd_z', 10.0)

                if cmd_type == 'force':
                    # 直接推力指令
                    return (0.0, 0.0, cmd_z)
                else:
                    # 高度設定値 - PID制御
                    self.controller.setpoint = cmd_z
                    pid_output = self.controller.update(current_altitude, self.dt)
                    thrust = pid_output + mass * gravity
                    return (0.0, 0.0, thrust)

        # デフォルト: PID制御（重力補償付き）
        pid_output = self.controller.update(current_altitude, self.dt)
        thrust = pid_output + mass * gravity

        # 推力制限
        max_thrust = 1000.0
        thrust = np.clip(thrust, 0, max_thrust)

        return (0.0, 0.0, thrust)
    
    def send_receive_udp(self, seq: int, sim_time: float, fx: float, fy: float, fz: float) -> Optional[Dict]:
        """UDPリクエスト・レスポンス通信"""
        try:
            # リクエストパケット生成
            request = create_request_packet(seq, fx, fy, fz)
            request_data = ProtocolHandler.pack_request(request)

            # 高精度RTT測定開始
            send_time = time.time()
            perf_start = time.perf_counter()

            # UDP送信
            self.socket.sendto(request_data, (self.plant_host, self.plant_port))
            self.sent_count += 1

            # UDP受信
            response_data, addr = self.socket.recvfrom(1024)
            recv_time = time.time()
            rtt_ms = (time.perf_counter() - perf_start) * 1000

            # レスポンスパケット解析
            response = ProtocolHandler.unpack_response(response_data)
            if not response:
                logger.warning(f"Invalid response packet from {addr}")
                return None

            self.received_count += 1
            self.rtt_history.append(rtt_ms)

            # RTT履歴管理（最新1000件）
            if len(self.rtt_history) > 1000:
                self.rtt_history = self.rtt_history[-500:]

            return {
                'response': response,
                'send_time': send_time,
                'recv_time': recv_time,
                'rtt_ms': rtt_ms,
                'timeout': False
            }

        except socket.timeout:
            logger.warning(f"Timeout on step {seq}")
            self.timeout_count += 1
            return {'timeout': True}
        except Exception as e:
            logger.error(f"Communication error on step {seq}: {e}")
            return None
    
    def run(self):
        """UDPクライアントメイン実行（新アーキテクチャ版）"""
        logger.info(f"Numeric UDP client started: {self.max_steps} steps at {self.rate_hz} Hz")
        logger.info(f"Target: {self.plant_host}:{self.plant_port}, timeout: {self.timeout_s}s")

        # 状態追跡変数
        current_altitude = 0.0
        sim_time = 0.0
        successful_steps = 0
        failed_steps = 0

        try:
            step_interval = 1.0 / self.rate_hz  # ステップ間隔[s]

            for step in range(self.max_steps):
                step_start = time.perf_counter()

                # 制御コマンド生成
                fx, fy, fz = self.get_command(step, current_altitude)

                # UDP通信実行
                result = self.send_receive_udp(step, sim_time, fx, fy, fz)

                timeout = False
                if result is None:
                    failed_steps += 1
                    logger.warning(f"Step {step} communication failed")
                    continue
                elif result.get('timeout', False):
                    failed_steps += 1
                    timeout = True
                    # タイムアウト時もログに記録
                    if self.csv_writer:
                        self.csv_writer.writerow([
                            step, sim_time, 0, 0, 0,  # タイムスタンプ・RTTは0
                            fx, fy, fz, current_altitude, 0, 0,  # 前回の値を使用
                            0, self.controller.setpoint, True
                        ])
                        self.log_fp.flush()
                    continue

                response = result['response']

                # Plant応答から状態データ抽出
                current_altitude = response.pos_z
                current_velocity = response.vel_z
                current_acceleration = response.acc_z

                # 高度誤差計算
                altitude_error = self.controller.setpoint - current_altitude

                # ログ記録
                if self.csv_writer:
                    self.csv_writer.writerow([
                        step, sim_time, result['send_time'], result['recv_time'], result['rtt_ms'],
                        fx, fy, fz, current_altitude, current_velocity, current_acceleration,
                        altitude_error, self.controller.setpoint, timeout
                    ])
                    self.log_fp.flush()

                successful_steps += 1
                sim_time += self.dt

                # 進捗表示（100ステップ毎）
                if (step + 1) % 100 == 0:
                    avg_rtt = np.mean(self.rtt_history[-100:]) if len(self.rtt_history) >= 100 else 0
                    logger.info(f"Step {step + 1}/{self.max_steps}, RTT: {result['rtt_ms']:.2f}ms (avg: {avg_rtt:.2f}ms), Alt: {current_altitude:.2f}m")

                # レート制御（固定周期実行）
                elapsed = time.perf_counter() - step_start
                sleep_time = step_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()

        # 統計表示
        self.print_final_statistics(successful_steps, failed_steps)

    def print_final_statistics(self, successful_steps: int, failed_steps: int):
        """最終統計の表示"""
        total_time = time.time() - self.start_time
        success_rate = successful_steps / (successful_steps + failed_steps) * 100 if (successful_steps + failed_steps) > 0 else 0

        # RTT統計
        rtt_stats = {}
        if len(self.rtt_history) > 0:
            rtt_stats = {
                'mean': np.mean(self.rtt_history),
                'std': np.std(self.rtt_history),
                'min': np.min(self.rtt_history),
                'max': np.max(self.rtt_history),
                'p95': np.percentile(self.rtt_history, 95)
            }

        logger.info(f"Simulation completed: {successful_steps} successful, {failed_steps} failed ({success_rate:.1f}% success rate)")
        logger.info(f"Communication stats: sent={self.sent_count}, received={self.received_count}, timeouts={self.timeout_count}")
        if rtt_stats:
            logger.info(f"RTT stats: {rtt_stats['mean']:.2f}±{rtt_stats['std']:.2f}ms [{rtt_stats['min']:.2f}-{rtt_stats['max']:.2f}ms] P95={rtt_stats['p95']:.2f}ms")

        # コンソール出力
        completion_msg = f"""
{'='*60}
🚀 HILS SIMULATION COMPLETED 🚀
{'='*60}
Steps: {successful_steps}/{successful_steps + failed_steps} successful ({success_rate:.1f}%)
Communication: {self.sent_count} sent, {self.received_count} received, {self.timeout_count} timeouts
Runtime: {total_time:.1f}s
{'='*60}
📊 Run 'make analyze' to view results
{'='*60}
"""
        print(completion_msg, flush=True)
        
    def cleanup(self):
        """リソース解放"""
        if hasattr(self, 'log_fp'):
            self.log_fp.close()
        if hasattr(self, 'socket'):
            self.socket.close()
        logger.info("Numeric client stopped")

if __name__ == "__main__":
    """
    メインエントリポイント

    新アーキテクチャ版：UDP Client として動作
    """
    client = NumericClient()
    client.run()