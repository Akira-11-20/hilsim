#!/usr/bin/env python3
"""
Simple Communication Test - Outside Docker

RTT測定の問題を切り分けるため、Dockerの外で実行する
communication_test_containersのパターンを参考にした最小テスト
"""

import zmq
import time
import json
import numpy as np
import threading
from typing import List

def server_process():
    """Simple REP server (communication_test_containersスタイル)"""
    print("Starting REP server on port 5559...")

    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://127.0.0.1:5559")

    message_count = 0

    try:
        while message_count < 200:  # Limited test
            # Receive message
            message_str = socket.recv_string()
            recv_time = time.perf_counter()

            try:
                message = json.loads(message_str)

                # Simple processing delay
                time.sleep(0.001)  # 1ms

                # Response
                response = {
                    'seq': message.get('seq', message_count),
                    'recv_time': recv_time,
                    'server_processing_time_ms': (time.perf_counter() - recv_time) * 1000,
                    'message_count': message_count
                }

                socket.send_string(json.dumps(response))
                message_count += 1

            except json.JSONDecodeError:
                socket.send_string("ERROR: Invalid JSON")

    except Exception as e:
        print(f"Server error: {e}")
    finally:
        socket.close()
        context.term()
        print(f"Server processed {message_count} messages")

def client_test() -> List[float]:
    """REQ client with RTT measurement"""
    print("Starting REQ client...")

    # Wait for server startup
    time.sleep(0.5)

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://127.0.0.1:5559")

    rtt_measurements = []

    try:
        for i in range(200):
            # High precision timing
            send_time = time.perf_counter()

            message = {
                'seq': i,
                'client_send_time': send_time
            }

            # Send and receive
            socket.send_string(json.dumps(message))
            response_str = socket.recv_string()
            recv_time = time.perf_counter()

            # Calculate RTT
            rtt_ms = (recv_time - send_time) * 1000.0
            rtt_measurements.append(rtt_ms)

            # Progress
            if (i + 1) % 50 == 0:
                recent = rtt_measurements[-50:]
                print(f"Messages {i+1}: Recent RTT={np.mean(recent):.2f}±{np.std(recent):.2f}ms")

    except Exception as e:
        print(f"Client error: {e}")
    finally:
        socket.close()
        context.term()

    return rtt_measurements

def main():
    print("=== Simple Communication Test ===")

    # Start server in background
    server_thread = threading.Thread(target=server_process)
    server_thread.daemon = True
    server_thread.start()

    # Run client test
    rtt_measurements = client_test()

    # Analysis
    if rtt_measurements:
        print(f"\n=== RTT ANALYSIS ===")
        print(f"Total: {len(rtt_measurements)} messages")
        print(f"Mean RTT: {np.mean(rtt_measurements):.3f}ms")
        print(f"Std RTT: {np.std(rtt_measurements):.3f}ms")
        print(f"Min RTT: {np.min(rtt_measurements):.3f}ms")
        print(f"Max RTT: {np.max(rtt_measurements):.3f}ms")
        print(f"P95 RTT: {np.percentile(rtt_measurements, 95):.3f}ms")

        # Growth check
        first_50 = np.mean(rtt_measurements[:50])
        last_50 = np.mean(rtt_measurements[-50:])
        growth = last_50 / first_50 if first_50 > 0 else 1.0

        print(f"\nFirst 50 avg: {first_50:.3f}ms")
        print(f"Last 50 avg: {last_50:.3f}ms")
        print(f"Growth factor: {growth:.2f}x")

        if growth > 1.1:
            print("⚠️  RTT GROWTH DETECTED")
        else:
            print("✅ RTT STABLE")
    else:
        print("No measurements collected")

if __name__ == "__main__":
    main()