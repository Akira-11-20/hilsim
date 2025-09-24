#!/usr/bin/env python3
"""
RTT Measurement Test - Enhanced Version

communication_test_containersのRTT測定とCSV出力機能を追加
成功したREQ/REPベースに詳細な測定とログ機能を統合
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

class RTTMeasurementServer:
    """RTT測定対応サーバー"""

    def __init__(self, port: int = 5559):
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.message_count = 0
        self.running = False

    def start(self):
        """サーバー開始"""
        self.socket.bind(f"tcp://127.0.0.1:{self.port}")
        self.running = True
        print(f"RTT Measurement Server started on port {self.port}")

        try:
            while self.running and self.message_count < 500:  # Test limit
                # High precision receive timing
                message_str = self.socket.recv_string()
                server_recv_time = time.perf_counter()
                server_wall_time = time.time()

                try:
                    message = json.loads(message_str)

                    # Simple processing delay (like communication_test_containers)
                    processing_start = time.perf_counter()
                    time.sleep(0.001)  # 1ms processing
                    processing_end = time.perf_counter()

                    # Response with detailed timing info
                    response = {
                        'seq': message.get('seq', self.message_count),
                        'client_send_time': message.get('client_send_time', 0),
                        'server_recv_time': server_recv_time,
                        'server_wall_time': server_wall_time,
                        'server_processing_time_ms': (processing_end - processing_start) * 1000,
                        'message_count': self.message_count,
                        'server_send_time': time.perf_counter()  # Response send time
                    }

                    self.socket.send_string(json.dumps(response))
                    self.message_count += 1

                    # Progress logging
                    if self.message_count % 100 == 0:
                        print(f"Server processed {self.message_count} messages")

                except json.JSONDecodeError:
                    self.socket.send_string(json.dumps({"error": "Invalid JSON"}))

        except Exception as e:
            print(f"Server error: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """リソース解放"""
        self.socket.close()
        self.context.term()
        print(f"Server stopped after processing {self.message_count} messages")

class RTTMeasurementClient:
    """RTT測定対応クライアント"""

    def __init__(self, server_port: int = 5559):
        self.server_port = server_port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.measurements = []

    def connect(self):
        """サーバーに接続"""
        self.socket.connect(f"tcp://127.0.0.1:{self.server_port}")
        print("RTT Measurement Client connected")

    def run_test(self, num_messages: int = 500) -> List[Dict]:
        """RTT測定テスト実行"""
        print(f"Starting RTT measurement test: {num_messages} messages")

        for i in range(num_messages):
            # High precision timing
            client_send_time = time.perf_counter()
            client_wall_time = time.time()

            message = {
                'seq': i,
                'client_send_time': client_send_time,
                'client_wall_time': client_wall_time
            }

            try:
                # Send message
                self.socket.send_string(json.dumps(message))

                # Receive response
                response_str = self.socket.recv_string()
                client_recv_time = time.perf_counter()
                client_recv_wall_time = time.time()

                # Parse response
                response = json.loads(response_str)

                # Calculate RTT
                rtt_ms = (client_recv_time - client_send_time) * 1000

                # Store detailed measurement
                measurement = {
                    'seq': i,
                    'client_send_time': client_send_time,
                    'client_recv_time': client_recv_time,
                    'client_wall_time': client_wall_time,
                    'client_recv_wall_time': client_recv_wall_time,
                    'server_recv_time': response.get('server_recv_time', 0),
                    'server_wall_time': response.get('server_wall_time', 0),
                    'server_processing_time_ms': response.get('server_processing_time_ms', 0),
                    'rtt_ms': rtt_ms,
                    'message_count': response.get('message_count', i)
                }

                self.measurements.append(measurement)

                # Progress reporting (communication_test_containersスタイル)
                if (i + 1) % 100 == 0:
                    recent_rtts = [m['rtt_ms'] for m in self.measurements[-100:]]
                    avg_rtt = np.mean(recent_rtts)
                    std_rtt = np.std(recent_rtts)
                    p95_rtt = np.percentile(recent_rtts, 95)
                    print(f"Message {i+1}/{num_messages}: RTT={rtt_ms:.2f}ms, "
                          f"Recent: {avg_rtt:.2f}±{std_rtt:.2f}ms, P95={p95_rtt:.2f}ms")

            except Exception as e:
                print(f"Error on message {i}: {e}")
                continue

        return self.measurements

    def save_results(self, measurements: List[Dict], test_name: str = "rtt_test"):
        """結果をCSV保存 (communication_test_containersスタイル)"""
        if not measurements:
            print("No measurements to save")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Create results directory
        os.makedirs("test_results", exist_ok=True)

        # Save detailed CSV
        csv_filename = f"test_results/rtt_detailed_{test_name}_{timestamp}.csv"

        fieldnames = measurements[0].keys()
        with open(csv_filename, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(measurements)

        print(f"Detailed results saved to: {csv_filename}")

        # Generate summary statistics
        rtts = [m['rtt_ms'] for m in measurements]
        summary = {
            'test_name': test_name,
            'timestamp': timestamp,
            'total_samples': len(measurements),
            'rtt_mean_ms': float(np.mean(rtts)),
            'rtt_std_ms': float(np.std(rtts)),
            'rtt_min_ms': float(np.min(rtts)),
            'rtt_max_ms': float(np.max(rtts)),
            'rtt_p95_ms': float(np.percentile(rtts, 95)),
            'rtt_p99_ms': float(np.percentile(rtts, 99))
        }

        # Save summary JSON
        summary_filename = f"test_results/rtt_summary_{test_name}_{timestamp}.json"
        with open(summary_filename, 'w') as f:
            json.dump(summary, f, indent=2)

        print(f"Summary saved to: {summary_filename}")

        return summary

    def analyze_results(self, measurements: List[Dict]):
        """RTT分析 (communication_test_containersスタイル)"""
        if not measurements:
            print("No measurements to analyze")
            return

        rtts = [m['rtt_ms'] for m in measurements]

        print(f"\n{'='*60}")
        print(f"RTT MEASUREMENT ANALYSIS")
        print(f"{'='*60}")
        print(f"Total samples: {len(measurements)}")
        print(f"RTT Mean: {np.mean(rtts):.3f} ± {np.std(rtts):.3f}ms")
        print(f"RTT Range: {np.min(rtts):.3f} - {np.max(rtts):.3f}ms")
        print(f"RTT Median: {np.median(rtts):.3f}ms")
        print(f"RTT P95: {np.percentile(rtts, 95):.3f}ms")
        print(f"RTT P99: {np.percentile(rtts, 99):.3f}ms")

        # Growth analysis
        if len(rtts) >= 200:
            first_100 = np.mean(rtts[:100])
            last_100 = np.mean(rtts[-100:])
            growth = last_100 / first_100 if first_100 > 0 else 1.0

            print(f"\nGROWTH ANALYSIS:")
            print(f"First 100 avg: {first_100:.3f}ms")
            print(f"Last 100 avg: {last_100:.3f}ms")
            print(f"Growth factor: {growth:.2f}x")

            if growth > 1.1:
                print("⚠️  RTT GROWTH DETECTED")
            elif growth < 0.9:
                print("📈 RTT IMPROVEMENT DETECTED")
            else:
                print("✅ RTT STABLE")

    def cleanup(self):
        """リソース解放"""
        self.socket.close()
        self.context.term()

def main():
    print("=== RTT Measurement Test ===")

    # Start server in background
    server = RTTMeasurementServer()
    server_thread = threading.Thread(target=server.start)
    server_thread.daemon = True
    server_thread.start()

    # Wait for server startup
    time.sleep(0.5)

    # Run client test
    client = RTTMeasurementClient()
    client.connect()

    measurements = client.run_test(num_messages=500)

    # Analysis and save
    client.analyze_results(measurements)
    summary = client.save_results(measurements, "req_rep_baseline")

    # Cleanup
    server.running = False
    client.cleanup()

    print(f"\n✅ RTT measurement test completed")
    print(f"Results saved in test_results/ directory")

if __name__ == "__main__":
    main()