#!/usr/bin/env python3
"""
Fixed Plant Server - REQ/REP Based

RTT調査結果に基づきPUB/SUBからREQ/REPに変更
安定した1.7ms RTTを実現する修正版Plant実装
"""

import zmq
import time
import json
import numpy as np
from typing import Dict, List, Optional

class FixedPlantServer:
    """
    修正版Plant - REQサーバー実装

    Numeric側からのREQUESTに対してREPLYで状態データを返す
    communication_test_containersで実証された安定通信パターン
    """

    def __init__(self, port: int = 5555):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)

        # Physics simulation
        self.position = 0.0
        self.velocity = 0.0
        self.acceleration = 0.0
        self.mass = 1.0
        self.gravity = 9.81
        self.dt = 0.02  # 50Hz

        # Control
        self.thrust = 0.0

        # Statistics
        self.step_count = 0
        self.message_count = 0

    def start_server(self):
        """サーバー開始"""
        self.socket.bind(f"tcp://*:{self.port}")
        print(f"Fixed Plant Server started on port {self.port}")
        print("Waiting for requests from Numeric...")

        try:
            while True:
                # Receive request from Numeric
                request_str = self.socket.recv_string()
                recv_time = time.perf_counter()
                recv_wall_time = time.time()

                try:
                    request = json.loads(request_str)

                    # Extract control command
                    thrust_cmd = request.get('thrust', 0.0)
                    seq = request.get('seq', self.message_count)
                    client_send_time = request.get('send_time', recv_time)

                    # Update control input
                    self.thrust = thrust_cmd

                    # Physics simulation step
                    self.simulate_physics()

                    # Prepare response with state data and timing
                    response = {
                        'seq': seq,
                        'step': self.step_count,
                        'position': self.position,
                        'velocity': self.velocity,
                        'acceleration': self.acceleration,
                        'thrust': self.thrust,
                        'client_send_time': client_send_time,
                        'server_recv_time': recv_time,
                        'server_wall_time': recv_wall_time,
                        'server_send_time': time.perf_counter(),
                        'message_count': self.message_count
                    }

                    # Send response
                    self.socket.send_string(json.dumps(response))

                    self.message_count += 1

                    # Progress logging
                    if self.message_count % 100 == 0:
                        print(f"Plant: Processed {self.message_count} requests, "
                              f"Position: {self.position:.2f}m, Thrust: {self.thrust:.2f}N")

                except json.JSONDecodeError:
                    # Error response
                    error_response = {
                        'error': 'Invalid JSON',
                        'message_count': self.message_count
                    }
                    self.socket.send_string(json.dumps(error_response))

        except KeyboardInterrupt:
            print(f"\nShutting down after {self.message_count} messages")
        finally:
            self.cleanup()

    def simulate_physics(self):
        """物理シミュレーション 1ステップ"""
        # Force calculation: F_net = F_thrust - mg
        net_force = self.thrust - self.mass * self.gravity

        # Acceleration: a = F_net / m
        self.acceleration = net_force / self.mass

        # Integration: v = v0 + a*dt, x = x0 + v*dt
        self.velocity += self.acceleration * self.dt
        self.position += self.velocity * self.dt

        self.step_count += 1

    def cleanup(self):
        """リソース解放"""
        self.socket.close()
        self.context.term()
        print("Plant server stopped")

def main():
    server = FixedPlantServer()
    server.start_server()

if __name__ == "__main__":
    main()