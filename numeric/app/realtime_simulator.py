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
    """非同期Plant通信クラス"""
    
    def __init__(self, plant_endpoint: str, timeout_ms: int):
        self.plant_endpoint = plant_endpoint
        self.timeout_ms = timeout_ms
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        self.socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
        self.socket.connect(plant_endpoint)
        
        # 通信管理
        self.request_queue = Queue()
        self.response_queue = Queue()
        self.latest_response = None
        self.communication_thread = None
        self.running = False
        self.seq_counter = 0
        
        # 統計
        self.sent_count = 0
        self.received_count = 0
        self.timeout_count = 0
        
        logger.info(f"AsyncPlantCommunicator connected to {plant_endpoint}")
        
    def start_communication(self):
        """通信スレッドを開始"""
        self.running = True
        self.communication_thread = threading.Thread(target=self._communication_loop)
        self.communication_thread.daemon = True
        self.communication_thread.start()
        logger.info("Async communication thread started")
        
    def stop_communication(self):
        """通信スレッドを停止"""
        self.running = False
        if self.communication_thread:
            self.communication_thread.join(timeout=1.0)
        self.socket.close()
        self.context.term()
        logger.info("Async communication stopped")
        
    def send_command_async(self, seq: int, sim_time: float, command: List[float]):
        """非同期でコマンドを送信（ノンブロッキング）"""
        request = {
            "seq": seq,
            "t": sim_time,
            "u": command,
            "send_time": time.time()
        }
        try:
            self.request_queue.put_nowait(request)
        except:
            logger.warning(f"Request queue full, dropping command for seq={seq}")
            
    def get_latest_response(self) -> Optional[Dict]:
        """最新の応答を取得（ノンブロッキング）"""
        try:
            # キューから最新の応答を取得
            while True:
                try:
                    self.latest_response = self.response_queue.get_nowait()
                except Empty:
                    break
        except:
            pass
            
        return self.latest_response
        
    def _communication_loop(self):
        """通信スレッドのメインループ"""
        logger.info("Communication loop started")
        
        while self.running:
            try:
                # リクエストを待機（タイムアウト付き）
                try:
                    request = self.request_queue.get(timeout=0.1)
                except Empty:
                    continue
                    
                # Plantに送信
                try:
                    send_time = time.perf_counter()
                    self.socket.send_json(request)
                    self.sent_count += 1
                    
                    # 応答受信
                    response_raw = self.socket.recv_json()
                    recv_time = time.perf_counter()
                    
                    # 応答データに統計情報を追加
                    response = {
                        'plant_response': response_raw,
                        'seq': request['seq'],
                        'sim_time': request['t'],
                        'command': request['u'],
                        'send_time': request['send_time'],
                        'recv_time': time.time(),
                        'rtt_ms': (recv_time - send_time) * 1000,
                        'valid': response_raw.get('valid', False)
                    }
                    
                    # 応答をキューに追加
                    try:
                        self.response_queue.put_nowait(response)
                        self.received_count += 1
                    except:
                        # キューが満杯の場合は古い応答を破棄
                        try:
                            self.response_queue.get_nowait()
                            self.response_queue.put_nowait(response)
                        except:
                            pass
                            
                except zmq.Again:
                    self.timeout_count += 1
                    logger.warning(f"Plant communication timeout for seq={request['seq']}")
                except Exception as e:
                    logger.error(f"Communication error: {e}")
                    
            except Exception as e:
                logger.error(f"Communication loop error: {e}")
                time.sleep(0.01)
                
        logger.info("Communication loop stopped")


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
        self.communicator = AsyncPlantCommunicator(self.plant_endpoint, self.timeout_ms)
        
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