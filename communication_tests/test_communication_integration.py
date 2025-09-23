#!/usr/bin/env python3
"""
統合通信テストスクリプト

Plant↔Numeric間の通信モジュールを統合的にテストするスクリプト。
両側のプロセスを起動して実際の通信をテスト。

テスト項目：
- 両側プロセス起動
- 同期プロトコル実行
- データ送受信フロー
- RTT測定
- 遅延シミュレーション
- エラー処理
"""

import subprocess
import time
import logging
import sys
import os
import argparse
import signal
import threading
from typing import List, Optional

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class CommunicationIntegrationTester:
    """
    統合通信テストクラス

    Plant・Numericプロセスを並行実行して通信をテスト
    """

    def __init__(self, test_duration: int = 30, enable_delay: bool = False):
        """
        テスター初期化

        Args:
            test_duration: テスト実行時間[秒]
            enable_delay: 遅延シミュレーション有効化
        """
        self.test_duration = test_duration
        self.enable_delay = enable_delay
        self.processes = []
        self.test_results = {}

    def start_plant_process(self) -> subprocess.Popen:
        """
        Plantテストプロセスを開始

        Returns:
            起動したプロセス
        """
        cmd = ["python3", "plant/app/test_plant_communication.py",
               "--duration", str(self.test_duration)]

        if self.enable_delay:
            cmd.append("--delay")

        logger.info(f"Starting Plant process: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd()
        )

        self.processes.append(process)
        return process

    def start_numeric_process(self) -> subprocess.Popen:
        """
        Numericテストプロセスを開始

        Returns:
            起動したプロセス
        """
        cmd = ["python3", "numeric/app/test_numeric_communication.py",
               "--duration", str(self.test_duration)]

        logger.info(f"Starting Numeric process: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd()
        )

        self.processes.append(process)
        return process

    def monitor_process(self, process: subprocess.Popen, name: str) -> dict:
        """
        プロセスの実行を監視

        Args:
            process: 監視対象プロセス
            name: プロセス名

        Returns:
            実行結果辞書
        """
        logger.info(f"Monitoring {name} process (PID: {process.pid})")

        try:
            # プロセス完了待ち（タイムアウト付き）
            stdout, stderr = process.communicate(timeout=self.test_duration + 30)

            result = {
                'name': name,
                'returncode': process.returncode,
                'stdout': stdout,
                'stderr': stderr,
                'success': process.returncode == 0
            }

            logger.info(f"{name} process completed with return code: {process.returncode}")

            # 出力の一部をログに表示
            if stdout:
                logger.info(f"{name} stdout (last 500 chars):\n{stdout[-500:]}")

            if stderr:
                logger.warning(f"{name} stderr:\n{stderr}")

            return result

        except subprocess.TimeoutExpired:
            logger.error(f"{name} process timed out, terminating...")
            process.kill()
            stdout, stderr = process.communicate()

            return {
                'name': name,
                'returncode': -1,
                'stdout': stdout,
                'stderr': stderr,
                'success': False,
                'error': 'timeout'
            }

        except Exception as e:
            logger.error(f"Error monitoring {name} process: {e}")
            return {
                'name': name,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'success': False,
                'error': str(e)
            }

    def test_basic_integration(self):
        """
        基本統合テスト

        Plant・Numeric両プロセスを起動して通信テスト
        """
        logger.info("=== Basic Integration Test ===")

        try:
            # Plantプロセス起動（先に起動して受信待機状態にする）
            plant_process = self.start_plant_process()
            time.sleep(2)  # Plant起動待ち

            # Numericプロセス起動
            numeric_process = self.start_numeric_process()

            # 両プロセスを並行監視
            plant_thread = threading.Thread(
                target=lambda: self.test_results.update({'plant': self.monitor_process(plant_process, 'Plant')})
            )
            numeric_thread = threading.Thread(
                target=lambda: self.test_results.update({'numeric': self.monitor_process(numeric_process, 'Numeric')})
            )

            plant_thread.start()
            numeric_thread.start()

            # 両スレッド完了待ち
            plant_thread.join()
            numeric_thread.join()

            # 結果分析
            plant_result = self.test_results.get('plant', {})
            numeric_result = self.test_results.get('numeric', {})

            both_success = plant_result.get('success', False) and numeric_result.get('success', False)

            logger.info("=== Integration Test Results ===")
            logger.info(f"Plant: {'SUCCESS' if plant_result.get('success') else 'FAILED'}")
            logger.info(f"Numeric: {'SUCCESS' if numeric_result.get('success') else 'FAILED'}")
            logger.info(f"Overall: {'SUCCESS' if both_success else 'FAILED'}")

            return both_success

        except Exception as e:
            logger.error(f"Integration test failed: {e}")
            return False

    def test_delay_simulation_integration(self):
        """
        遅延シミュレーション統合テスト

        遅延機能を有効にして統合テスト
        """
        if not self.enable_delay:
            logger.info("Delay simulation disabled, skipping test")
            return True

        logger.info("=== Delay Simulation Integration Test ===")

        # 短時間で遅延テスト
        original_duration = self.test_duration
        self.test_duration = 15

        try:
            result = self.test_basic_integration()
            return result
        finally:
            self.test_duration = original_duration

    def cleanup_processes(self):
        """
        プロセスクリーンアップ

        起動した全プロセスを適切に終了
        """
        logger.info("Cleaning up processes...")

        for process in self.processes:
            if process.poll() is None:  # プロセスがまだ動いている
                logger.info(f"Terminating process PID: {process.pid}")
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Force killing process PID: {process.pid}")
                    process.kill()
                    process.wait()

        self.processes.clear()

    def run_all_tests(self):
        """
        全統合テストの実行

        Returns:
            全テスト成功の場合True
        """
        logger.info("Starting Communication Integration Tests...")
        logger.info(f"Test duration: {self.test_duration} seconds")
        logger.info(f"Delay simulation: {'Enabled' if self.enable_delay else 'Disabled'}")

        tests = [
            ("Basic Integration", self.test_basic_integration),
        ]

        if self.enable_delay:
            tests.append(("Delay Simulation Integration", self.test_delay_simulation_integration))

        results = []
        for test_name, test_func in tests:
            logger.info(f"\n{'='*60}")
            logger.info(f"Running: {test_name}")
            logger.info(f"{'='*60}")

            try:
                result = test_func()
                results.append(result)
                logger.info(f"{test_name}: {'PASSED' if result else 'FAILED'}")
            except Exception as e:
                logger.error(f"{test_name}: FAILED with exception: {e}")
                results.append(False)
            finally:
                # テスト間でプロセスクリーンアップ
                self.cleanup_processes()
                time.sleep(2)

        # 総合結果
        all_passed = all(results)
        logger.info(f"\n{'='*60}")
        logger.info(f"Overall Result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
        logger.info(f"{'='*60}")

        return all_passed


def signal_handler(signum, frame):
    """
    シグナルハンドラー

    Ctrl+C等でのプロセス終了時にクリーンアップ
    """
    logger.info("Received interrupt signal, cleaning up...")
    sys.exit(1)


def main():
    """
    メイン関数

    コマンドライン引数でテスト設定を受け取り実行
    """
    parser = argparse.ArgumentParser(description='Communication Integration Tester')
    parser.add_argument('--duration', type=int, default=30,
                       help='Test duration in seconds (default: 30)')
    parser.add_argument('--delay', action='store_true',
                       help='Enable delay simulation test')
    parser.add_argument('--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # シグナルハンドラー設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # テスター初期化・実行
    tester = CommunicationIntegrationTester(
        test_duration=args.duration,
        enable_delay=args.delay
    )

    try:
        logger.info("Communication Integration Tester Starting...")
        success = tester.run_all_tests()

        # 終了コード設定
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        sys.exit(1)
    finally:
        tester.cleanup_processes()


if __name__ == "__main__":
    main()