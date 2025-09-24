#!/usr/bin/env python3
"""
Minimal ZMQ Echo Server for Communication Overhead Testing
"""

import zmq
import time
import json
import sys

def run_echo_server(port=5555):
    """Run a minimal echo server"""

    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind(f"tcp://*:{port}")

    print(f"Echo server started on port {port}")
    print("Ready to receive messages...")

    message_count = 0

    try:
        while True:
            # Receive message
            message = socket.recv_string()

            # Parse and respond immediately (minimal processing)
            try:
                data = json.loads(message)
                data['server_timestamp'] = time.time()
                data['message_id'] = message_count
                response = json.dumps(data)
            except json.JSONDecodeError:
                response = json.dumps({
                    'echo': message,
                    'server_timestamp': time.time(),
                    'message_id': message_count
                })

            # Send response immediately
            socket.send_string(response)

            message_count += 1

            if message_count % 100 == 0:
                print(f"Processed {message_count} messages")

    except KeyboardInterrupt:
        print("Server stopping...")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    run_echo_server()