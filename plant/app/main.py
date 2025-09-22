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
        
        # Independent simulation state
        self.current_thrust = 0.0
        self.step_count = 0
        self.sim_time = 0.0
        self.max_steps = int(os.getenv('MAX_STEPS', 4000))
        
        # Command queue for delayed processing
        self.command_queue = []
        
        # RTT measurement
        self.latest_command_timestamp = 0.0
        self.latest_command_seq = -1

        # Synchronized timing
        self.sync_base_time = None
        self.is_synchronized = False
        
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
        
        # State publisher (Plant → Numeric)
        self.state_publisher = self.context.socket(zmq.PUB)
        self.state_publisher.bind("tcp://*:5555")
        
        # Command subscriber (Numeric → Plant)
        self.cmd_subscriber = self.context.socket(zmq.SUB)
        self.cmd_subscriber.connect("tcp://numeric:5556")
        self.cmd_subscriber.setsockopt(zmq.SUBSCRIBE, b"")
        self.cmd_subscriber.setsockopt(zmq.RCVTIMEO, 1)  # 1ms timeout
        
        logger.info(f"Plant async communication setup: PUB on :5555, SUB on numeric:5556")

        # Allow ZMQ connections to establish
        time.sleep(1.0)
        
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
                                 'altitude', 'velocity', 'acceleration',
                                 'step_start_sync', 'step_start_wall', 'sync_base_time'])

    def get_sync_timestamp(self):
        """同期基準時刻からの相対時間を取得"""
        if not self.is_synchronized:
            return 0.0  # 同期前は0を返す
        return time.time() - self.sync_base_time

    def handle_sync_protocol(self, msg):
        """同期プロトコルメッセージを処理"""
        command = msg.get("command")

        if command == "READY":
            # READY_ACK を送信
            ack_msg = {
                "command": "READY_ACK",
                "sender": "plant",
                "timestamp": time.time()
            }
            self.state_publisher.send_json(ack_msg)
            logger.info("Sent READY_ACK to Numeric")

        elif command == "SYNC_START":
            # 同期基準時刻を設定
            self.sync_base_time = msg.get("sync_base_time")
            if self.sync_base_time:
                # 同期時刻まで待機
                while time.time() < self.sync_base_time:
                    time.sleep(0.001)
                self.is_synchronized = True
                logger.info(f"Synchronization established, base time: {self.sync_base_time}")
            else:
                logger.error("SYNC_START message missing sync_base_time")

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
    
    def receive_commands(self):
        """Non-blocking command reception with delay simulation"""
        try:
            while True:
                try:
                    cmd_msg = self.cmd_subscriber.recv_json(zmq.NOBLOCK)
                    recv_time = time.time()

                    # Check for synchronization protocol messages
                    if cmd_msg.get("command") in ["READY", "SYNC_START"]:
                        self.handle_sync_protocol(cmd_msg)
                        continue

                    # Track latest command for RTT measurement
                    self.latest_command_timestamp = cmd_msg.get('timestamp', recv_time)
                    self.latest_command_seq = cmd_msg.get('seq', 0)
                    
                    if self.enable_delay:
                        # Calculate total delay
                        total_delay = self.processing_delay + self.response_delay
                        if self.delay_variation > 0:
                            total_delay += np.random.uniform(-self.delay_variation, self.delay_variation)
                        
                        # Queue command with application time
                        apply_time = recv_time + total_delay
                        self.command_queue.append({
                            'thrust': cmd_msg.get('u', [0.0, 0.0, 0.0])[2],
                            'apply_time': apply_time,
                            'seq': cmd_msg.get('seq', 0),
                            'original_timestamp': self.latest_command_timestamp
                        })
                    else:
                        # Apply immediately if no delay
                        self.current_thrust = cmd_msg.get('u', [0.0, 0.0, 0.0])[2]
                        
                except zmq.Again:
                    break  # No more messages
        except Exception as e:
            logger.warning(f"Error receiving commands: {e}")
    
    def process_delayed_commands(self):
        """Apply commands that have passed their delay time"""
        current_time = time.time()
        applied_commands = []
        
        for cmd in self.command_queue:
            if current_time >= cmd['apply_time']:
                self.current_thrust = cmd['thrust']
                applied_commands.append(cmd)
                
        # Remove applied commands
        for cmd in applied_commands:
            self.command_queue.remove(cmd)
    
    def broadcast_state(self):
        """Broadcast current plant state with RTT info and simulated response delay"""
        # Calculate effective timestamp to include response delay for RTT calculation
        current_time = time.time()
        effective_timestamp = current_time

        if self.enable_delay and self.response_delay > 0:
            # Add response delay to timestamp for RTT calculation without blocking
            delay_time = self.response_delay
            if self.delay_variation > 0:
                delay_time += np.random.uniform(-self.delay_variation, self.delay_variation)
            effective_timestamp = current_time + delay_time

        state_msg = {
            "seq": self.step_count,
            "t": self.sim_time,
            "y": {
                "acc": [0.0, 0.0, self.plant.acceleration],
                "gyro": [0.0, 0.0, 0.0],
                "position": [0.0, 0.0, self.plant.position],
                "velocity": [0.0, 0.0, self.plant.velocity]
            },
            "valid": True,
            "timestamp": effective_timestamp,  # Use effective timestamp for RTT
            "sync_timestamp": self.get_sync_timestamp(),  # Synchronized timestamp
            "is_synchronized": self.is_synchronized,
            # RTT measurement data
            "latest_cmd_timestamp": self.latest_command_timestamp,
            "latest_cmd_seq": self.latest_command_seq
        }

        self.state_publisher.send_json(state_msg)
    
    def wait_for_synchronization(self):
        """Wait for synchronization protocol from Numeric"""
        logger.info("Waiting for synchronization protocol from Numeric...")

        timeout_start = time.time()
        while not self.is_synchronized and (time.time() - timeout_start) < 30.0:
            try:
                cmd_msg = self.cmd_subscriber.recv_json(zmq.NOBLOCK)
                if cmd_msg.get("command") in ["READY", "SYNC_START"]:
                    self.handle_sync_protocol(cmd_msg)
            except zmq.Again:
                time.sleep(0.01)

        if not self.is_synchronized:
            logger.warning("Synchronization timeout - continuing without sync")

    def run(self):
        """Independent simulation loop"""
        logger.info(f"Plant independent simulation started: {self.max_steps} steps at {1/self.dt:.0f} Hz")

        # Wait for synchronization from Numeric
        self.wait_for_synchronization()

        # Reset plant for new simulation
        sim_config = self.config['simulation']
        initial_position = float(sim_config['initial_position'])
        initial_velocity = float(sim_config['initial_velocity'])
        self.plant.reset(initial_position, initial_velocity)

        try:
            start_time = time.perf_counter()
            
            for step in range(self.max_steps):
                step_start = time.perf_counter()
                step_start_sync = self.get_sync_timestamp()
                step_start_wall = time.time()

                self.step_count = step
                self.sim_time = step * self.dt

                # Process any delayed commands
                self.process_delayed_commands()

                # Receive new commands (non-blocking)
                self.receive_commands()

                # Update plant physics
                position, velocity, acceleration = self.plant.update(self.current_thrust, self.dt)

                # Broadcast state to Numeric
                self.broadcast_state()

                # Log data with sync verification timestamps
                if self.csv_writer:
                    current_time = time.time()
                    self.csv_writer.writerow([
                        step, self.sim_time, current_time, current_time,
                        self.current_thrust, position, velocity, acceleration,
                        step_start_sync, step_start_wall, self.sync_base_time
                    ])
                    self.log_fp.flush()
                
                # Progress logging
                if (step + 1) % 500 == 0:
                    logger.info(f"Plant step {step + 1}/{self.max_steps}, Alt: {position:.2f}m, Thrust: {self.current_thrust:.1f}N")
                
                # Fixed timestep
                elapsed = time.perf_counter() - step_start
                sleep_time = self.dt - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    logger.warning(f"Plant missed timestep by {-sleep_time*1000:.1f}ms at step {step}")
            
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
        if self.csv_writer:
            self.log_fp.close()
        self.state_publisher.close()
        self.cmd_subscriber.close()
        self.context.term()
        logger.info("Plant simulator stopped")

if __name__ == "__main__":
    simulator = PlantSimulator()
    simulator.run()