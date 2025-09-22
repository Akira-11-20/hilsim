#!/usr/bin/env python3
"""
リアルタイム制御シミュレーター
固定dt周期で動作し、通信遅延に関係なく一定周期で制御を実行
"""

import zmq
import json
import yaml
import numpy as np
import pandas as pd
import os
import sys
import time
import csv
import logging
import threading
from queue import Queue, Empty
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AltitudePIDController:
    """動作確認済みのPID制御器"""
    
    def __init__(self, kp: float, ki: float, kd: float, setpoint: float):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = float(setpoint)
        
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


class AsyncPlantCommunicator:
    """非同期Plant通信クラス - PUB/SUB版"""
    
    def __init__(self, plant_state_endpoint: str, cmd_publish_port: int = 5556):
        self.plant_state_endpoint = plant_state_endpoint
        self.cmd_publish_port = cmd_publish_port
        self.context = zmq.Context()
        
        # State subscriber (Plant → Numeric)
        self.state_subscriber = self.context.socket(zmq.SUB)
        self.state_subscriber.connect(plant_state_endpoint)
        self.state_subscriber.setsockopt(zmq.SUBSCRIBE, b"")
        self.state_subscriber.setsockopt(zmq.RCVTIMEO, 10)  # 10ms timeout
        
        # Command publisher (Numeric → Plant)
        self.cmd_publisher = self.context.socket(zmq.PUB)
        self.cmd_publisher.bind(f"tcp://*:{cmd_publish_port}")
        
        # 通信管理
        self.latest_state = None
        self.seq_counter = 0
        
        # RTT measurement
        self.command_timestamps = {}  # seq -> timestamp mapping
        
        # 統計
        self.sent_count = 0
        self.received_count = 0
        self.timeout_count = 0
        
        logger.info(f"AsyncPlantCommunicator setup: SUB from {plant_state_endpoint}, PUB on :{cmd_publish_port}")
        
    def start_communication(self):
        """通信初期化（PUB/SUB版では不要だが互換性のため）"""
        logger.info("Async communication ready")
        
    def stop_communication(self):
        """通信停止"""
        self.state_subscriber.close()
        self.cmd_publisher.close()
        self.context.term()
        logger.info("Async communication stopped")
        
    def send_command_async(self, seq: int, sim_time: float, command: List[float]):
        """非同期でコマンドを送信（ノンブロッキング）"""
        send_timestamp = time.time()
        cmd_msg = {
            "seq": seq,
            "t": sim_time,
            "u": command,
            "timestamp": send_timestamp
        }
        
        # Store timestamp for RTT calculation
        self.command_timestamps[seq] = send_timestamp
        
        # Clean up old timestamps (keep only last 100)
        if len(self.command_timestamps) > 100:
            oldest_seq = min(self.command_timestamps.keys())
            del self.command_timestamps[oldest_seq]
        
        try:
            self.cmd_publisher.send_json(cmd_msg, zmq.NOBLOCK)
            self.sent_count += 1
        except zmq.Again:
            logger.warning(f"Command send buffer full for seq={seq}")
            
    def get_latest_response(self) -> Optional[Dict]:
        """最新の応答を取得（ノンブロッキング）"""
        try:
            # Get all available messages, keep only the latest
            while True:
                try:
                    state_msg = self.state_subscriber.recv_json(zmq.NOBLOCK)
                    recv_time = time.time()
                    
                    # Calculate RTT if we have the command timestamp
                    rtt_ms = 0.0
                    latest_cmd_seq = state_msg.get('latest_cmd_seq', -1)
                    latest_cmd_timestamp = state_msg.get('latest_cmd_timestamp', 0)
                    
                    if latest_cmd_seq in self.command_timestamps:
                        # Calculate actual RTT: current time - command send time from Numeric
                        send_time = self.command_timestamps[latest_cmd_seq]
                        rtt_ms = (recv_time - send_time) * 1000
                    
                    self.latest_state = {
                        'plant_response': state_msg,
                        'seq': state_msg.get('seq', 0),
                        'sim_time': state_msg.get('t', 0),
                        'recv_time': recv_time,
                        'rtt_ms': rtt_ms,
                        'valid': state_msg.get('valid', False)
                    }
                    self.received_count += 1
                except zmq.Again:
                    break
        except Exception as e:
            logger.warning(f"Error receiving state: {e}")
            
        return self.latest_state


class RealtimeNumericSimulator:
    """リアルタイム制御シミュレーター"""
    
    def __init__(self, config_file: str = "config.yaml"):
        self.load_config(config_file)
        self.setup_controller()
        self.setup_logging()
        self.setup_communication()
        
        # 制御状態
        self.current_altitude = 0.0
        self.current_velocity = 0.0
        self.current_acceleration = 0.0
        self.sim_time = 0.0
        self.step_count = 0
        
        # フォールバック制御（通信失敗時）
        self.last_valid_altitude = 0.0
        self.consecutive_failures = 0
        self.max_consecutive_failures = 10
        
    def load_config(self, config_file: str):
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
            
        # Override with environment variables
        self.plant_endpoint = os.getenv('PLANT_ENDPOINT', self.config['numeric']['plant_endpoint'])
        self.dt = float(os.getenv('STEP_DT', self.config['numeric']['dt']))
        self.max_steps = int(os.getenv('MAX_STEPS', self.config['numeric']['max_steps']))
        self.timeout_ms = self.config['numeric']['timeout_ms']
        
        # Create timestamped log directory
        run_id = os.getenv('RUN_ID', time.strftime('%Y%m%d_%H%M%S'))
        log_dir = f"/app/logs/{run_id}"
        self.log_file = f"{log_dir}/realtime_numeric_log.csv"
        
    def setup_controller(self):
        ctrl_config = self.config['controller']
        self.controller = AltitudePIDController(
            kp=ctrl_config['kp'],
            ki=ctrl_config['ki'], 
            kd=ctrl_config['kd'],
            setpoint=ctrl_config['setpoint']
        )
        
    def setup_logging(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self.log_fp = open(self.log_file, 'w', newline='')
        self.csv_writer = csv.writer(self.log_fp)
        self.csv_writer.writerow(['seq', 'sim_time', 'actual_time', 'control_dt',
                                 'thrust_cmd', 'altitude', 'velocity', 'acceleration',
                                 'altitude_error', 'setpoint', 'communication_status',
                                 'rtt_ms', 'consecutive_failures'])
                                 
    def setup_communication(self):
        self.communicator = AsyncPlantCommunicator(self.plant_endpoint)
        
    def get_command(self, step: int, current_altitude: float) -> List[float]:
        """Generate thrust command - same as original"""
        mass = 1.0
        gravity = 9.81
        
        # PID controller with proper gravity compensation
        pid_output = self.controller.update(current_altitude, self.dt)
        thrust = pid_output + mass * gravity
        
        # Thrust limits
        max_thrust = 1000.0
        thrust = np.clip(thrust, 0, max_thrust)
        
        return [0.0, 0.0, thrust]
        
    def run_realtime(self):
        """リアルタイム制御メインループ"""
        logger.info(f"Realtime simulator started, will run {self.max_steps} steps at {1/self.dt:.0f} Hz")
        logger.info(f"Control period: {self.dt*1000:.1f}ms")
        
        # 通信スレッド開始
        self.communicator.start_communication()
        
        # リアルタイム制御ループ
        start_time = time.perf_counter()
        next_step_time = start_time
        
        successful_steps = 0
        failed_steps = 0
        
        try:
            for step in range(self.max_steps):
                step_start_time = time.perf_counter()
                
                # 最新のPlant応答を取得
                latest_response = self.communicator.get_latest_response()
                
                if latest_response and latest_response.get('valid', False):
                    # 有効な応答がある場合
                    plant_data = latest_response['plant_response']['y']
                    self.current_altitude = plant_data['position'][2]
                    self.current_velocity = plant_data['velocity'][2]
                    self.current_acceleration = plant_data['acc'][2]
                    self.last_valid_altitude = self.current_altitude
                    self.consecutive_failures = 0
                    communication_status = "OK"
                    rtt_ms = latest_response.get('rtt_ms', 0)
                    successful_steps += 1
                else:
                    # 応答がない場合（遅延またはタイムアウト）
                    self.consecutive_failures += 1
                    communication_status = "TIMEOUT"
                    rtt_ms = 0
                    failed_steps += 1
                    
                    # フォールバック制御（最後の有効値を使用）
                    if self.consecutive_failures > self.max_consecutive_failures:
                        logger.error(f"Too many consecutive failures ({self.consecutive_failures}), using fallback")
                        # 緊急停止またはフェールセーフ制御
                        self.current_altitude = self.last_valid_altitude
                        
                # 制御コマンド生成
                command = self.get_command(step, self.current_altitude)
                
                # 非同期でPlantにコマンド送信
                self.communicator.send_command_async(step, self.sim_time, command)
                
                # ログ記録
                actual_time = time.perf_counter() - start_time
                control_dt = actual_time - self.sim_time if step > 0 else self.dt
                altitude_error = self.controller.setpoint - self.current_altitude
                
                if self.csv_writer:
                    self.csv_writer.writerow([
                        step, self.sim_time, actual_time, control_dt,
                        command[2], self.current_altitude, self.current_velocity, 
                        self.current_acceleration, altitude_error, self.controller.setpoint,
                        communication_status, rtt_ms, self.consecutive_failures
                    ])
                    self.log_fp.flush()
                
                # 進捗表示
                if (step + 1) % 100 == 0:
                    logger.info(f"Step {step + 1}/{self.max_steps}, Alt: {self.current_altitude:.2f}m, "
                              f"Status: {communication_status}, RTT: {rtt_ms:.1f}ms")
                
                # 次のステップ時刻まで待機
                self.sim_time += self.dt
                next_step_time += self.dt
                
                sleep_time = next_step_time - time.perf_counter()
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # 制御周期を逃した場合
                    logger.warning(f"Missed control deadline by {-sleep_time*1000:.1f}ms at step {step}")
                    
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Error in realtime loop: {e}")
        finally:
            self.cleanup()
            
        total_time = time.perf_counter() - start_time
        logger.info(f"Realtime simulation completed: {successful_steps} successful, {failed_steps} failed")
        logger.info(f"Total time: {total_time:.2f}s, Average period: {total_time/self.max_steps*1000:.1f}ms")
        logger.info(f"Communication stats: Sent={self.communicator.sent_count}, "
                   f"Received={self.communicator.received_count}, Timeouts={self.communicator.timeout_count}")
        
        # Print completion notification to stdout (visible in docker logs)
        import sys
        completion_msg = f"""
{'='*60}
🚀 HILS SIMULATION COMPLETED 🚀
{'='*60}
Steps: {successful_steps}/{self.max_steps} successful ({successful_steps/self.max_steps*100:.1f}%)
Runtime: {total_time:.2f}s (Target: {self.max_steps*self.dt:.2f}s)
Real-time factor: {total_time/(self.max_steps*self.dt):.2f}x
Communication: {self.communicator.timeout_count} timeouts
{'='*60}
📊 Run 'make analyze' to view results
{'='*60}
"""
        print(completion_msg, flush=True)
        sys.stdout.flush()
        
    def cleanup(self):
        if hasattr(self, 'log_fp'):
            self.log_fp.close()
        if hasattr(self, 'communicator'):
            self.communicator.stop_communication()
        logger.info("Realtime simulator stopped")


if __name__ == "__main__":
    simulator = RealtimeNumericSimulator()
    simulator.run_realtime()