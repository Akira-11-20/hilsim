#!/usr/bin/env python3
"""
リアルタイム制御シミュレーターのエントリーポイント
環境変数 REALTIME_MODE=1 で有効化
"""

import os
import sys

# 環境変数でリアルタイムモードを確認
if os.getenv('REALTIME_MODE', '0') == '1':
    print("Starting REALTIME control simulator...")
    from realtime_simulator import RealtimeNumericSimulator
    simulator = RealtimeNumericSimulator()
    simulator.run_realtime()
else:
    print("Starting SYNC control simulator...")
    from main import NumericSimulator
    simulator = NumericSimulator()
    simulator.run()