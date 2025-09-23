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
        self.latest_command_timestamp = 0.0  # 最新コマンドのタイムスタンプ
        self.latest_command_seq = -1         # 最新コマンドのシーケンス番号

        # ===== 通信遅延シミュレーション =====
        self.enable_delay = False      # 遅延シミュレーション有効/無効
        self.processing_delay = 0.0    # 処理遅延[s]
        self.response_delay = 0.0      # 応答遅延[s]
        self.delay_variation = 0.0     # 遅延変動[s]
        self.command_queue = []        # 遅延適用用コマンドキュー

        logger.info(f"PlantCommunicator setup: PUB on :{state_pub_port}, SUB on {cmd_sub_endpoint}")

        # ZeroMQ接続確立待ち
        time.sleep(1.0)

    def configure_delay_simulation(self, enable: bool, processing_delay_ms: float = 0.0,
                                 response_delay_ms: float = 0.0, delay_variation_ms: float = 0.0):
        """
        通信遅延シミュレーション設定

        Args:
            enable: 遅延シミュレーション有効化
            processing_delay_ms: 処理遅延[ms]
            response_delay_ms: 応答遅延[ms]
            delay_variation_ms: 遅延変動[ms]
        """
        self.enable_delay = enable
        self.processing_delay = processing_delay_ms / 1000.0  # ms → s
        self.response_delay = response_delay_ms / 1000.0      # ms → s
        self.delay_variation = delay_variation_ms / 1000.0    # ms → s

        if self.enable_delay:
            logger.info(f"Communication delay enabled: processing={processing_delay_ms:.1f}ms, "
                       f"response={response_delay_ms:.1f}ms, variation={delay_variation_ms:.1f}ms")

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

                    # RTT測定用データ更新
                    self.latest_command_timestamp = cmd_msg.get('timestamp', recv_time)
                    self.latest_command_seq = cmd_msg.get('seq', 0)

                    control_input = cmd_msg.get('u', [0.0, 0.0, 0.0])

                    if self.enable_delay:
                        # ===== 遅延シミュレーション =====
                        total_delay = self.processing_delay + self.response_delay
                        if self.delay_variation > 0:
                            # 遅延変動を追加
                            total_delay += np.random.uniform(-self.delay_variation, self.delay_variation)

                        # 遅延キューに追加
                        apply_time = recv_time + total_delay
                        self.command_queue.append({
                            'control_input': control_input,
                            'apply_time': apply_time,
                            'seq': cmd_msg.get('seq', 0),
                            'original_timestamp': self.latest_command_timestamp
                        })
                        return None  # 遅延適用のため即座には返さない
                    else:
                        # ===== 即座適用 =====
                        return control_input

                except zmq.Again:
                    break  # 受信待ちメッセージなし

        except Exception as e:
            logger.warning(f"Error receiving commands: {e}")

        return None

    def process_delayed_commands(self) -> Optional[List[float]]:
        """
        遅延キューから適用時刻に達したコマンドを処理

        Returns:
            適用すべき制御コマンド [fx, fy, fz] or None
        """
        if not self.enable_delay:
            return None

        current_time = time.time()
        applied_command = None

        # 適用時刻に達したコマンドを探す
        commands_to_remove = []
        for cmd in self.command_queue:
            if current_time >= cmd['apply_time']:
                applied_command = cmd['control_input']
                commands_to_remove.append(cmd)

        # 適用済みコマンドを削除
        for cmd in commands_to_remove:
            self.command_queue.remove(cmd)

        return applied_command

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
        if self.enable_delay and self.response_delay > 0:
            delay_time = self.response_delay
            if self.delay_variation > 0:
                delay_time += np.random.uniform(-self.delay_variation, self.delay_variation)
            effective_timestamp = current_time + delay_time

        # 状態データメッセージ構築
        state_msg = {
            "seq": seq,                                    # シーケンス番号
            "t": sim_time,                                # シミュレーション時刻
            "y": state_data,                              # 状態データ
            "valid": True,                                # データ有効性フラグ
            "timestamp": effective_timestamp,             # 有効タイムスタンプ（RTT計算用）
            "sync_timestamp": self.get_sync_timestamp(),  # 同期タイムスタンプ
            "is_synchronized": self.is_synchronized,      # 同期状態
            # RTT測定用データ
            "latest_cmd_timestamp": self.latest_command_timestamp,
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

        # 遅延シミュレーション設定
        comm_config = self.config.get('communication', {})
        if comm_config:
            enable_delay = comm_config.get('enable_delay', False)
            processing_delay = comm_config.get('processing_delay', 0.0)
            response_delay = comm_config.get('response_delay', 0.0)
            delay_variation = comm_config.get('delay_variation', 0.0)

            self.communicator.configure_delay_simulation(
                enable_delay, processing_delay, response_delay, delay_variation
            )

        return self.communicator

    def cleanup(self):
        """
        リソース解放
        """
        if self.communicator:
            self.communicator.stop_communication()