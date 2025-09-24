#!/usr/bin/env python3
"""
Minimal Numeric Communication Test

communication_test_containersの成功パターンを参考にした
最小限の通信テスト実装 - RTT測定重視
"""

import zmq
import time
import json
import numpy as np

def main():
    print("=== Minimal Numeric Communication Test ===")

    # ZeroMQ REQソケット (communication_test_containersと同じパターン)
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://plant:5555")

    print("Numeric REQ client connected to plant:5555")

    # Test parameters
    num_messages = 500
    rtt_measurements = []

    print(f"Sending {num_messages} test messages...")

    for i in range(num_messages):
        # High precision timing (communication_test_containersスタイル)
        send_time = time.perf_counter()

        # メッセージ作成
        message = {
            'seq': i,
            'send_time': send_time,
            'timestamp': time.time()
        }

        try:
            # メッセージ送信
            socket.send_string(json.dumps(message))

            # レスポンス受信
            response_str = socket.recv_string()
            recv_time = time.perf_counter()

            # RTT計算 (communication_test_containersと同じ方式)
            rtt_ms = (recv_time - send_time) * 1000.0

            # レスポンス解析
            response = json.loads(response_str)

            # RTT記録
            rtt_measurements.append(rtt_ms)

            # Progress reporting
            if (i + 1) % 50 == 0:
                recent_rtts = rtt_measurements[-50:]
                avg_rtt = np.mean(recent_rtts)
                std_rtt = np.std(recent_rtts)
                print(f"Message {i+1}/{num_messages}: RTT={rtt_ms:.2f}ms, Recent Avg={avg_rtt:.2f}±{std_rtt:.2f}ms")

        except Exception as e:
            print(f"Error on message {i}: {e}")
            continue

    # Final statistics
    if rtt_measurements:
        print(f"\n=== RTT STATISTICS ===")
        print(f"Total messages: {len(rtt_measurements)}")
        print(f"RTT Mean: {np.mean(rtt_measurements):.2f}ms")
        print(f"RTT Std: {np.std(rtt_measurements):.2f}ms")
        print(f"RTT Min: {np.min(rtt_measurements):.2f}ms")
        print(f"RTT Max: {np.max(rtt_measurements):.2f}ms")
        print(f"RTT P95: {np.percentile(rtt_measurements, 95):.2f}ms")

        # Check for RTT growth
        first_100 = np.mean(rtt_measurements[:100]) if len(rtt_measurements) >= 100 else 0
        last_100 = np.mean(rtt_measurements[-100:]) if len(rtt_measurements) >= 100 else 0
        if last_100 > 0 and first_100 > 0:
            growth_factor = last_100 / first_100
            print(f"RTT Growth Factor: {growth_factor:.2f}x")
            if growth_factor > 1.1:
                print("⚠️  RTT GROWTH DETECTED")
            else:
                print("✅ RTT STABLE")

    socket.close()
    context.term()

if __name__ == "__main__":
    main()