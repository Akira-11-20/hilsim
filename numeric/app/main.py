#!/usr/bin/env python3
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
from typing import Dict, List, Optional

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

class NumericSimulator:
    def __init__(self, config_file: str = "config.yaml"):
        self.load_config(config_file)
        self.setup_zmq()
        self.setup_controller()
        self.setup_logging()
        self.load_scenario()
        
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
        self.log_file = f"{log_dir}/numeric_log.csv"
        
    def setup_zmq(self):
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        self.socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
        self.socket.connect(self.plant_endpoint)
        logger.info(f"Connected to plant at {self.plant_endpoint}")
        
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
                                 'thrust_cmd', 'altitude', 'velocity', 'acceleration',
                                 'altitude_error', 'setpoint'])
    
    def load_scenario(self):
        self.scenario = None
        scenario_config = self.config.get('scenario', {})
        if scenario_config.get('enabled', False):
            scenario_file = scenario_config.get('file')
            if scenario_file and os.path.exists(scenario_file):
                self.scenario = pd.read_csv(scenario_file)
                logger.info(f"Loaded scenario from {scenario_file}")
    
    def get_command(self, step: int, current_altitude: float) -> List[float]:
        """Generate thrust command for altitude control - simplified"""
        # 質量は設定から取得（通常は1.0kg）
        mass = 1.0  # または self.config から取得可能
        gravity = 9.81
        
        if self.scenario is not None:
            # Find the appropriate scenario command for this step
            scenario_row = None
            for _, row in self.scenario.iterrows():
                if row['step'] <= step:
                    scenario_row = row
                else:
                    break
            
            if scenario_row is not None:
                cmd_type = scenario_row.get('cmd_type', 'position')
                cmd_z = scenario_row.get('cmd_z', 10.0)  # Default altitude
                
                if cmd_type == 'force':
                    # Direct thrust command
                    thrust = cmd_z
                    return [0.0, 0.0, thrust]
                else:  # cmd_type == 'position' or default
                    # Altitude setpoint command - use PID controller
                    self.controller.setpoint = cmd_z
                    pid_output = self.controller.update(current_altitude, self.dt)
                    thrust = pid_output + mass * gravity  # 正しい重力補償
                    return [0.0, 0.0, thrust]
        
        # Default: PID controller with proper gravity compensation
        pid_output = self.controller.update(current_altitude, self.dt)
        thrust = pid_output + mass * gravity  # mg分の重力補償
        
        # 推力制限（現実的な範囲）
        max_thrust = 1000.0  # 最大推力 [N]
        thrust = np.clip(thrust, 0, max_thrust)
        
        return [0.0, 0.0, thrust]
    
    def send_receive(self, seq: int, t: float, command: List[float]) -> Optional[Dict]:
        """Send command and receive response"""
        try:
            request = {
                "seq": seq,
                "t": t,
                "u": command
            }
            
            send_time = time.time()
            self.socket.send_json(request)
            
            response = self.socket.recv_json()
            recv_time = time.time()
            
            rtt_ms = (recv_time - send_time) * 1000
            
            return {
                'response': response,
                'send_time': send_time,
                'recv_time': recv_time,
                'rtt_ms': rtt_ms
            }
            
        except zmq.Again:
            logger.error(f"Timeout on step {seq}")
            return None
        except Exception as e:
            logger.error(f"Communication error on step {seq}: {e}")
            return None
    
    def run(self):
        logger.info(f"Numeric simulator started, will run {self.max_steps} steps")
        
        # State tracking
        current_altitude = 0.0
        sim_time = 0.0
        successful_steps = 0
        failed_steps = 0
        
        try:
            for step in range(self.max_steps):
                # Generate control command (thrust)
                command = self.get_command(step, current_altitude)
                
                # Communication with plant
                result = self.send_receive(step, sim_time, command)
                
                if result is None:
                    failed_steps += 1
                    logger.warning(f"Step {step} failed")
                    continue
                
                response = result['response']
                
                # Extract plant response
                if not response.get('valid', False):
                    failed_steps += 1
                    logger.warning(f"Plant returned invalid response at step {step}")
                    continue
                
                y = response['y']
                plant_pos = y.get('position', [0.0, 0.0, 0.0])
                plant_vel = y.get('velocity', [0.0, 0.0, 0.0])
                plant_acc = y.get('acc', [0.0, 0.0, 0.0])
                
                # Extract altitude (Z-axis)
                current_altitude = plant_pos[2]
                current_velocity = plant_vel[2]
                current_acceleration = plant_acc[2]
                
                # Calculate altitude error
                altitude_error = self.controller.setpoint - current_altitude
                
                # Log data
                if self.csv_writer:
                    self.csv_writer.writerow([
                        step, sim_time, result['send_time'], result['recv_time'], result['rtt_ms'],
                        command[2],  # thrust_cmd
                        current_altitude, current_velocity, current_acceleration,
                        altitude_error, self.controller.setpoint
                    ])
                    self.log_fp.flush()
                
                successful_steps += 1
                sim_time += self.dt
                
                # Progress logging
                if (step + 1) % 100 == 0:
                    logger.info(f"Completed {step + 1}/{self.max_steps} steps, RTT: {result['rtt_ms']:.2f}ms")
                    
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()
            
        logger.info(f"Simulation completed: {successful_steps} successful, {failed_steps} failed")
        
    def cleanup(self):
        if hasattr(self, 'log_fp'):
            self.log_fp.close()
        self.socket.close()
        self.context.term()
        logger.info("Numeric simulator stopped")

if __name__ == "__main__":
    simulator = NumericSimulator()
    simulator.run()