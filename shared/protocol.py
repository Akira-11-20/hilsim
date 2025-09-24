#!/usr/bin/env python3
"""
HILS 通信プロトコル定義

参考構造（communication_test_containers）に基づく
シンプルで高性能なUDP通信プロトコル実装。

主要機能:
- Network byte order (big-endian) パケット
- データ整合性チェック
- 高精度RTT測定
- 統計・分析対応
"""

import struct
import time
import hashlib
from typing import Tuple, Optional
from dataclasses import dataclass


# ===== パケット構造定義 =====

@dataclass
class RequestPacket:
    """制御コマンドパケット（Numeric→Plant）"""
    sequence_number: int
    timestamp: float
    fx: float  # X方向力[N]
    fy: float  # Y方向力[N]
    fz: float  # Z方向力[N]


@dataclass
class ResponsePacket:
    """状態応答パケット（Plant→Numeric）"""
    sequence_number: int
    timestamp: float
    pos_x: float    # X座標[m]
    pos_y: float    # Y座標[m]
    pos_z: float    # Z座標（高度）[m]
    vel_x: float    # X速度[m/s]
    vel_y: float    # Y速度[m/s]
    vel_z: float    # Z速度[m/s]
    acc_x: float    # X加速度[m/s²]
    acc_y: float    # Y加速度[m/s²]
    acc_z: float    # Z加速度[m/s²]


class ProtocolHandler:
    """プロトコル処理クラス"""

    # パケットフォーマット（Network byte order）
    REQUEST_FORMAT = "!IdfffQ"        # int32, double, 3*float, uint64
    RESPONSE_FORMAT = "!IdfffffffffQ"  # int32, double, 9*float, uint64

    REQUEST_SIZE = struct.calcsize(REQUEST_FORMAT)    # 32 bytes
    RESPONSE_SIZE = struct.calcsize(RESPONSE_FORMAT)  # 72 bytes

    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """データ整合性チェックサム計算"""
        return int(hashlib.md5(data).hexdigest()[:16], 16)

    @classmethod
    def pack_request(cls, packet: RequestPacket) -> bytes:
        """リクエストパケットをバイナリにパック"""
        # チェックサム計算用のデータ部分
        data_part = struct.pack("!Idfff",
                               packet.sequence_number,
                               packet.timestamp,
                               packet.fx, packet.fy, packet.fz)

        checksum = cls.calculate_checksum(data_part)

        # 完全なパケット構築
        return struct.pack(cls.REQUEST_FORMAT,
                          packet.sequence_number,
                          packet.timestamp,
                          packet.fx, packet.fy, packet.fz,
                          checksum)

    @classmethod
    def unpack_request(cls, data: bytes) -> Optional[RequestPacket]:
        """バイナリデータからリクエストパケットをアンパック"""
        if len(data) != cls.REQUEST_SIZE:
            return None

        try:
            unpacked = struct.unpack(cls.REQUEST_FORMAT, data)
            seq, timestamp, fx, fy, fz, received_checksum = unpacked

            # チェックサム検証
            data_part = data[:-8]  # チェックサム部分を除く
            expected_checksum = cls.calculate_checksum(data_part)

            if received_checksum != expected_checksum:
                return None  # チェックサム不一致

            return RequestPacket(seq, timestamp, fx, fy, fz)

        except struct.error:
            return None

    @classmethod
    def pack_response(cls, packet: ResponsePacket) -> bytes:
        """レスポンスパケットをバイナリにパック"""
        # チェックサム計算用のデータ部分
        data_part = struct.pack("!Idfffffffff",
                               packet.sequence_number,
                               packet.timestamp,
                               packet.pos_x, packet.pos_y, packet.pos_z,
                               packet.vel_x, packet.vel_y, packet.vel_z,
                               packet.acc_x, packet.acc_y, packet.acc_z)

        checksum = cls.calculate_checksum(data_part)

        # 完全なパケット構築
        return struct.pack(cls.RESPONSE_FORMAT,
                          packet.sequence_number,
                          packet.timestamp,
                          packet.pos_x, packet.pos_y, packet.pos_z,
                          packet.vel_x, packet.vel_y, packet.vel_z,
                          packet.acc_x, packet.acc_y, packet.acc_z,
                          checksum)

    @classmethod
    def unpack_response(cls, data: bytes) -> Optional[ResponsePacket]:
        """バイナリデータからレスポンスパケットをアンパック"""
        if len(data) != cls.RESPONSE_SIZE:
            return None

        try:
            unpacked = struct.unpack(cls.RESPONSE_FORMAT, data)
            seq, timestamp, pos_x, pos_y, pos_z, vel_x, vel_y, vel_z, acc_x, acc_y, acc_z, received_checksum = unpacked

            # チェックサム検証
            data_part = data[:-8]  # チェックサム部分を除く
            expected_checksum = cls.calculate_checksum(data_part)

            if received_checksum != expected_checksum:
                return None  # チェックサム不一致

            return ResponsePacket(seq, timestamp, pos_x, pos_y, pos_z,
                                vel_x, vel_y, vel_z, acc_x, acc_y, acc_z)

        except struct.error:
            return None


# ===== 便利関数 =====

def create_request_packet(seq: int, fx: float, fy: float, fz: float) -> RequestPacket:
    """リクエストパケット生成（タイムスタンプ自動設定）"""
    return RequestPacket(seq, time.time(), fx, fy, fz)


def create_response_packet(seq: int, position: Tuple[float, float, float],
                         velocity: Tuple[float, float, float],
                         acceleration: Tuple[float, float, float]) -> ResponsePacket:
    """レスポンスパケット生成（タイムスタンプ自動設定）"""
    return ResponsePacket(
        seq, time.time(),
        position[0], position[1], position[2],
        velocity[0], velocity[1], velocity[2],
        acceleration[0], acceleration[1], acceleration[2]
    )


# ===== テスト用 =====

if __name__ == "__main__":
    """プロトコル動作テスト"""

    # リクエストパケットテスト
    req = create_request_packet(123, 1.0, 2.0, 9.81)
    req_data = ProtocolHandler.pack_request(req)
    req_unpacked = ProtocolHandler.unpack_request(req_data)

    print(f"Request original: {req}")
    print(f"Request unpacked: {req_unpacked}")
    print(f"Request test: {req == req_unpacked}")
    print(f"Request size: {len(req_data)} bytes")

    # レスポンスパケットテスト
    resp = create_response_packet(123, (0, 0, 10), (0, 0, 1), (0, 0, -9.81))
    resp_data = ProtocolHandler.pack_response(resp)
    resp_unpacked = ProtocolHandler.unpack_response(resp_data)

    print(f"Response original: {resp}")
    print(f"Response unpacked: {resp_unpacked}")
    print(f"Response test: {resp == resp_unpacked}")
    print(f"Response size: {len(resp_data)} bytes")