#!/usr/bin/env python3
"""
Numeric側通信モジュール

ZeroMQ PUB/SUBパターンを使用したNumeric→Plant間通信の実装。
同期プロトコル、RTT測定、非同期通信機能を提供。

主要機能：
- 同期プロトコル実装（Plant側との時刻同期）
- 制御コマンド送信（PUBソケット）
- 状態データ受信（SUBソケット）
- RTT測定・統計
- ノンブロッキング通信（制御ループをブロックしない）
"""

import zmq
import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class NumericCommunicator:
    """
    Numeric側通信クラス

    ZeroMQを使用してPlant側と非同期通信を行う。
    - Numeric→Plant: PUBソケット（制御コマンド送信）
    - Plant→Numeric: SUBソケット（状態データ受信）

    同期プロトコルを実装して、両側で共通の基準時刻を確立し、
    正確なRTT（Round Trip Time）測定を可能にする。
    """

    def __init__(self, plant_state_endpoint: str, cmd_publish_port: int = 5556):
        """
        通信設定の初期化

        Args:
            plant_state_endpoint: Plantからの状態データ受信エンドポイント
            cmd_publish_port: 制御コマンド送信用ポート番号
        """
        self.plant_state_endpoint = plant_state_endpoint
        self.cmd_publish_port = cmd_publish_port
        self.context = zmq.Context()  # ZeroMQコンテキスト

        # ===== ZeroMQソケット設定 =====
        # State subscriber (Plant → Numeric): 状態データ受信
        self.state_subscriber = self.context.socket(zmq.SUB)
        self.state_subscriber.connect(plant_state_endpoint)
        self.state_subscriber.setsockopt(zmq.SUBSCRIBE, b"")  # 全メッセージを受信
        self.state_subscriber.setsockopt(zmq.RCVTIMEO, 10)   # 10ms受信タイムアウト

        # Command publisher (Numeric → Plant): 制御コマンド送信
        self.cmd_publisher = self.context.socket(zmq.PUB)
        self.cmd_publisher.bind(f"tcp://*:{cmd_publish_port}")

        # ===== 通信状態管理 =====
        self.latest_state = None    # 最新の受信状態データ
        self.seq_counter = 0        # シーケンス番号カウンタ

        # ===== 同期タイミング管理 =====
        self.sync_base_time = None  # 同期基準時刻
        self.is_synchronized = False # 同期状態フラグ

        # ===== RTT測定（同期タイムスタンプ使用）=====
        self.command_timestamps = {}  # seq -> sync_timestamp マッピング

        # ===== 通信統計 =====
        self.sent_count = 0       # 送信コマンド数
        self.received_count = 0   # 受信状態数
        self.timeout_count = 0    # タイムアウト数

        logger.info(f"NumericCommunicator setup: SUB from {plant_state_endpoint}, PUB on :{cmd_publish_port}")

        # ZeroMQ接続確立待ち（重要：PUBソケットは接続に時間がかかる）
        time.sleep(1.0)

    def establish_synchronization(self, sync_delay_seconds: float = 3.0):
        """
        同期プロトコルを実行して基準時刻を確立

        Numeric↔Plant間で共通の基準時刻を設定する4段階プロトコル：
        1. Numeric → Plant: READY信号送信
        2. Plant → Numeric: READY_ACK応答受信
        3. Numeric → Plant: SYNC_START信号送信（基準時刻通知）
        4. 両側で基準時刻まで待機→同期完了

        Args:
            sync_delay_seconds: 同期開始までの待機時間[s]
        """
        logger.info("Starting synchronization protocol...")

        # ===== Phase 1: READY信号送信 =====
        ready_msg = {
            "command": "READY",      # コマンド種別
            "sender": "numeric",     # 送信者識別
            "timestamp": time.time() # 送信時刻（参考用）
        }
        self.cmd_publisher.send_json(ready_msg)
        logger.info("Sent READY signal to Plant")

        # ===== Phase 2: READY_ACK応答受信待ち =====
        ready_ack_received = False
        timeout_start = time.time()
        # 10秒間READY_ACK応答を待機
        while not ready_ack_received and (time.time() - timeout_start) < 10.0:
            try:
                msg = self.state_subscriber.recv_json(zmq.NOBLOCK)  # ノンブロッキング受信
                if msg.get("command") == "READY_ACK":
                    ready_ack_received = True
                    logger.info("Received READY_ACK from Plant")
            except zmq.Again:
                time.sleep(0.01)  # 短時間待機後再試行

        if not ready_ack_received:
            raise TimeoutError("Plant did not respond to READY signal within 10 seconds")

        # ===== Phase 3: 同期基準時刻計算・SYNC_START送信 =====
        self.sync_base_time = time.time() + sync_delay_seconds  # 基準時刻設定
        sync_msg = {
            "command": "SYNC_START",
            "sync_base_time": self.sync_base_time,  # 両側共通の基準時刻
            "delay_seconds": sync_delay_seconds,    # 待機時間情報
            "sender": "numeric"
        }
        self.cmd_publisher.send_json(sync_msg)
        logger.info(f"Sent SYNC_START signal, base time: {self.sync_base_time}")

        # ===== Phase 4: 基準時刻まで待機 =====
        while time.time() < self.sync_base_time:
            time.sleep(0.001)  # 1ms精度で待機

        self.is_synchronized = True
        logger.info("Synchronization established successfully")

    def get_sync_timestamp(self) -> float:
        """
        同期基準時刻からの相対時間を取得

        Returns:
            基準時刻からの経過時間[s]（正確なRTT測定に使用）
        """
        if not self.is_synchronized:
            raise ValueError("Not synchronized - call establish_synchronization() first")
        return time.time() - self.sync_base_time

    def start_communication(self):
        """
        通信初期化（PUB/SUB版では不要だが互換性のため）
        同期プロトコルを実行して通信準備完了
        """
        self.establish_synchronization()
        logger.info("Async communication ready with synchronization")

    def stop_communication(self):
        """
        通信停止・リソース解放
        ZeroMQソケットとコンテキストを適切にクローズ
        """
        self.state_subscriber.close()  # SUBソケット終了
        self.cmd_publisher.close()     # PUBソケット終了
        self.context.term()            # ZeroMQコンテキスト終了
        logger.info("Numeric communication stopped")

    def send_command_async(self, seq: int, sim_time: float, command: List[float]):
        """
        非同期でコマンドを送信（ノンブロッキング）

        制御コマンドをPlantに送信。ノンブロッキング送信のため、
        制御ループをブロックすることなく高頻度通信が可能。

        Args:
            seq: シーケンス番号（RTT測定用）
            sim_time: シミュレーション時刻[s]
            command: 制御コマンド [fx, fy, fz] [N]
        """
        if not self.is_synchronized:
            raise ValueError("Not synchronized - call establish_synchronization() first")

        # 同期タイムスタンプ取得（RTT測定用）
        sync_timestamp = self.get_sync_timestamp()

        # 送信メッセージ構築
        cmd_msg = {
            "seq": seq,                          # シーケンス番号
            "t": sim_time,                       # シミュレーション時刻
            "u": command,                        # 制御入力 [fx, fy, fz]
            "sync_timestamp": sync_timestamp,    # 同期タイムスタンプ（RTT測定用）
            "timestamp": time.time()             # 後方互換性のため保持
        }

        # RTT計算用にタイムスタンプを保存
        self.command_timestamps[seq] = sync_timestamp

        # 古いタイムスタンプを削除（メモリリーク防止、最新100個まで保持）
        if len(self.command_timestamps) > 100:
            oldest_seq = min(self.command_timestamps.keys())
            del self.command_timestamps[oldest_seq]

        try:
            # ノンブロッキング送信（制御ループをブロックしない）
            self.cmd_publisher.send_json(cmd_msg, zmq.NOBLOCK)
            self.sent_count += 1
        except zmq.Again:
            # 送信バッファフル時の警告（通常は発生しない）
            logger.warning(f"Command send buffer full for seq={seq}")

    def get_latest_response(self) -> Optional[Dict]:
        """
        最新の応答を取得（ノンブロッキング）

        Plantからの状態データを受信し、RTTを計算。
        複数のメッセージが溜まっている場合は最新のものだけを取得。

        Returns:
            最新の状態データ辞書 or None（データがない場合）
        """
        try:
            # 利用可能な全メッセージを取得し、最新のものだけ保持
            while True:
                try:
                    state_msg = self.state_subscriber.recv_json(zmq.NOBLOCK)  # ノンブロッキング受信
                    recv_time = time.time()

                    # ===== RTT計算（同期タイムスタンプ使用）=====
                    rtt_ms = 0.0
                    latest_cmd_seq = state_msg.get('latest_cmd_seq', -1)

                    if self.is_synchronized and latest_cmd_seq in self.command_timestamps:
                        # 同期タイムスタンプを使用した正確なRTT計算
                        recv_sync_timestamp = self.get_sync_timestamp()
                        send_sync_timestamp = self.command_timestamps[latest_cmd_seq]
                        rtt_ms = (recv_sync_timestamp - send_sync_timestamp) * 1000

                        # 健全性チェック：同期タイムスタンプでは負のRTTは発生しないはず
                        if rtt_ms < 0:
                            logger.error(f"Negative RTT detected: {rtt_ms}ms - sync error for seq={latest_cmd_seq}")
                            rtt_ms = 0.0
                    elif not self.is_synchronized:
                        # 同期していない場合の従来方式（後方互換性）
                        latest_cmd_timestamp = state_msg.get('latest_cmd_timestamp', 0)
                        if latest_cmd_seq in self.command_timestamps:
                            send_time = self.command_timestamps[latest_cmd_seq]
                            rtt_ms = (recv_time - send_time) * 1000

                    # 状態データを構造化して保存
                    self.latest_state = {
                        'plant_response': state_msg,                    # 生の応答データ
                        'seq': state_msg.get('seq', 0),                # シーケンス番号
                        'sim_time': state_msg.get('t', 0),             # シミュレーション時刻
                        'recv_time': recv_time,                        # 受信時刻
                        'rtt_ms': rtt_ms,                             # ラウンドトリップ時間[ms]
                        'valid': state_msg.get('valid', False)         # データ有効性フラグ
                    }
                    self.received_count += 1
                except zmq.Again:
                    # 受信待ちメッセージなし→ループ終了
                    break
        except Exception as e:
            logger.warning(f"Error receiving state: {e}")

        return self.latest_state

    def get_communication_stats(self) -> Dict:
        """
        通信統計を取得

        Returns:
            通信統計辞書（送信数、受信数、タイムアウト数）
        """
        return {
            'sent_count': self.sent_count,
            'received_count': self.received_count,
            'timeout_count': self.timeout_count,
            'is_synchronized': self.is_synchronized
        }


class NumericCommunicationManager:
    """
    Numeric通信マネージャー

    設定ファイルから通信パラメータを読み込み、
    NumericCommunicatorを初期化・管理する。
    """

    def __init__(self, config: Dict):
        """
        通信マネージャー初期化

        Args:
            config: 設定辞書（YAMLから読み込み）
        """
        self.config = config
        self.communicator = None

    def setup_communication(self, plant_endpoint: str) -> NumericCommunicator:
        """
        設定に基づいて通信を初期化

        Args:
            plant_endpoint: Plant状態データ受信エンドポイント

        Returns:
            設定済みのNumericCommunicatorインスタンス
        """
        # 制御コマンド送信ポート
        cmd_publish_port = 5556

        # NumericCommunicator初期化
        self.communicator = NumericCommunicator(plant_endpoint, cmd_publish_port)

        return self.communicator

    def cleanup(self):
        """
        リソース解放
        """
        if self.communicator:
            self.communicator.stop_communication()