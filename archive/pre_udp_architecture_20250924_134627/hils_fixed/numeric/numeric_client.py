#!/usr/bin/env python3
"""
Fixed Numeric Client - REQ/REP Based

RTT調査結果に基づく修正版Numeric実装
安定したRTT測定とリアルタイム制御を実現
"""

import zmq
import time
import json
import numpy as np
import csv
import os
from datetime import datetime
from typing import Dict, List, Optional

class FixedNumericClient:
    """
    修正版Numeric - REQクライアント実装

    Plant側にREQUESTを送信してREPLYで状態データを受信
    調査で実証された安定通信パターンを使用
    """

    def __init__(self, plant_endpoint: str = "tcp://plant:5555"):
        self.plant_endpoint = plant_endpoint
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)

        # Control parameters
        self.dt = 0.02  # 50Hz control loop
        self.setpoint = 10.0  # Target altitude [m]

        # PID Controller
        self.kp = 18.0  # Proportional gain
        self.ki = 2.0   # Integral gain
        self.kd = 8.0   # Derivative gain

        self.error_integral = 0.0
        self.prev_error = 0.0

        # RTT measurement
        self.rtt_measurements = []
        self.request_times = {}

        # Statistics
        self.step_count = 0
        self.timeout_count = 0

        # CSV logging
        self.csv_file = None
        self.csv_writer = None

    def connect(self):
        """Plant サーバーに接続"""
        self.socket.connect(self.plant_endpoint)
        self.socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout
        print(f"Fixed Numeric connected to {self.plant_endpoint}")

    def setup_logging(self, run_id: str):
        """CSVログ設定"""
        log_dir = f"logs/{run_id}"
        os.makedirs(log_dir, exist_ok=True)

        log_file_path = os.path.join(log_dir, "fixed_numeric_log.csv")
        self.csv_file = open(log_file_path, 'w', newline='')

        fieldnames = [
            'seq', 'sim_time', 'actual_time', 'control_dt',
            'thrust_cmd', 'altitude', 'velocity', 'acceleration',
            'altitude_error', 'setpoint', 'communication_status',
            'rtt_ms', 'client_send_time', 'server_recv_time',
            'client_recv_time', 'timeout_count'
        ]

        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=fieldnames)
        self.csv_writer.writeheader()

        print(f"Logging to: {log_file_path}")

    def pid_control(self, current_altitude: float) -> float:
        """PID制御計算"""
        error = self.setpoint - current_altitude

        # Integral
        self.error_integral += error * self.dt

        # Derivative
        error_derivative = (error - self.prev_error) / self.dt
        self.prev_error = error

        # PID output
        thrust = (self.kp * error +
                 self.ki * self.error_integral +
                 self.kd * error_derivative)

        # Anti-windup
        thrust = max(0.0, min(thrust, 100.0))

        return thrust

    def run_control_loop(self, num_steps: int = 4000):
        """リアルタイム制御ループ"""
        print(f"Starting fixed control loop: {num_steps} steps at 50Hz")

        start_time = time.perf_counter()
        run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.setup_logging(run_id)

        try:
            for step in range(num_steps):
                step_start = time.perf_counter()

                # Send request to Plant
                send_time = time.perf_counter()
                send_wall_time = time.time()

                # Calculate control (based on previous state or initial values)
                if step == 0:
                    current_altitude = 0.0  # Initial condition
                else:
                    current_altitude = getattr(self, 'last_altitude', 0.0)

                thrust_cmd = self.pid_control(current_altitude)

                request = {
                    'seq': step,
                    'thrust': thrust_cmd,
                    'send_time': send_time,
                    'wall_time': send_wall_time,
                    'setpoint': self.setpoint
                }

                self.request_times[step] = send_time

                try:
                    # Send request
                    self.socket.send_string(json.dumps(request))

                    # Receive response
                    response_str = self.socket.recv_string()
                    recv_time = time.perf_counter()
                    recv_wall_time = time.time()

                    # Parse response
                    response = json.loads(response_str)

                    # Extract state
                    altitude = response.get('position', 0.0)
                    velocity = response.get('velocity', 0.0)
                    acceleration = response.get('acceleration', 0.0)
                    self.last_altitude = altitude

                    # Calculate RTT
                    client_send_time = response.get('client_send_time', send_time)
                    rtt_ms = (recv_time - send_time) * 1000.0
                    self.rtt_measurements.append(rtt_ms)

                    # Log data
                    actual_time = recv_time - start_time
                    altitude_error = self.setpoint - altitude

                    if self.csv_writer:
                        self.csv_writer.writerow({
                            'seq': step,
                            'sim_time': step * self.dt,
                            'actual_time': actual_time,
                            'control_dt': self.dt,
                            'thrust_cmd': thrust_cmd,
                            'altitude': altitude,
                            'velocity': velocity,
                            'acceleration': acceleration,
                            'altitude_error': altitude_error,
                            'setpoint': self.setpoint,
                            'communication_status': 'OK',
                            'rtt_ms': rtt_ms,
                            'client_send_time': send_time,
                            'server_recv_time': response.get('server_recv_time', 0),
                            'client_recv_time': recv_time,
                            'timeout_count': self.timeout_count
                        })

                    # Progress logging
                    if (step + 1) % 100 == 0:
                        recent_rtts = self.rtt_measurements[-100:]
                        avg_rtt = np.mean(recent_rtts)
                        std_rtt = np.std(recent_rtts)
                        print(f"Step {step+1}/{num_steps}: Alt={altitude:.2f}m, "
                              f"RTT={rtt_ms:.2f}ms, Avg RTT={avg_rtt:.2f}±{std_rtt:.2f}ms")

                except zmq.Again:
                    # Timeout
                    print(f"Timeout on step {step}")
                    self.timeout_count += 1

                    if self.csv_writer:
                        self.csv_writer.writerow({
                            'seq': step,
                            'sim_time': step * self.dt,
                            'actual_time': time.perf_counter() - start_time,
                            'control_dt': self.dt,
                            'thrust_cmd': thrust_cmd,
                            'altitude': 0.0,
                            'velocity': 0.0,
                            'acceleration': 0.0,
                            'altitude_error': self.setpoint,
                            'setpoint': self.setpoint,
                            'communication_status': 'TIMEOUT',
                            'rtt_ms': 0.0,
                            'client_send_time': send_time,
                            'server_recv_time': 0,
                            'client_recv_time': 0,
                            'timeout_count': self.timeout_count
                        })

                # Fixed timing control (50Hz)
                elapsed = time.perf_counter() - step_start
                sleep_time = max(0, self.dt - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("Control loop interrupted")
        finally:
            self.cleanup_logging()

        # Final statistics
        total_time = time.perf_counter() - start_time
        self.print_final_stats(total_time, num_steps)

    def print_final_stats(self, total_time: float, num_steps: int):
        """最終統計表示"""
        print(f"\n{'='*60}")
        print(f"FIXED HILS CONTROL COMPLETED")
        print(f"{'='*60}")
        print(f"Steps: {num_steps - self.timeout_count}/{num_steps} successful")
        print(f"Runtime: {total_time:.2f}s (Target: {num_steps * self.dt:.2f}s)")
        print(f"Real-time factor: {total_time / (num_steps * self.dt):.2f}x")
        print(f"Timeouts: {self.timeout_count}")

        if self.rtt_measurements:
            print(f"RTT Mean: {np.mean(self.rtt_measurements):.3f}ms")
            print(f"RTT Std: {np.std(self.rtt_measurements):.3f}ms")
            print(f"RTT Range: {np.min(self.rtt_measurements):.3f}-{np.max(self.rtt_measurements):.3f}ms")

    def cleanup_logging(self):
        """ログファイル終了"""
        if self.csv_file:
            self.csv_file.close()

    def cleanup(self):
        """リソース解放"""
        self.cleanup_logging()
        self.socket.close()
        self.context.term()

def main():
    client = FixedNumericClient()
    client.connect()

    try:
        client.run_control_loop(num_steps=500)  # Test with 500 steps
    finally:
        client.cleanup()

if __name__ == "__main__":
    main()