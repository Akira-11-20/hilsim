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

class PIDController:
    def __init__(self, kp: float, ki: float, kd: float, setpoint: List[float]):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.setpoint = np.array(setpoint, dtype=np.float64)
        
        self.error_sum = np.zeros(3)
        self.prev_error = np.zeros(3)
        self.prev_time = None
        
    def update(self, current_pos: np.ndarray, dt: float) -> np.ndarray:
        error = self.setpoint - current_pos
        
        if self.prev_time is None:
            self.prev_error = error
            
        # PID calculation
        self.error_sum += error * dt
        error_diff = (error - self.prev_error) / dt if dt > 0 else np.zeros(3)
        
        output = (self.kp * error + 
                 self.ki * self.error_sum + 
                 self.kd * error_diff)
        
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
        self.controller = PIDController(
            kp=ctrl_config['kp'],
            ki=ctrl_config['ki'], 
            kd=ctrl_config['kd'],
            setpoint=ctrl_config['setpoint']
        )
        
    def setup_logging(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self.log_fp = open(self.log_file, 'w', newline='')
        self.csv_writer = csv.writer(self.log_fp)
        self.csv_writer.writerow(['seq', 't', 'send_time', 'recv_time', 'rtt_ms',
                                 'cmd_x', 'cmd_y', 'cmd_z',
                                 'pos_x', 'pos_y', 'pos_z', 
                                 'vel_x', 'vel_y', 'vel_z',
                                 'acc_x', 'acc_y', 'acc_z',
                                 'gyro_x', 'gyro_y', 'gyro_z',
                                 'error_x', 'error_y', 'error_z'])
    
    def load_scenario(self):
        self.scenario = None
        scenario_config = self.config.get('scenario', {})
        if scenario_config.get('enabled', False):
            scenario_file = scenario_config.get('file')
            if scenario_file and os.path.exists(scenario_file):
                self.scenario = pd.read_csv(scenario_file)
                logger.info(f"Loaded scenario from {scenario_file}")
    
    def get_command(self, step: int, current_pos: np.ndarray) -> np.ndarray:
        """Generate control command"""
        if self.scenario is not None and step < len(self.scenario):
            # Use predefined scenario
            row = self.scenario.iloc[step]
            return np.array([row.get('cmd_x', 0.0), row.get('cmd_y', 0.0), row.get('cmd_z', 0.0)])
        else:
            # Use PID controller
            return self.controller.update(current_pos, self.dt)
    
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
        current_pos = np.zeros(3)
        sim_time = 0.0
        successful_steps = 0
        failed_steps = 0
        
        try:
            for step in range(self.max_steps):
                # Generate control command
                command = self.get_command(step, current_pos)
                
                # Communication with plant
                result = self.send_receive(step, sim_time, command.tolist())
                
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
                plant_pos = np.array(y.get('position', [0.0, 0.0, 0.0]))
                plant_vel = np.array(y.get('velocity', [0.0, 0.0, 0.0]))
                plant_acc = np.array(y.get('acc', [0.0, 0.0, 0.0]))
                plant_gyro = np.array(y.get('gyro', [0.0, 0.0, 0.0]))
                
                # Update state for next iteration
                current_pos = plant_pos
                
                # Calculate error
                error = self.controller.setpoint - current_pos
                
                # Log data
                if self.csv_writer:
                    self.csv_writer.writerow([
                        step, sim_time, result['send_time'], result['recv_time'], result['rtt_ms'],
                        command[0], command[1], command[2],
                        plant_pos[0], plant_pos[1], plant_pos[2],
                        plant_vel[0], plant_vel[1], plant_vel[2],
                        plant_acc[0], plant_acc[1], plant_acc[2],
                        plant_gyro[0], plant_gyro[1], plant_gyro[2],
                        error[0], error[1], error[2]
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