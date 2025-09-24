# PUB/SUB vs REQ/REP 通信パターンの違い

## 基本的な通信パターン

### REQ/REP (Request-Reply)
```
Client (REQ) ----request----> Server (REP)
Client (REQ) <----reply----- Server (REP)
```
- **同期通信**: リクエストを送ったら必ずレスポンスを待つ
- **1対1**: 一つのREQに対して一つのREP
- **順序保証**: メッセージの順序が保たれる

### PUB/SUB (Publisher-Subscriber)
```
Publisher (PUB) ----message----> Subscriber (SUB)
Publisher (PUB) ----message----> Subscriber (SUB)
Publisher (PUB) ----message----> Subscriber (SUB)
```
- **非同期通信**: メッセージを送りっぱなし、応答を待たない
- **1対多**: 一つのPUBから複数のSUBに配信
- **順序保証なし**: メッセージの順序や到達が保証されない

## 具体的な動作の違い

### REQ/REP の動作
```python
# Client側 (REQ)
socket.send_string("Hello")          # メッセージ送信
response = socket.recv_string()      # レスポンス受信（ブロック）
print(f"Got: {response}")           # "Got: Echo: Hello"

# Server側 (REP)
message = socket.recv_string()       # リクエスト受信（ブロック）
socket.send_string(f"Echo: {message}")  # レスポンス送信
```

### PUB/SUB の動作
```python
# Publisher側 (PUB)
socket.send_string("Hello")          # メッセージ配信（ノンブロック）
socket.send_string("World")          # 次のメッセージ配信
# レスポンスは期待しない

# Subscriber側 (SUB)
message1 = socket.recv_string()      # メッセージ受信（ブロック可能）
message2 = socket.recv_string()      # 次のメッセージ受信
# 送信者に応答しない
```

## HILSシステムでの問題

### 元のHILS実装（PUB/SUB）の問題
```
Numeric (PUB) ----command----> Plant (SUB)
Numeric (SUB) <----state----- Plant (PUB)
```

**問題点:**
1. **RTT測定の困難**
   - コマンド送信と状態受信が別々のメッセージ
   - どのコマンドに対する状態かが不明確

2. **バッファリング**
   - メッセージがZeroMQ内部バッファに蓄積
   - 処理が追いつかないと遅延が累積

3. **非同期性**
   - 送信したコマンドがいつ処理されるか不明
   - 状態データがいつのコマンドに対応するか不明

### 修正版HILS実装（REQ/REP）の利点
```
Numeric (REQ) ----request----> Plant (REP)
Numeric (REQ) <----response--- Plant (REP)
```

**利点:**
1. **正確なRTT測定**
   - リクエスト送信からレスポンス受信まで明確
   - 1対1対応で測定が簡単

2. **バッファリング最小化**
   - 同期通信でメッセージの蓄積を防ぐ
   - 即座に処理される

3. **確実な応答**
   - 必ずレスポンスが返る（タイムアウト設定可能）
   - エラー処理が明確

## 実測結果の比較

### REQ/REP（調査結果）
```
RTT Mean: 1.724 ± 0.113ms
RTT Range: 1.426 - 2.409ms
Growth Factor: 0.93x (改善傾向)
✅ RTT STABLE
```

### PUB/SUB（調査結果）
```
RTT Mean: 1142.421 ± 58.701ms
RTT Range: 1014.961 - 1205.397ms
Growth Factor: 1.09x (増加傾向)
⚠️ RTT HIGH LATENCY
```

**差は約670倍！**

## なぜPUB/SUBでRTTが増加するのか

### 1. メッセージキューイング
```
PUB側: [msg1][msg2][msg3][msg4]... (送信キュー)
SUB側: [msg1][msg2][msg3][msg4]... (受信キュー)
```
- メッセージが蓄積される
- 処理速度 < 送信速度 の場合、遅延が累積

### 2. 非同期処理
```python
# PUB/SUBの場合
pub.send("command_1")    # t=0ms
pub.send("command_2")    # t=20ms
pub.send("command_3")    # t=40ms
# この時点でsub側はまだcommand_1を処理中の可能性

# REQ/REPの場合
req.send("command_1")    # t=0ms
response = req.recv()    # t=1.7ms (処理完了を確認)
req.send("command_2")    # t=20ms (前の処理が完了してから)
```

### 3. RTT測定の複雑化
```python
# PUB/SUBでのRTT測定（複雑）
command_timestamps[seq] = send_time    # コマンド送信時刻を記録
# ... 別のメッセージで状態受信
state = sub.recv()
latest_cmd_seq = state["latest_cmd_seq"]  # どのコマンドに対する状態？
if latest_cmd_seq in command_timestamps:
    rtt = recv_time - command_timestamps[latest_cmd_seq]  # 推定RTT

# REQ/REPでのRTT測定（シンプル）
send_time = time.perf_counter()
req.send(request)
response = req.recv()
recv_time = time.perf_counter()
rtt = recv_time - send_time  # 正確なRTT
```

## 使い分けの指針

### REQ/REPが適している場面
- **リアルタイム制御** ← HILSシステム
- 確実な応答が必要
- RTT測定が重要
- 1対1通信

### PUB/SUBが適している場面
- **データ配信・ストリーミング**
- 高スループットが必要
- 1対多通信
- 一部のメッセージ損失が許容される

## HILSシステムでの結論

**HILSシステムはリアルタイム制御システム**のため：
- 確実な応答が必要
- 低レイテンシが重要
- RTT測定が必須

→ **REQ/REPパターンが最適**

PUB/SUBの非同期・高スループット特性は、HILSの要求と合わない。