#!/usr/bin/env python3
"""
Minimal Plant Communication Test

communication_test_containersの成功パターンを参考にした
最小限の通信テスト実装
"""

import zmq
import time
import json

def main():
    print("=== Minimal Plant Communication Test ===")

    # ZeroMQ REPソケット (communication_test_containersと同じパターン)
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://*:5555")

    print("Plant REP server started on port 5555")
    print("Waiting for messages...")

    message_count = 0

    try:
        while True:
            # メッセージ受信 (ブロッキング)
            message_str = socket.recv_string()
            recv_time = time.perf_counter()

            try:
                message = json.loads(message_str)
                seq = message.get('seq', message_count)
                send_time = message.get('send_time', recv_time)

                # Simple processing delay (communication_test_containersスタイル)
                time.sleep(0.001)  # 1ms processing delay

                # レスポンス作成
                response = {
                    'seq': seq,
                    'recv_time': recv_time,
                    'send_time': send_time,
                    'plant_processing_time': time.perf_counter() - recv_time,
                    'message_count': message_count,
                    'status': 'OK'
                }

                # レスポンス送信
                socket.send_string(json.dumps(response))

                message_count += 1

                # Progress logging
                if message_count % 100 == 0:
                    print(f"Processed {message_count} messages")

            except json.JSONDecodeError:
                # Simple echo for non-JSON messages
                socket.send_string(f"Echo: {message_str}")
                message_count += 1

    except KeyboardInterrupt:
        print(f"\nShutting down after {message_count} messages")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    main()