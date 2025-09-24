#!/usr/bin/env python3
"""
PUB/SUB RTT Measurement Test

REQ/REPで成功したRTT測定をPUB/SUBパターンに適用
RTT増加問題がPUB/SUBで発生するかを確認
"""

import zmq
import time
import json
import numpy as np
import threading
import csv
import os
from datetime import datetime
from typing import List, Dict

class PubSubRTTServer:
    """PUB/SUB RTT測定サーバー (Plant相当)"""

    def __init__(self, state_port: int = 5570, cmd_port: int = 5571):
        self.state_port = state_port
        self.cmd_port = cmd_port
        self.context = zmq.Context()

        # State publisher (Plant → Numeric)
        self.state_publisher = self.context.socket(zmq.PUB)
        self.state_publisher.bind(f"tcp://127.0.0.1:{state_port}")

        # Command subscriber (Numeric → Plant)
        self.cmd_subscriber = self.context.socket(zmq.SUB)
        self.cmd_subscriber.setsockopt(zmq.SUBSCRIBE, b"")
        self.cmd_subscriber.setsockopt(zmq.RCVTIMEO, 10)  # 10ms timeout

        self.running = False
        self.message_count = 0
        self.latest_command = None

    def start(self):
        """サーバー開始"""
        print(f"PUB/SUB Server: PUB on {self.state_port}, SUB on {self.cmd_port}")
        self.running = True

        # Connect to client's command publisher
        self.cmd_subscriber.connect(f"tcp://127.0.0.1:{self.cmd_port}")

        # ZeroMQ connection establishment
        time.sleep(1.0)

        try:
            # Simulation loop (like original plant)
            for step in range(500):
                step_start_time = time.perf_counter()

                # Check for commands (non-blocking)
                try:
                    cmd_str = self.cmd_subscriber.recv_string(zmq.NOBLOCK)
                    cmd_recv_time = time.perf_counter()

                    cmd = json.loads(cmd_str)
                    self.latest_command = {
                        **cmd,
                        'recv_time': cmd_recv_time,
                        'recv_wall_time': time.time()
                    }

                except zmq.Again:
                    # No command received
                    pass
                except json.JSONDecodeError:
                    pass

                # Simple processing delay
                time.sleep(0.001)  # 1ms processing

                # Broadcast state with timing info
                state_data = {
                    'seq': step,
                    'server_step_start': step_start_time,
                    'server_wall_time': time.time(),
                    'latest_cmd': self.latest_command,
                    'message_count': self.message_count
                }

                self.state_publisher.send_string(json.dumps(state_data))
                self.message_count += 1

                # Progress
                if (step + 1) % 100 == 0:
                    print(f"Server: Published {step + 1} states")

                # Fixed timing (20ms like original HILS)
                elapsed = time.perf_counter() - step_start_time
                sleep_time = max(0, 0.02 - elapsed)  # 50Hz
                time.sleep(sleep_time)

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """リソース解放"""
        self.state_publisher.close()
        self.cmd_subscriber.close()
        self.context.term()
        print(f"Server stopped after {self.message_count} messages")

class PubSubRTTClient:
    """PUB/SUB RTT測定クライアント (Numeric相当)"""

    def __init__(self, state_port: int = 5570, cmd_port: int = 5571):
        self.state_port = state_port
        self.cmd_port = cmd_port
        self.context = zmq.Context()

        # State subscriber (Plant → Numeric)
        self.state_subscriber = self.context.socket(zmq.SUB)
        self.state_subscriber.connect(f"tcp://127.0.0.1:{state_port}")
        self.state_subscriber.setsockopt(zmq.SUBSCRIBE, b"")
        self.state_subscriber.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout

        # Command publisher (Numeric → Plant)
        self.cmd_publisher = self.context.socket(zmq.PUB)
        self.cmd_publisher.bind(f"tcp://127.0.0.1:{cmd_port}")

        self.measurements = []
        self.command_timestamps = {}  # seq -> send_time mapping

    def connect(self):
        """接続・初期化"""
        print("PUB/SUB Client connected")
        # ZeroMQ connection establishment
        time.sleep(1.0)

    def run_test(self, num_messages: int = 500) -> List[Dict]:
        """PUB/SUB RTT測定テスト"""
        print(f"Starting PUB/SUB RTT test: {num_messages} messages")

        for i in range(num_messages):
            # Send command with high precision timing
            cmd_send_time = time.perf_counter()
            cmd_wall_time = time.time()

            command = {
                'seq': i,
                'cmd_send_time': cmd_send_time,
                'cmd_wall_time': cmd_wall_time,
                'command_data': f"cmd_{i}"
            }

            # Store command timestamp for RTT calculation
            self.command_timestamps[i] = cmd_send_time

            try:
                # Send command
                self.cmd_publisher.send_string(json.dumps(command))

                # Receive state (may not be immediate due to async nature)
                state_str = self.state_subscriber.recv_string()
                state_recv_time = time.perf_counter()
                state_recv_wall_time = time.time()

                # Parse state
                state = json.loads(state_str)

                # RTT calculation
                latest_cmd = state.get('latest_cmd')
                rtt_ms = 0.0

                if latest_cmd and latest_cmd.get('seq') == i:
                    # Direct RTT measurement
                    rtt_ms = (state_recv_time - cmd_send_time) * 1000
                elif latest_cmd and latest_cmd.get('seq') is not None:
                    # RTT for different sequence (due to async)
                    cmd_seq = latest_cmd.get('seq')
                    if cmd_seq in self.command_timestamps:
                        orig_send_time = self.command_timestamps[cmd_seq]
                        rtt_ms = (state_recv_time - orig_send_time) * 1000

                # Store measurement
                measurement = {
                    'seq': i,
                    'cmd_send_time': cmd_send_time,
                    'state_recv_time': state_recv_time,
                    'cmd_wall_time': cmd_wall_time,
                    'state_recv_wall_time': state_recv_wall_time,
                    'rtt_ms': rtt_ms,
                    'state_seq': state.get('seq', -1),
                    'matched_cmd_seq': latest_cmd.get('seq', -1) if latest_cmd else -1,
                    'server_message_count': state.get('message_count', 0)
                }

                self.measurements.append(measurement)

                # Progress reporting
                if (i + 1) % 100 == 0:
                    recent_rtts = [m['rtt_ms'] for m in self.measurements[-100:] if m['rtt_ms'] > 0]
                    if recent_rtts:
                        avg_rtt = np.mean(recent_rtts)
                        std_rtt = np.std(recent_rtts)
                        p95_rtt = np.percentile(recent_rtts, 95)
                        print(f"Message {i+1}/{num_messages}: RTT={rtt_ms:.2f}ms, "
                              f"Recent: {avg_rtt:.2f}±{std_rtt:.2f}ms, P95={p95_rtt:.2f}ms")

                # Control loop timing (20ms like original)
                elapsed = time.perf_counter() - cmd_send_time
                sleep_time = max(0, 0.02 - elapsed)  # 50Hz
                time.sleep(sleep_time)

            except zmq.Again:
                print(f"Timeout on message {i}")
                # Record timeout
                measurement = {
                    'seq': i,
                    'cmd_send_time': cmd_send_time,
                    'state_recv_time': 0,
                    'cmd_wall_time': cmd_wall_time,
                    'state_recv_wall_time': 0,
                    'rtt_ms': 0,
                    'state_seq': -1,
                    'matched_cmd_seq': -1,
                    'server_message_count': 0
                }
                self.measurements.append(measurement)
                continue

            except Exception as e:
                print(f"Error on message {i}: {e}")
                continue

        return self.measurements

    def analyze_and_save(self, measurements: List[Dict], test_name: str = "pubsub_test"):
        """結果分析・保存"""
        if not measurements:
            print("No measurements to analyze")
            return

        # Filter valid RTT measurements
        valid_rtts = [m['rtt_ms'] for m in measurements if m['rtt_ms'] > 0]

        print(f"\n{'='*60}")
        print(f"PUB/SUB RTT ANALYSIS")
        print(f"{'='*60}")
        print(f"Total messages: {len(measurements)}")
        print(f"Valid RTT measurements: {len(valid_rtts)}")

        if valid_rtts:
            print(f"RTT Mean: {np.mean(valid_rtts):.3f} ± {np.std(valid_rtts):.3f}ms")
            print(f"RTT Range: {np.min(valid_rtts):.3f} - {np.max(valid_rtts):.3f}ms")
            print(f"RTT P95: {np.percentile(valid_rtts, 95):.3f}ms")

            # Growth analysis
            if len(valid_rtts) >= 200:
                first_half = valid_rtts[:len(valid_rtts)//2]
                last_half = valid_rtts[len(valid_rtts)//2:]

                first_avg = np.mean(first_half)
                last_avg = np.mean(last_half)
                growth = last_avg / first_avg if first_avg > 0 else 1.0

                print(f"\nGROWTH ANALYSIS:")
                print(f"First half avg: {first_avg:.3f}ms")
                print(f"Last half avg: {last_avg:.3f}ms")
                print(f"Growth factor: {growth:.2f}x")

                if growth > 1.1:
                    print("⚠️  RTT GROWTH DETECTED")
                else:
                    print("✅ RTT STABLE")

        # Save to CSV
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs("test_results", exist_ok=True)

        csv_filename = f"test_results/pubsub_rtt_{test_name}_{timestamp}.csv"
        fieldnames = measurements[0].keys()

        with open(csv_filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(measurements)

        print(f"Results saved to: {csv_filename}")

    def cleanup(self):
        """リソース解放"""
        self.state_subscriber.close()
        self.cmd_publisher.close()
        self.context.term()

def main():
    print("=== PUB/SUB RTT Measurement Test ===")

    # Start client first (it binds the command port)
    client = PubSubRTTClient()
    client.connect()

    # Start server in background (it connects to client's port)
    server = PubSubRTTServer()
    server_thread = threading.Thread(target=server.start)
    server_thread.daemon = True
    server_thread.start()

    # Wait for full startup
    time.sleep(2.0)

    measurements = client.run_test(num_messages=500)

    # Analysis and save
    client.analyze_and_save(measurements, "pubsub_baseline")

    # Cleanup
    server.running = False
    client.cleanup()

    print(f"\n✅ PUB/SUB RTT test completed")

if __name__ == "__main__":
    main()