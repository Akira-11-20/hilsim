#!/usr/bin/env python3
"""
Plant側通信モジュール

ZeroMQ PUB/SUBパターンを使用したPlant→Numeric間通信の実装。
同期プロトコル、遅延シミュレーション、RTT測定機能を提供。

主要機能：
- 同期プロトコル実装（Numeric側との時刻同期）
- 状態データ配信（PUBソケット）
- 制御コマンド受信（SUBソケット）
- 通信遅延シミュレーション
- RTT測定・ログ記録
"""

import zmq
import time
import numpy as np
import logging
import json
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PlantCommunicator:
    """
    Plant側通信クラス

    ZeroMQを使用してNumeric側と非同期通信を行う。
    - Plant→Numeric: PUBソケット（状態データ配信）
    - Numeric→Plant: SUBソケット（制御コマンド受信）
    """

    def __init__(self, state_pub_port: int = 5555, cmd_sub_endpoint: str = "tcp://numeric:5556"):
        """
        通信初期化

        Args:
            state_pub_port: 状態データ配信用ポート
            cmd_sub_endpoint: 制御コマンド受信エンドポイント
        """
        self.state_pub_port = state_pub_port
        self.cmd_sub_endpoint = cmd_sub_endpoint
        self.context = zmq.Context()

        # ===== ZeroMQソケット設定 =====
        # State publisher (Plant → Numeric): 状態データ配信
        self.state_publisher = self.context.socket(zmq.PUB)
        self.state_publisher.bind(f"tcp://*:{state_pub_port}")

        # Command subscriber (Numeric → Plant): 制御コマンド受信
        self.cmd_subscriber = self.context.socket(zmq.SUB)
        self.cmd_subscriber.connect(cmd_sub_endpoint)
        self.cmd_subscriber.setsockopt(zmq.SUBSCRIBE, b"")  # 全メッセージ受信
        self.cmd_subscriber.setsockopt(zmq.RCVTIMEO, 1)    # 1ms受信タイムアウト

        # ===== 同期管理 =====
        self.sync_base_time = None   # 同期基準時刻
        self.is_synchronized = False # 同期状態フラグ

        # ===== RTT測定 =====
        self.latest_command_timestamp = 0.0      # 最新コマンドのタイムスタンプ
        self.latest_command_sync_timestamp = 0.0 # 最新コマンドの同期タイムスタンプ
        self.latest_command_seq = -1             # 最新コマンドのシーケンス番号

        # ===== 通信遅延シミュレーション（enhanced） =====
        self.enable_delay = False      # 遅延シミュレーション有効/無効
        self.base_delay_ms = 0.0       # 基本処理遅延[ms]
        self.network_delay_ms = 0.0    # ネットワーク遅延[ms]
        self.jitter_ms = 0.0           # ジッタ振幅[ms]
        self.jitter_type = "uniform"   # ジッタ分布型（uniform/gaussian/exponential）
        self.command_queue = []        # 遅延適用用コマンドキュー

        # ===== 統計・分析 =====
        self.message_count = 0         # メッセージ処理数
        self.delay_history = []        # 遅延履歴（最近1000件）
        self.stats_interval = 100      # 統計表示間隔

        logger.info(f"PlantCommunicator setup: PUB on :{state_pub_port}, SUB on {cmd_sub_endpoint}")

        # ZeroMQ接続確立待ち
        time.sleep(1.0)

    def configure_delay_simulation(self, enable: bool, base_delay_ms: float = 0.0,
                                 network_delay_ms: float = 0.0, jitter_ms: float = 0.0,
                                 jitter_type: str = "uniform"):
        """
        通信遅延シミュレーション設定（enhanced版）

        Args:
            enable: 遅延シミュレーション有効化
            base_delay_ms: 基本処理遅延[ms]
            network_delay_ms: ネットワーク遅延[ms]
            jitter_ms: ジッタ振幅[ms]
            jitter_type: ジッタ分布型（uniform/gaussian/exponential）
        """
        self.enable_delay = enable
        self.base_delay_ms = base_delay_ms
        self.network_delay_ms = network_delay_ms
        self.jitter_ms = jitter_ms
        self.jitter_type = jitter_type

        total_fixed_delay = base_delay_ms + network_delay_ms

        if self.enable_delay:
            logger.info(f"Enhanced delay simulation enabled:")
            logger.info(f"  Base Processing: {base_delay_ms:.1f}ms")
            logger.info(f"  Network Simulation: {network_delay_ms:.1f}ms")
            logger.info(f"  Jitter: {jitter_ms:.1f}ms ({jitter_type})")
            logger.info(f"  Total Fixed: {total_fixed_delay:.1f}ms")

    def generate_jitter(self):
        """ジッタ生成（communication_test_containersと同じアルゴリズム）"""
        if self.jitter_ms <= 0:
            return 0.0

        if self.jitter_type == "uniform":
            return np.random.uniform(-self.jitter_ms, self.jitter_ms)
        elif self.jitter_type == "gaussian":
            return np.random.normal(0, self.jitter_ms / 3.0)  # 3σ = jitter_ms
        elif self.jitter_type == "exponential":
            return np.clip(np.random.exponential(self.jitter_ms / 2.0), 0, self.jitter_ms)
        else:
            return 0.0

    def apply_delay(self, delay_ms):
        """高精度遅延適用"""
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

    def print_delay_statistics(self):
        """遅延統計表示"""
        if len(self.delay_history) > 0:
            recent_delays = self.delay_history[-self.stats_interval:]
            avg_delay = np.mean(recent_delays)
            std_delay = np.std(recent_delays)
            min_delay = np.min(recent_delays)
            max_delay = np.max(recent_delays)

            logger.info(f"Plant delay stats (last {len(recent_delays)}): "
                       f"{avg_delay:.2f}±{std_delay:.2f}ms [{min_delay:.2f}-{max_delay:.2f}ms]")

    def get_sync_timestamp(self) -> float:
        """
        同期基準時刻からの相対時間を取得

        Returns:
            基準時刻からの経過時間[s]（同期前は0.0）
        """
        if not self.is_synchronized:
            return 0.0
        return time.time() - self.sync_base_time

    def handle_sync_protocol(self, msg: Dict) -> bool:
        """
        同期プロトコルメッセージを処理

        Args:
            msg: 受信メッセージ辞書

        Returns:
            True: 同期プロトコルメッセージを処理した
            False: 通常メッセージ（処理不要）
        """
        command = msg.get("command")

        if command == "READY":
            # ===== Phase 2: READY_ACK応答送信 =====
            ack_msg = {
                "command": "READY_ACK",
                "sender": "plant",
                "timestamp": time.time()
            }
            self.state_publisher.send_json(ack_msg)
            logger.info("Sent READY_ACK to Numeric")
            return True

        elif command == "SYNC_START":
            # ===== Phase 4: 同期基準時刻設定・待機 =====
            self.sync_base_time = msg.get("sync_base_time")
            if self.sync_base_time:
                # 同期時刻まで正確に待機
                while time.time() < self.sync_base_time:
                    time.sleep(0.001)
                self.is_synchronized = True
                logger.info(f"Synchronization established, base time: {self.sync_base_time}")
            else:
                logger.error("SYNC_START message missing sync_base_time")
            return True

        return False  # 通常メッセージ

    def wait_for_synchronization(self, timeout_seconds: float = 30.0):
        """
        Numeric側からの同期プロトコル待機

        Args:
            timeout_seconds: タイムアウト時間[s]
        """
        logger.info("Waiting for synchronization protocol from Numeric...")

        timeout_start = time.time()
        while not self.is_synchronized and (time.time() - timeout_start) < timeout_seconds:
            try:
                cmd_msg = self.cmd_subscriber.recv_json(zmq.NOBLOCK)
                if self.handle_sync_protocol(cmd_msg):
                    continue  # 同期プロトコルメッセージを処理
            except zmq.Again:
                time.sleep(0.01)

        if not self.is_synchronized:
            logger.warning("Synchronization timeout - continuing without sync")

    def receive_commands(self) -> Optional[List[float]]:
        """
        制御コマンド受信（ノンブロッキング）

        遅延シミュレーション有効時は遅延キューに追加、
        無効時は即座に適用。

        Returns:
            制御コマンド [fx, fy, fz] or None（コマンドなし）
        """
        try:
            while True:
                try:
                    cmd_msg = self.cmd_subscriber.recv_json(zmq.NOBLOCK)
                    recv_time = time.time()

                    # 同期プロトコルメッセージをチェック
                    if self.handle_sync_protocol(cmd_msg):
                        continue

                    # RTT測定用データ更新（遅延処理に関係なく即座に記録）
                    self.latest_command_timestamp = cmd_msg.get('timestamp', recv_time)
                    # 受信時点での同期タイムスタンプを記録（遅延シミュレーションは適用しない）
                    if self.is_synchronized:
                        self.latest_command_sync_timestamp = self.get_sync_timestamp()
                    else:
                        self.latest_command_sync_timestamp = cmd_msg.get('sync_timestamp', 0.0)
                    self.latest_command_seq = cmd_msg.get('seq', 0)

                    control_input = cmd_msg.get('u', [0.0, 0.0, 0.0])

                    if self.enable_delay:
                        # ===== Simple遅延シミュレーション（communication_test_containersスタイル）=====
                        # ジッタ生成
                        jitter = self.generate_jitter()
                        total_delay_ms = self.base_delay_ms + self.network_delay_ms + jitter

                        # 遅延適用（シンプルに全体遅延を一度に適用）
                        self.apply_delay(total_delay_ms)

                        # 統計更新
                        self.delay_history.append(total_delay_ms)
                        self.message_count += 1

                        # メモリ管理：最新1000件まで保持
                        if len(self.delay_history) > 1000:
                            self.delay_history = self.delay_history[-500:]

                        # 定期的統計表示
                        if self.message_count % self.stats_interval == 0:
                            self.print_delay_statistics()

                        return control_input  # 遅延適用後に返す
                    else:
                        # ===== 即座適用 =====
                        return control_input

                except zmq.Again:
                    break  # 受信待ちメッセージなし

        except Exception as e:
            logger.warning(f"Error receiving commands: {e}")

        return None

    def broadcast_state(self, seq: int, sim_time: float, state_data: Dict):
        """
        状態データを配信

        Args:
            seq: シーケンス番号
            sim_time: シミュレーション時刻[s]
            state_data: 状態データ辞書（position, velocity, acceleration等）
        """
        current_time = time.time()
        effective_timestamp = current_time

        # 応答遅延シミュレーション（RTT計算への影響なしでタイムスタンプ調整）
        if self.enable_delay and self.network_delay_ms > 0:
            delay_time_ms = self.network_delay_ms + self.generate_jitter()
            effective_timestamp = current_time + (delay_time_ms / 1000.0)

        # RTT測定用の正確なタイムスタンプ（遅延シミュレーションの影響を除く）
        rtt_timestamp = current_time if not self.enable_delay else current_time

        # 状態データメッセージ構築
        state_msg = {
            "seq": seq,                                    # シーケンス番号
            "t": sim_time,                                # シミュレーション時刻
            "y": state_data,                              # 状態データ
            "valid": True,                                # データ有効性フラグ
            "timestamp": rtt_timestamp,                   # RTT計算用タイムスタンプ（遅延無し）
            "sync_timestamp": self.get_sync_timestamp(),  # 現在の同期タイムスタンプ
            "is_synchronized": self.is_synchronized,      # 同期状態
            # RTT測定用データ
            "latest_cmd_timestamp": self.latest_command_timestamp,
            "latest_cmd_sync_timestamp": self.latest_command_sync_timestamp,
            "latest_cmd_seq": self.latest_command_seq
        }

        # 状態データ配信
        self.state_publisher.send_json(state_msg)

    def stop_communication(self):
        """
        通信停止・リソース解放
        """
        self.state_publisher.close()  # PUBソケット終了
        self.cmd_subscriber.close()   # SUBソケット終了
        self.context.term()           # ZeroMQコンテキスト終了
        logger.info("Plant communication stopped")


class PlantCommunicationManager:
    """
    Plant通信マネージャー

    設定ファイルから通信パラメータを読み込み、
    PlantCommunicatorを初期化・管理する。
    """

    def __init__(self, config: Dict):
        """
        通信マネージャー初期化

        Args:
            config: 設定辞書（YAMLから読み込み）
        """
        self.config = config
        self.communicator = None

    def setup_communication(self) -> PlantCommunicator:
        """
        設定に基づいて通信を初期化

        Returns:
            設定済みのPlantCommunicatorインスタンス
        """
        # 通信エンドポイント設定
        state_pub_port = 5555
        cmd_sub_endpoint = "tcp://numeric:5556"

        # PlantCommunicator初期化
        self.communicator = PlantCommunicator(state_pub_port, cmd_sub_endpoint)

        # Enhanced遅延シミュレーション設定
        comm_config = self.config.get('communication', {})
        if comm_config:
            enable_delay = comm_config.get('enable_delay', False)
            # 新しいパラメータ構成
            base_delay = comm_config.get('base_delay_ms', 0.0)
            network_delay = comm_config.get('network_delay_ms', 0.0)
            jitter = comm_config.get('jitter_ms', 0.0)
            jitter_type = comm_config.get('jitter_type', 'uniform')

            # 後方互換性：古いパラメータが設定されている場合
            if 'processing_delay' in comm_config:
                base_delay = comm_config.get('processing_delay', 0.0)
            if 'response_delay' in comm_config:
                network_delay = comm_config.get('response_delay', 0.0)
            if 'delay_variation' in comm_config:
                jitter = comm_config.get('delay_variation', 0.0)

            self.communicator.configure_delay_simulation(
                enable_delay, base_delay, network_delay, jitter, jitter_type
            )

        return self.communicator

    def cleanup(self):
        """
        リソース解放
        """
        if self.communicator:
            self.communicator.stop_communication()