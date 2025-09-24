#!/usr/bin/env python3
"""
Numeric側通信テストスクリプト

NumericCommunicatorモジュールの機能をテストするためのスタンドアロンスクリプト。
制御アルゴリズムなしで通信機能のみをテスト。

テスト項目：
- 基本的な通信設定
- 同期プロトコル
- メッセージ送受信
- RTT測定
- エラーハンドリング
"""

import time
import logging
import sys
import os
import argparse
from typing import Dict, Optional

# 通信モジュールをインポート
from numeric_communication import NumericCommunicator

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NumericCommunicationTester:
    """
    Numeric側通信テストクラス

    実際の制御アルゴリズムなしで通信機能をテスト
    """

    def __init__(self, test_duration: int = 30):
        """
        テスター初期化

        Args:
            test_duration: テスト実行時間[秒]
        """
        self.test_duration = test_duration
        self.step_count = 0

        # 模擬制御データ
        self.mock_setpoint = 10.0  # 目標高度10m
        self.current_altitude = 0.0
        self.control_output = 0.0

        # 統計
        self.commands_sent = 0
        self.states_received = 0
        self.rtt_measurements = []

    def setup_communicator(self) -> NumericCommunicator:
        """
        通信設定をセットアップ

        Returns:
            設定済みのNumericCommunicatorインスタンス
        """
        # localhostで通信（テスト環境）
        plant_state_endpoint = "tcp://localhost:5555"
        cmd_publish_port = 5556

        # NumericCommunicator初期化
        communicator = NumericCommunicator(plant_state_endpoint, cmd_publish_port)

        return communicator

    def generate_mock_control_command(self, altitude: float) -> list:
        """
        モック制御コマンドを生成

        簡単なP制御で推力コマンドを計算

        Args:
            altitude: 現在高度[m]

        Returns:
            制御コマンド [fx, fy, fz]
        """
        # 簡単なP制御
        kp = 15.0  # 比例ゲイン
        mass = 1.0
        gravity = 9.81

        error = self.mock_setpoint - altitude
        thrust = kp * error + mass * gravity

        # 推力制限
        thrust = max(0.0, min(thrust, 1000.0))

        return [0.0, 0.0, thrust]

    def test_basic_communication(self):
        """
        基本通信テスト

        同期プロトコル→データ送受信のフロー
        """
        logger.info("=== Basic Communication Test ===")

        communicator = self.setup_communicator()

        try:
            # 同期プロトコル実行
            logger.info("Starting synchronization protocol...")
            communicator.start_communication()

            if not communicator.is_synchronized:
                logger.error("Synchronization failed")
                return False

            logger.info("Synchronization successful")

            # データ送受信テスト
            start_time = time.time()
            dt = 0.01  # 10ms周期

            logger.info(f"Starting communication test for {self.test_duration} seconds...")

            while (time.time() - start_time) < self.test_duration:
                loop_start = time.time()

                # Plant状態データ受信
                latest_response = communicator.get_latest_response()

                if latest_response and latest_response.get('valid', False):
                    # 有効な応答を受信
                    plant_data = latest_response['plant_response']['y']
                    self.current_altitude = plant_data['position'][2]
                    rtt_ms = latest_response.get('rtt_ms', 0)

                    self.states_received += 1
                    if rtt_ms > 0:
                        self.rtt_measurements.append(rtt_ms)

                # 制御コマンド生成・送信
                command = self.generate_mock_control_command(self.current_altitude)
                sim_time = time.time() - start_time
                communicator.send_command_async(self.step_count, sim_time, command)
                self.commands_sent += 1

                # 進捗表示（1秒毎）
                if self.step_count % 100 == 0:
                    avg_rtt = sum(self.rtt_measurements[-100:]) / max(len(self.rtt_measurements[-100:]), 1)
                    logger.info(f"Step {self.step_count}: Alt={self.current_altitude:.2f}m, "
                              f"Cmd={command[2]:.1f}N, States={self.states_received}, RTT={avg_rtt:.1f}ms")

                self.step_count += 1

                # 固定周期維持
                elapsed = time.time() - loop_start
                sleep_time = dt - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # テスト結果
            comm_stats = communicator.get_communication_stats()
            avg_rtt = sum(self.rtt_measurements) / max(len(self.rtt_measurements), 1)

            logger.info("=== Test Results ===")
            logger.info(f"Steps executed: {self.step_count}")
            logger.info(f"Commands sent: {self.commands_sent}")
            logger.info(f"States received: {self.states_received}")
            logger.info(f"Final altitude: {self.current_altitude:.2f}m")
            logger.info(f"Average RTT: {avg_rtt:.1f}ms")
            logger.info(f"RTT measurements: {len(self.rtt_measurements)}")
            logger.info(f"Communication stats: {comm_stats}")

            # 成功条件チェック
            success = (
                self.commands_sent > 0 and
                self.states_received > 0 and
                len(self.rtt_measurements) > 0
            )

            return success

        except Exception as e:
            logger.error(f"Communication test failed: {e}")
            return False
        finally:
            communicator.stop_communication()

    def test_synchronization_protocol(self):
        """
        同期プロトコル単体テスト

        同期機能が正しく動作するかを確認
        """
        logger.info("=== Synchronization Protocol Test ===")

        communicator = self.setup_communicator()

        try:
            # 同期前状態確認
            assert not communicator.is_synchronized, "Should not be synchronized initially"

            # 同期プロトコル実行
            start_time = time.time()
            communicator.establish_synchronization(sync_delay_seconds=2.0)
            sync_time = time.time() - start_time

            # 同期後状態確認
            assert communicator.is_synchronized, "Should be synchronized after protocol"
            assert communicator.sync_base_time is not None, "Sync base time should be set"

            logger.info(f"Synchronization completed in {sync_time:.2f} seconds")
            logger.info(f"Sync base time: {communicator.sync_base_time}")

            # 同期タイムスタンプテスト
            sync_timestamp = communicator.get_sync_timestamp()
            assert sync_timestamp >= 0, "Sync timestamp should be non-negative"

            logger.info(f"Current sync timestamp: {sync_timestamp:.3f}s")

            return True

        except Exception as e:
            logger.error(f"Synchronization test failed: {e}")
            return False
        finally:
            communicator.stop_communication()

    def test_rtt_measurement(self):
        """
        RTT測定テスト

        短時間でRTT測定機能をテスト
        """
        logger.info("=== RTT Measurement Test ===")

        # 短時間でRTTテスト
        original_duration = self.test_duration
        self.test_duration = 10

        try:
            result = self.test_basic_communication()

            # RTT測定結果分析
            if self.rtt_measurements:
                min_rtt = min(self.rtt_measurements)
                max_rtt = max(self.rtt_measurements)
                avg_rtt = sum(self.rtt_measurements) / len(self.rtt_measurements)

                logger.info(f"RTT Statistics:")
                logger.info(f"  Min: {min_rtt:.1f}ms")
                logger.info(f"  Max: {max_rtt:.1f}ms")
                logger.info(f"  Avg: {avg_rtt:.1f}ms")
                logger.info(f"  Count: {len(self.rtt_measurements)}")

                # RTT合理性チェック
                if avg_rtt < 0 or avg_rtt > 1000:
                    logger.warning(f"RTT seems unreasonable: {avg_rtt:.1f}ms")
                    return False

            return result and len(self.rtt_measurements) > 0

        finally:
            self.test_duration = original_duration

    def run_all_tests(self):
        """
        全テストの実行

        Returns:
            全テスト成功の場合True
        """
        logger.info("Starting Numeric Communication Tests...")

        tests = [
            ("Synchronization Protocol", self.test_synchronization_protocol),
            ("RTT Measurement", self.test_rtt_measurement),
            ("Basic Communication", self.test_basic_communication),
        ]

        results = []
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"Running: {test_name}")
            logger.info(f"{'='*50}")

            try:
                # テスト間でリセット
                self.step_count = 0
                self.commands_sent = 0
                self.states_received = 0
                self.rtt_measurements = []
                self.current_altitude = 0.0

                result = test_func()
                results.append(result)
                logger.info(f"{test_name}: {'PASSED' if result else 'FAILED'}")
            except Exception as e:
                logger.error(f"{test_name}: FAILED with exception: {e}")
                results.append(False)

        # 総合結果
        all_passed = all(results)
        logger.info(f"\n{'='*50}")
        logger.info(f"Overall Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
        logger.info(f"{'='*50}")

        return all_passed


def main():
    """
    メイン関数

    コマンドライン引数でテスト設定を受け取り実行
    """
    parser = argparse.ArgumentParser(description='Numeric Communication Tester')
    parser.add_argument('--duration', type=int, default=30,
                       help='Test duration in seconds (default: 30)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # テスター初期化・実行
    tester = NumericCommunicationTester(test_duration=args.duration)

    logger.info("Numeric Communication Tester Starting...")
    logger.info(f"Test duration: {args.duration} seconds")

    success = tester.run_all_tests()

    # 終了コード設定
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()