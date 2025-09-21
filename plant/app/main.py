#!/usr/bin/env python3
import zmq
import json
import yaml
import numpy as np
import os
import sys
import time
import csv
import logging
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleAltitudePlant:
    """シンプルな高度植物モデル（質点の1次元運動）- 動作確認済みモデル"""
    
    def __init__(self, mass: float = 1.0, gravity: float = 9.81):
        self.mass = mass
        self.gravity = gravity
        
        # 状態変数
        self.position = 0.0    # 高度 [m]
        self.velocity = 0.0    # 速度 [m/s]
        self.acceleration = 0.0 # 加速度 [m/s²]
        
    def reset(self, initial_position: float = 0.0, initial_velocity: float = 0.0):
        """植物状態をリセット"""
        self.position = initial_position
        self.velocity = initial_velocity
        self.acceleration = 0.0
        
    def update(self, thrust: float, dt: float) -> Tuple[float, float, float]:
        """植物モデルの更新"""
        # 力の計算: F_thrust - mg = ma
        # thrust: 上向き正、gravity: 下向き正
        net_force = thrust - self.mass * self.gravity
        
        # 加速度の計算
        self.acceleration = net_force / self.mass
        
        # オイラー積分で状態更新
        self.velocity += self.acceleration * dt
        self.position += self.velocity * dt
        
        # センサーノイズを追加（現実的に）
        position_noise = np.random.normal(0, 0.005)  # 0.5cm標準偏差
        velocity_noise = np.random.normal(0, 0.005)  # 0.5cm/s標準偏差
        
        return (
            self.position + position_noise,
            self.velocity + velocity_noise,
            self.acceleration
        )

class PlantSimulator:
    def __init__(self, config_file: str = "config.yaml"):
        self.load_config(config_file)
        self.setup_zmq()
        self.setup_simulation()
        self.setup_logging()
        
    def load_config(self, config_file: str):
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Override with environment variables
        self.bind_address = os.getenv('PLANT_BIND', self.config['plant']['bind_address'])
        self.dt = float(os.getenv('STEP_DT', self.config['plant']['dt']))
        
        # Communication delay settings
        comm_config = self.config.get('communication', {})
        self.enable_delay = comm_config.get('enable_delay', False)
        self.processing_delay = comm_config.get('processing_delay', 0.0) / 1000.0  # ms to s
        self.response_delay = comm_config.get('response_delay', 0.0) / 1000.0      # ms to s
        self.delay_variation = comm_config.get('delay_variation', 0.0) / 1000.0    # ms to s
        
        if self.enable_delay:
            logger.info(f"Communication delay enabled: processing={self.processing_delay*1000:.1f}ms, "
                       f"response={self.response_delay*1000:.1f}ms, variation={self.delay_variation*1000:.1f}ms")
        
        # Create timestamped log directory
        run_id = os.getenv('RUN_ID', time.strftime('%Y%m%d_%H%M%S'))
        log_dir = f"/app/logs/{run_id}"
        self.log_file = f"{log_dir}/plant_log.csv"
        
    def setup_zmq(self):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(self.bind_address)
        logger.info(f"Plant server bound to {self.bind_address}")
        
    def setup_simulation(self):
        sim_config = self.config['simulation']
        mass = sim_config['mass']
        gravity = abs(sim_config['gravity'])  # 正の値として使用
        
        # 動作確認済みの物理モデルを使用
        self.plant = SimpleAltitudePlant(mass=mass, gravity=gravity)
        
        # 初期状態設定
        initial_position = float(sim_config['initial_position'])
        initial_velocity = float(sim_config['initial_velocity'])
        self.plant.reset(initial_position, initial_velocity)
        
        # Simulation time
        self.sim_time = 0.0
        self.step_count = 0
        
    def setup_logging(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self.csv_writer = None
        self.log_fp = open(self.log_file, 'w', newline='')
        self.csv_writer = csv.writer(self.log_fp)
        self.csv_writer.writerow(['seq', 't', 'recv_time', 'send_time', 'thrust', 
                                 'altitude', 'velocity', 'acceleration'])
        
    def simulate_step(self, control_input: List[float]) -> Dict:
        """推力コマンドを受け取り、対応する状態を返す（シンプル化）"""
        # Z軸推力のみ取得
        thrust = control_input[2] if len(control_input) >= 3 else 0.0
        
        # 動作確認済みのplantモデルで状態更新
        measured_position, measured_velocity, acceleration = self.plant.update(thrust, self.dt)
        
        # 時間更新
        self.sim_time += self.dt
        self.step_count += 1
        
        # 標準的なセンサーデータフォーマットで返す
        return {
            "acc": [0.0, 0.0, acceleration + np.random.normal(0, 0.01)],  # Z軸加速度計
            "gyro": [0.0, 0.0, 0.0],  # 回転なし
            "position": [0.0, 0.0, measured_position],  # 高度のみ
            "velocity": [0.0, 0.0, measured_velocity]   # Z軸速度のみ
        }
    
    def run(self):
        logger.info("Plant simulator started")
        try:
            while True:
                # Wait for request
                recv_time = time.time()
                message = self.socket.recv_json()
                
                seq = message.get('seq', 0)
                t = message.get('t', 0.0)
                u = message.get('u', [0.0, 0.0, 0.0])
                
                logger.debug(f"Received: seq={seq}, t={t}, u={u}")
                
                # Simulate processing delay (after receiving command)
                if self.enable_delay and self.processing_delay > 0:
                    # Add random jitter if specified
                    actual_delay = self.processing_delay
                    if self.delay_variation > 0:
                        actual_delay += np.random.uniform(-self.delay_variation, self.delay_variation)
                    if actual_delay > 0:
                        time.sleep(actual_delay)
                
                # Reset state if new simulation starts (seq == 0)
                if seq == 0:
                    sim_config = self.config['simulation']
                    initial_position = float(sim_config['initial_position'])
                    initial_velocity = float(sim_config['initial_velocity'])
                    self.plant.reset(initial_position, initial_velocity)
                    self.sim_time = 0.0
                    self.step_count = 0
                    logger.info("Plant state reset for new simulation")
                
                # Simulate one step
                sensor_data = self.simulate_step(u)
                
                # Prepare response
                response = {
                    "seq": seq,
                    "t": self.sim_time,
                    "y": sensor_data,
                    "valid": True
                }
                
                # Simulate response delay (before sending response)
                if self.enable_delay and self.response_delay > 0:
                    # Add random jitter if specified  
                    actual_delay = self.response_delay
                    if self.delay_variation > 0:
                        actual_delay += np.random.uniform(-self.delay_variation, self.delay_variation)
                    if actual_delay > 0:
                        time.sleep(actual_delay)
                
                send_time = time.time()
                
                # Log data
                if self.csv_writer:
                    thrust = u[2] if len(u) > 2 else 0.0
                    self.csv_writer.writerow([
                        seq, t, recv_time, send_time,
                        thrust, self.plant.position, self.plant.velocity, self.plant.acceleration
                    ])
                    self.log_fp.flush()
                
                # Send response
                self.socket.send_json(response)
                logger.debug(f"Sent: seq={seq}, t={self.sim_time}")
                
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        if self.csv_writer:
            self.log_fp.close()
        self.socket.close()
        self.context.term()
        logger.info("Plant simulator stopped")

if __name__ == "__main__":
    simulator = PlantSimulator()
    simulator.run()