# 通信モジュールテストガイド

HILS システムの通信モジュールをテストするためのスクリプトとコマンドの説明。

## 概要

通信モジュールが分離されたことで、以下の独立したテストが可能になりました：

- **Plant側通信テスト**: 物理シミュレーションなしで通信機能をテスト
- **Numeric側通信テスト**: 制御アルゴリズムなしで通信機能をテスト
- **統合通信テスト**: Plant↔Numeric間の完全な通信フローをテスト

## テストファイル構成

```
hilsim/
├── test_communication_integration.py    # 統合通信テスト
├── plant/app/
│   ├── test_plant_communication.py      # Plant側通信テスト
│   └── plant_communication.py           # Plant側通信モジュール
└── numeric/app/
    ├── test_numeric_communication.py    # Numeric側通信テスト
    └── numeric_communication.py         # Numeric側通信モジュール
```

## 実行方法

### 1. 統合通信テスト（推奨）

Plant・Numericの両プロセスを起動して通信をテスト：

```bash
# 基本的な通信テスト（20秒間）
make test-comm

# 遅延シミュレーション付きテスト
make test-comm-delay
```

### 2. 個別モジュールテスト

#### Plant側通信テスト
```bash
# 基本テスト
make test-plant-comm

# 手動実行（より詳細な設定）
cd plant/app
python test_plant_communication.py --duration 30 --delay
```

#### Numeric側通信テスト
```bash
# 基本テスト
make test-numeric-comm

# 手動実行（より詳細な設定）
cd numeric/app
python test_numeric_communication.py --duration 30 --verbose
```

### 3. 手動詳細テスト

統合テストを手動で詳細設定付きで実行：

```bash
# 60秒間のテスト
python test_communication_integration.py --duration 60

# 遅延シミュレーション付き + 詳細ログ
python test_communication_integration.py --duration 30 --delay --verbose
```

## テスト項目

### Plant側通信テスト

- **基本通信**: ソケット設定、メッセージ送受信
- **同期プロトコル**: Numeric側との時刻同期
- **遅延シミュレーション**: 処理・応答遅延の模擬
- **状態データ配信**: 模擬物理データの送信
- **コマンド受信**: 制御コマンドの受信処理

### Numeric側通信テスト

- **同期プロトコル**: Plant側との時刻同期確立
- **RTT測定**: 往復時間の正確な計測
- **コマンド送信**: 制御コマンドの非同期送信
- **状態データ受信**: Plant状態データの受信・解析
- **通信統計**: 送受信カウント、エラー統計

### 統合通信テスト

- **プロセス管理**: Plant・Numeric両プロセスの起動・監視
- **同期確立**: 両側での時刻同期プロトコル実行
- **データフロー**: 完全な制御ループでのデータ交換
- **エラーハンドリング**: 通信障害時の処理確認

## テスト結果の見方

### 成功例
```
=== Test Results ===
Steps executed: 3000
Commands sent: 3000
States received: 2998
Final altitude: 9.95m
Average RTT: 2.3ms
RTT measurements: 2998
Communication stats: {'sent_count': 3000, 'received_count': 2998, 'timeout_count': 2}

=== Integration Test Results ===
Plant: SUCCESS
Numeric: SUCCESS
Overall: SUCCESS
```

### 確認ポイント

1. **Steps executed**: 実行ステップ数（期待値と一致するか）
2. **Commands sent/received**: 送受信数（概ね一致するか）
3. **RTT measurements**: RTT測定回数（通信成功率）
4. **Average RTT**: 平均往復時間（通常1-10ms程度）
5. **Overall Result**: 全体的な成功/失敗

## トラブルシューティング

### よくあるエラー

#### 1. 同期タイムアウト
```
ERROR: Plant did not respond to READY signal within 10 seconds
```
**解決策**:
- Plant側プロセスが正しく起動しているか確認
- ファイアウォール設定でポート5555, 5556が開いているか確認

#### 2. ソケット接続エラー
```
zmq.error.ZMQError: Address already in use
```
**解決策**:
- 既存のテストプロセスを終了: `pkill -f test_.*_communication.py`
- ポートが解放されるまで数秒待機

#### 3. RTT測定異常
```
WARNING: RTT seems unreasonable: 1523.4ms
```
**解決策**:
- システム負荷を確認（CPU、メモリ使用率）
- 同期プロトコルが正しく実行されているか確認

### デバッグオプション

```bash
# 詳細ログ出力
python test_communication_integration.py --verbose

# 長時間テスト（安定性確認）
python test_communication_integration.py --duration 300

# Plant側詳細ログ
cd plant/app
python test_plant_communication.py --duration 60 --delay --verbose
```

## 通信設定の変更

通信パラメータを変更して異なる条件でテストする方法：

### 遅延シミュレーション設定

`plant_communication.py` の `configure_delay_simulation()` で設定：

```python
communicator.configure_delay_simulation(
    enable=True,
    processing_delay_ms=10.0,  # 処理遅延
    response_delay_ms=5.0,     # 応答遅延
    delay_variation_ms=3.0     # 遅延変動
)
```

### タイムアウト設定

`numeric_communication.py` でタイムアウト時間を調整：

```python
self.state_subscriber.setsockopt(zmq.RCVTIMEO, 20)  # 20ms timeout
```

## パフォーマンス基準

### 正常範囲の目安

- **RTT**: 1-10ms（ローカル環境）
- **通信成功率**: >95%
- **同期確立時間**: <5秒
- **CPU使用率**: <10%（テスト中）

### 問題の兆候

- RTT > 50ms（ネットワーク問題または高負荷）
- 通信成功率 < 90%（通信障害または設定問題）
- 頻繁な同期失敗（プロセス起動順序問題）

これらのテストにより、通信モジュールの動作を独立して検証し、問題の切り分けが容易になります。