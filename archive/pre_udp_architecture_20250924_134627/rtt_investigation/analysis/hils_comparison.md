# 元のHILS実装 vs 調査結果比較

## 元のHILS通信アーキテクチャ

### Plant側 (plant_communication.py)
```
Plant → Numeric: PUBソケット (port 5555) - 状態データ配信
Numeric → Plant: SUBソケット (tcp://numeric:5556) - 制御コマンド受信
```

### Numeric側 (numeric_communication.py)
```
Plant → Numeric: SUBソケット (tcp://plant:5555) - 状態データ受信
Numeric → Plant: PUBソケット (port 5556) - 制御コマンド送信
```

## 問題の根本原因

### 1. PUB/SUB双方向通信の複雑性

**調査で判明した問題:**
- PUB/SUB単方向: 1142ms平均RTT
- REQ/REP双方向: 1.7ms平均RTT (約670倍の差)

**HILSでの実装問題:**
- 双方向PUB/SUBでさらに複雑化
- 異なるポート間でのメッセージ同期の困難
- バッファリングの蓄積効果

### 2. RTT測定方式の問題

**元のHILS実装:**
```python
# Numeric側でコマンド送信
self.command_timestamps[seq] = (sync_timestamp, send_perf_time)

# Plant側で状態配信時にRTT情報を埋め込み
state_msg = {
    "latest_cmd_timestamp": self.latest_command_timestamp,
    "latest_cmd_sync_timestamp": self.latest_command_sync_timestamp,
    "latest_cmd_seq": self.latest_command_seq
}

# Numeric側でRTT計算
rtt_ms = (plant_sync_timestamp - send_sync_timestamp) * 1000
```

**問題点:**
1. **メッセージ順序の不保証**: PUB/SUBでは順序保証なし
2. **タイムスタンプ同期の複雑さ**: 複雑な同期プロトコル
3. **遅延の累積**: 各段階でのバッファリング遅延

### 3. リアルタイム制約との不整合

**HILSシステムの要求:**
- 50Hz (20ms周期) の厳格なリアルタイム制御
- 低レイテンシ通信が必須

**PUB/SUBの特性:**
- 非同期・バッファリング通信
- スループット重視、レイテンシは二の次
- リアルタイム制御に不適

## 推奨修正方針

### Option 1: REQ/REPへの全面変更
```python
# Plant側: REPサーバー
socket = context.socket(zmq.REP)
socket.bind("tcp://*:5555")

# Numeric側: REQクライアント
socket = context.socket(zmq.REQ)
socket.connect("tcp://plant:5555")
```

**メリット:**
- RTTが安定 (1.7ms)
- 実装が簡単
- 確実な応答保証

**デメリット:**
- 1対1通信のみ
- Numericが主導権を持つ必要

### Option 2: ハイブリッド通信
```python
# 制御ループ: REQ/REP (低レイテンシ重視)
# ログ・監視: PUB/SUB (スループット重視)
```

### Option 3: PUB/SUB最適化
```python
# バッファサイズ制限
socket.setsockopt(zmq.SNDHWM, 1)  # 送信バッファ1メッセージ
socket.setsockopt(zmq.RCVHWM, 1)  # 受信バッファ1メッセージ

# 即座配信
socket.setsockopt(zmq.IMMEDIATE, 1)
```

## 実装優先順位

1. **Option 1 (REQ/REP)**: 最も確実、調査で実証済み
2. **Option 2 (ハイブリッド)**: 柔軟性と性能のバランス
3. **Option 3 (最適化)**: 現在の構造を維持

## 次のステップ

元のHILSシステムにOption 1を適用して動作確認を行う