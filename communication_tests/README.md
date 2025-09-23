# HILS通信テストスイート

このディレクトリには、HILSシステムの通信機能をテストするためのスクリプトが含まれています。

## テストの目的

### 1. 通信機能の単体テスト
- Plant側通信モジュールの機能検証
- Numeric側通信モジュールの機能検証
- ZeroMQ PUB/SUB通信の動作確認

### 2. 遅延シミュレーション検証
- 遅延設定がRTTに与える影響の確認
- 遅延ロジックの正確性検証
- 設定値と実測値の相関確認

### 3. 統合通信テスト
- Plant-Numeric間の完全な通信フロー
- RTT測定機能の動作確認
- 同期プロトコルの検証

## テストファイル構成

### 基本通信テスト
- `test_plant_communication.py` - Plant側通信テスト
- `test_numeric_communication.py` - Numeric側通信テスト
- `test_communication_integration.py` - 統合通信テスト

### 遅延検証テスト
- `delay_logic_test.py` - 遅延ロジック単体テスト（推奨）
- `delay_verification_test.py` - 遅延機能検証テスト
- `simple_delay_test.py` - シンプル遅延テスト
- `quick_delay_test.py` - 高速遅延テスト

### RTT監視・分析
- `rtt_monitor.py` - リアルタイムRTT監視
- `final_rtt_demo.py` - RTT実測デモンストレーション

## 使用方法

### 推奨テスト順序

#### 1. 遅延ロジック検証（最も確実）
```bash
uv run python delay_logic_test.py
```
- ✅ ネットワークソケット不要
- ✅ 高速実行（数秒）
- ✅ 確実な結果

#### 2. 統合通信テスト（完全テスト）
```bash
uv run python test_communication_integration.py --duration 10 --delay
```
- Plant/Numericプロセス両方起動
- 実際のZeroMQ通信使用
- RTT測定機能確認

#### 3. RTTリアルタイム監視
```bash
uv run python rtt_monitor.py
```
- 30秒間のRTT変動を可視化
- CSV形式でデータ出力

### Makefileコマンド

便利なMakefileターゲット：
```bash
# 通信テスト実行
make test-communication

# Plant側テスト
make test-plant

# Numeric側テスト
make test-numeric

# 統合テスト
make test-integration
```

## テスト結果の解釈

### 正常な結果の例

#### 遅延ロジックテスト
```
遅延なし: 0ms → 0.0ms ✅
固定15ms遅延: 15ms → 15.0ms ✅
相関係数: 0.9999 ✅
```

#### 統合通信テスト
```
RTT Statistics:
- Min: 12.5ms
- Max: 28.7ms
- Avg: 18.3ms
- Count: 800
RTT Measurement: PASSED ✅
```

### 異常な結果の対処

#### テスト失敗の主な原因
1. **ポート競合**: 他のプロセスが5555/5556ポート使用中
2. **プロセス起動失敗**: Plant/Numericプロセスが正常起動しない
3. **タイムアウト**: ネットワーク遅延やシステム負荷

#### 対処方法
```bash
# ポート使用状況確認
netstat -an | grep 555

# プロセス確認
ps aux | grep python

# Docker環境使用
make up  # 安定した環境でテスト
```

## 各テストファイルの詳細

### delay_logic_test.py（推奨）
- **目的**: 遅延計算ロジックの単体テスト
- **利点**: ネットワーク不要、高速、確実
- **確認内容**: 遅延設定と実際の遅延時間の相関

### test_communication_integration.py
- **目的**: 完全な通信フロー検証
- **利点**: 実環境に近いテスト
- **確認内容**: RTT測定、同期プロトコル、データ送受信

### rtt_monitor.py
- **目的**: RTT変動のリアルタイム監視
- **利点**: 可視化、データ保存
- **確認内容**: RTT時系列変化、統計情報

## トラブルシューティング

### よくある問題

#### 1. ZMQエラー: Address already in use
```bash
# 解決策: 既存プロセス終了
pkill -f python.*test
sleep 2
# テスト再実行
```

#### 2. テストタイムアウト
```bash
# 解決策: テスト時間短縮
uv run python test_communication_integration.py --duration 5
```

#### 3. 依存関係エラー
```bash
# 解決策: 依存関係再インストール
uv add pyzmq numpy matplotlib pandas
```

## 関連ファイル
- `../analysis/` - 通信分析結果
- `../plant/app/plant_communication.py` - Plant通信モジュール
- `../numeric/app/numeric_communication.py` - Numeric通信モジュール
- `../Makefile` - テスト用ターゲット定義