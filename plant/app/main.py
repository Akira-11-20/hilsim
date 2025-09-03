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
        self.mass = sim_config['mass']
        self.gravity = sim_config['gravity']
        
        # State variables
        self.position = np.array(sim_config['initial_position'], dtype=np.float64)
        self.velocity = np.array(sim_config['initial_velocity'], dtype=np.float64)
        self.acceleration = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        
        # Simulation time
        self.sim_time = 0.0
        self.step_count = 0
        
    def setup_logging(self):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self.csv_writer = None
        self.log_fp = open(self.log_file, 'w', newline='')
        self.csv_writer = csv.writer(self.log_fp)
        self.csv_writer.writerow(['seq', 't', 'recv_time', 'send_time', 'u1', 'u2', 'u3', 
                                 'pos_x', 'pos_y', 'pos_z', 'vel_x', 'vel_y', 'vel_z',
                                 'acc_x', 'acc_y', 'acc_z'])
        
    def simulate_step(self, control_input: List[float]) -> Dict:
        """Simple 3DOF point mass dynamics"""
        u = np.array(control_input[:3], dtype=np.float64)
        
        # Force = mass * acceleration + gravity
        force_gravity = np.array([0.0, 0.0, self.mass * self.gravity])
        force_control = u
        total_force = force_control + force_gravity
        
        # Update acceleration
        self.acceleration = total_force / self.mass
        
        # Euler integration
        self.velocity += self.acceleration * self.dt
        self.position += self.velocity * self.dt
        
        # Update time
        self.sim_time += self.dt
        self.step_count += 1
        
        # Simulate IMU measurements (acceleration + noise)
        imu_acc = self.acceleration + np.random.normal(0, 0.01, 3)
        imu_gyro = np.random.normal(0, 0.001, 3)  # Simple noise model
        
        return {
            "acc": imu_acc.tolist(),
            "gyro": imu_gyro.tolist(),
            "position": self.position.tolist(),
            "velocity": self.velocity.tolist()
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
                
                # Simulate one step
                sensor_data = self.simulate_step(u)
                
                # Prepare response
                response = {
                    "seq": seq,
                    "t": self.sim_time,
                    "y": sensor_data,
                    "valid": True
                }
                
                send_time = time.time()
                
                # Log data
                if self.csv_writer:
                    self.csv_writer.writerow([
                        seq, t, recv_time, send_time,
                        u[0] if len(u) > 0 else 0.0,
                        u[1] if len(u) > 1 else 0.0, 
                        u[2] if len(u) > 2 else 0.0,
                        self.position[0], self.position[1], self.position[2],
                        self.velocity[0], self.velocity[1], self.velocity[2],
                        self.acceleration[0], self.acceleration[1], self.acceleration[2]
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