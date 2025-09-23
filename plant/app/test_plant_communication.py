#!/usr/bin/env python3
"""
Plant側通信テストスクリプト

PlantCommunicatorモジュールの機能をテストするためのスタンドアロンスクリプト。
物理シミュレーションなしで通信機能のみをテスト。

テスト項目：
- 基本的な通信設定
- 同期プロトコル
- メッセージ送受信
- 遅延シミュレーション
- エラーハンドリング
"""

import time
import logging
import sys
import os
import argparse
from typing import Dict

# 通信モジュールをインポート
from plant_communication import PlantCommunicator

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PlantCommunicationTester:
    """
    Plant側通信テストクラス

    実際の物理シミュレーションなしで通信機能をテスト
    """

    def __init__(self, enable_delay: bool = False, test_duration: int = 30):
        """
        テスター初期化

        Args:
            enable_delay: 遅延シミュレーション有効化
            test_duration: テスト実行時間[秒]
        """
        self.enable_delay = enable_delay
        self.test_duration = test_duration
        self.step_count = 0
        self.command_count = 0

        # 模擬データ生成用
        self.mock_altitude = 0.0
        self.mock_velocity = 0.0
        self.mock_thrust = 0.0

        # 統計
        self.commands_received = 0
        self.states_sent = 0

    def setup_communicator(self) -> PlantCommunicator:
        """
        通信設定をセットアップ

        Returns:
            設定済みのPlantCommunicatorインスタンス
        """
        # localhostで通信（テスト環境）
        state_pub_port = 5555
        cmd_sub_endpoint = "tcp://localhost:5556"

        # PlantCommunicator初期化
        communicator = PlantCommunicator(state_pub_port, cmd_sub_endpoint)

        # 遅延シミュレーション設定
        if self.enable_delay:
            communicator.configure_delay_simulation(
                enable=True,
                processing_delay_ms=5.0,   # 5ms処理遅延
                response_delay_ms=3.0,     # 3ms応答遅延
                delay_variation_ms=2.0     # ±2ms変動
            )
            logger.info("Delay simulation enabled")

        return communicator

    def generate_mock_state_data(self) -> Dict:
        """
        モック状態データを生成

        簡単な物理モデルで状態を更新

        Returns:
            状態データ辞書
        """
        dt = 0.01  # 10ms周期

        # 簡単な物理更新（推力→加速度→速度→位置）
        mass = 1.0
        gravity = 9.81

        acceleration = (self.mock_thrust - mass * gravity) / mass
        self.mock_velocity += acceleration * dt
        self.mock_altitude += self.mock_velocity * dt

        return {
            "acc": [0.0, 0.0, acceleration],
            "gyro": [0.0, 0.0, 0.0],
            "position": [0.0, 0.0, self.mock_altitude],
            "velocity": [0.0, 0.0, self.mock_velocity]
        }

    def test_basic_communication(self):
        """
        基本通信テスト

        同期プロトコル→データ送受信のフロー
        """
        logger.info("=== Basic Communication Test ===")

        communicator = self.setup_communicator()

        try:
            # 同期プロトコル待機
            logger.info("Waiting for synchronization from Numeric...")
            communicator.wait_for_synchronization(timeout_seconds=15.0)

            if not communicator.is_synchronized:
                logger.warning("Synchronization failed, continuing anyway")
                return False

            # データ送受信テスト
            start_time = time.time()
            dt = 0.01  # 10ms周期

            logger.info(f"Starting communication test for {self.test_duration} seconds...")

            while (time.time() - start_time) < self.test_duration:
                loop_start = time.time()

                # 遅延コマンド処理
                delayed_command = communicator.process_delayed_commands()
                if delayed_command is not None:
                    self.mock_thrust = delayed_command[2] if len(delayed_command) >= 3 else 0.0
                    self.commands_received += 1

                # 新コマンド受信
                new_command = communicator.receive_commands()
                if new_command is not None:
                    self.mock_thrust = new_command[2] if len(new_command) >= 3 else 0.0
                    self.commands_received += 1

                # 状態データ生成・送信
                state_data = self.generate_mock_state_data()
                sim_time = time.time() - start_time
                communicator.broadcast_state(self.step_count, sim_time, state_data)
                self.states_sent += 1

                # 進捗表示（1秒毎）
                if self.step_count % 100 == 0:
                    logger.info(f"Step {self.step_count}: Alt={self.mock_altitude:.2f}m, "
                              f"Thrust={self.mock_thrust:.1f}N, Commands={self.commands_received}")

                self.step_count += 1

                # 固定周期維持
                elapsed = time.time() - loop_start
                sleep_time = dt - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

            # テスト結果
            logger.info("=== Test Results ===")
            logger.info(f"Steps executed: {self.step_count}")
            logger.info(f"Commands received: {self.commands_received}")
            logger.info(f"States sent: {self.states_sent}")
            logger.info(f"Final altitude: {self.mock_altitude:.2f}m")

            return True

        except Exception as e:
            logger.error(f"Communication test failed: {e}")
            return False
        finally:
            communicator.stop_communication()

    def test_delay_simulation(self):
        """
        遅延シミュレーションテスト

        遅延機能が正しく動作するかを確認
        """
        logger.info("=== Delay Simulation Test ===")

        if not self.enable_delay:
            logger.info("Delay simulation disabled, skipping test")
            return True

        # 短時間で遅延テスト
        self.test_duration = 10
        return self.test_basic_communication()

    def run_all_tests(self):
        """
        全テストの実行

        Returns:
            全テスト成功の場合True
        """
        logger.info("Starting Plant Communication Tests...")

        tests = [
            ("Basic Communication", self.test_basic_communication),
        ]

        if self.enable_delay:
            tests.append(("Delay Simulation", self.test_delay_simulation))

        results = []
        for test_name, test_func in tests:
            logger.info(f"\n{'='*50}")
            logger.info(f"Running: {test_name}")
            logger.info(f"{'='*50}")

            try:
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
    parser = argparse.ArgumentParser(description='Plant Communication Tester')
    parser.add_argument('--delay', action='store_true',
                       help='Enable delay simulation test')
    parser.add_argument('--duration', type=int, default=30,
                       help='Test duration in seconds (default: 30)')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # テスター初期化・実行
    tester = PlantCommunicationTester(
        enable_delay=args.delay,
        test_duration=args.duration
    )

    logger.info("Plant Communication Tester Starting...")
    logger.info(f"Delay simulation: {'Enabled' if args.delay else 'Disabled'}")
    logger.info(f"Test duration: {args.duration} seconds")

    success = tester.run_all_tests()

    # 終了コード設定
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()