# HILS 二系統シミュレーション Docker システム

HILSシミュレーションシステムのDocker実装です。Plant/HILS側とNumeric/Simulator側をZeroMQ TCPベースの同期通信で結合し、タイムスタンプ付きログ管理と統合分析システムを提供します。

## システム構成

```
Plant Container (A)     <--ZeroMQ TCP-->     Numeric Container (B)
- REP Server (port:5555)                     - REQ Client  
- 3DOF物理シミュレーション                       - PID制御 / シナリオ実行
- IMUセンサ模擬                              - ログ記録 (RTT測定)
- Euler積分                                 - タイムアウト制御
```

## クイックスタート

```bash
# 1. Python依存関係のインストール
make setup

# 2. システムの構築と起動
make build
make up

# 3. 統合分析・可視化実行
make analyze

# 4. ログ状況確認
make logs-status

# 停止
make down
```

## 主な機能

### ✨ タイムスタンプ付きログ管理
- 各シミュレーション実行で独立したディレクトリ生成: `logs/YYYYMMDD_HHMMSS/`
- Plant/Numericの完全なログ保存
- 可視化ファイルも同一ディレクトリに保存

### 🎯 制御システム
- **PIDモード**: 目標位置制御 (デフォルト)
- **シナリオモード**: 事前定義コマンド実行
- リアルタイムRTT測定 (~0.5ms平均)

### 📊 統合分析・可視化
- 統合ダッシュボード (軌道、制御性能、通信性能)
- 3D軌道可視化
- 性能レポート (RTT、制御誤差、システム状態)
- 特定実行結果の分析可能

## ディレクトリ構成

```
.
├── docker/
│   ├── compose.yaml      # Docker Compose設定
│   └── .env             # 環境変数
├── plant/               # Plant側（A系統）
│   ├── Dockerfile
│   └── app/
│       ├── main.py      # Plantメインアプリ
│       ├── config.yaml  # 設定ファイル
│       └── requirements.txt
├── numeric/             # Numeric側（B系統）
│   ├── Dockerfile
│   └── app/
│       ├── main.py      # Numericメインアプリ
│       ├── config.yaml  # 設定ファイル
│       └── requirements.txt
├── scripts/             # 分析・管理スクリプト
│   ├── hils_analyzer.py # 統合ログ管理・可視化ツール
│   └── README_ANALYZER.md
├── shared/              # 共有リソース
│   ├── scenarios/       # シナリオファイル
│   └── schemas/         # メッセージスキーマ
├── logs/               # タイムスタンプ付きログディレクトリ
│   ├── 20250903_143025/  # 実行ごとの独立ログ
│   │   ├── plant_log.csv
│   │   ├── numeric_log.csv
│   │   ├── hils_analysis_dashboard.png
│   │   ├── hils_flight_trajectory.png
│   │   └── hils_performance_report.png
│   └── .gitkeep
└── Makefile           # ビルド・実行自動化
```

## 設定

### 環境変数 (docker/.env)
- `STEP_DT=0.002` - シミュレーションステップ間隔 (s)
- `MAX_STEPS=1000` - 最大ステップ数
- `PLANT_ENDPOINT=tcp://plant:5555` - Plant接続エンドポイント

### 制御モード切り替え
**PIDモード (デフォルト):**
```yaml
# numeric/app/config.yaml
scenario:
  enabled: false
```

**シナリオモード:**
```yaml
# numeric/app/config.yaml
scenario:
  enabled: true
  file: "/app/shared/scenarios/default.csv"
```

### 通信プロトコル
- **ZeroMQ REQ/REP** パターンでロックステップ同期
- **JSON形式** でメッセージ交換
- **TCP/IP** による通信 (デフォルト: `tcp://plant:5555`)

### メッセージ形式

**Request (Numeric → Plant):**
```json
{
  "seq": 1234,
  "t": 1.234,
  "u": [1.0, 0.0, 0.0]
}
```

**Response (Plant → Numeric):**
```json
{
  "seq": 1234,
  "t": 1.234,
  "y": {
    "acc": [0.1, 0.0, 9.8],
    "gyro": [0.0, 0.0, 0.0],
    "position": [1.0, 0.0, 10.0],
    "velocity": [1.0, 0.0, 0.0]
  },
  "valid": true
}
```

## 利用可能なコマンド

```bash
# セットアップと基本操作
make setup      # Python依存関係インストール
make build      # コンテナビルド
make up         # システム起動
make down       # システム停止
make restart    # 再起動
make rebuild    # 完全再構築

# 統合分析・ログ管理
make analyze    # 最新ログの統合分析と可視化
make logs-status # ログファイル状態確認

# ログとモニタリング
make logs       # 全ログ表示
make logs-plant # Plant側ログ
make logs-numeric # Numeric側ログ
make monitor    # リアルタイム監視
make status     # ステータス確認

# テストとメンテナンス
make test       # テスト実行
make clean      # リソース削除
make help       # ヘルプ表示
```

## 詳細分析機能

### 特定実行結果の分析
```bash
# 利用可能なRUN_ID確認
make logs-status

# 特定の実行結果を分析
python3 scripts/hils_analyzer.py visualize --run-id 20250903_211154

# 特定のプロットのみ生成
python3 scripts/hils_analyzer.py visualize --run-id 20250903_211154 --plots dashboard trajectory

# 最新結果の分析（デフォルト）
python3 scripts/hils_analyzer.py visualize
```

### 生成されるファイル
各分析で以下のファイルが生成されます：
- `hils_analysis_dashboard.png` - 統合ダッシュボード
- `hils_flight_trajectory.png` - 3D軌道可視化  
- `hils_performance_report.png` - 性能レポート

## ワークフロー例

### 標準的な使用手順
```bash
# 1. 初回セットアップ
git clone https://github.com/Akira-11-20/hilsim.git
cd hilsim
make setup

# 2. PIDモードでの実行
make build
make up       # 自動で RUN_ID: 20250903_143025 生成
make analyze  # 結果分析

# 3. シナリオモードに切り替え
# numeric/app/config.yaml で scenario.enabled = true に変更
make restart  # 新しい RUN_ID: 20250903_144512 生成
make analyze  # シナリオ実行結果を分析

# 4. 過去結果との比較
python3 scripts/hils_analyzer.py visualize --run-id 20250903_143025  # PID結果
python3 scripts/hils_analyzer.py visualize --run-id 20250903_144512  # シナリオ結果
```

### PIDパラメータ調整ワークフロー
```bash
# 1. 初期パラメータでテスト実行
make up && make down && make analyze

# 2. numeric/app/config.yaml でPIDゲイン調整
# controller:
#   kp: 1.0 → 2.0
#   ki: 0.1 → 0.2  
#   kd: 0.01 → 0.05

# 3. 再実行・比較
make restart && make analyze

# 4. 複数バージョンの性能比較
make logs-status  # 利用可能なRUN_IDを確認
```

## システム性能

### 実測値
- **RTT**: 平均 0.5ms, 最大 1.0ms
- **ステップレート**: 500Hz (STEP_DT=0.002s)
- **CPU使用率**: ~5-10% (通常時)
- **メモリ使用量**: ~50MB/コンテナ

## トラブルシューティング

### よくある問題

1. **Python依存関係エラー**: 
```bash
make setup  # 依存関係を再インストール
```

2. **接続エラー**: Plant側の起動を確認
```bash
make logs-plant
make status
```

3. **分析エラー**: ログファイルの存在確認
```bash
make logs-status
ls -la logs/
```

4. **権限エラー**: Docker実行時の権限問題
```bash
# logs/ ディレクトリが作成されているか確認
ls -la logs/
```

### デバッグ方法

```bash
# コンテナ内での実行
docker exec -it hils-plant /bin/bash
docker exec -it hils-numeric /bin/bash

# 特定RUN_IDの詳細確認
python3 scripts/hils_analyzer.py status
python3 scripts/hils_analyzer.py visualize --run-id <RUN_ID>
```

## 技術詳細

### 物理シミュレーション
- **3DOF point mass dynamics**: 質量1.0kg
- **Euler積分**: dt=0.002s
- **IMUセンサ**: 加速度・角速度にガウシアンノイズ
- **重力**: -9.81 m/s² (Z軸)

### 制御システム  
- **PID制御**: 位置制御ループ
- **目標値**: [0, 0, 10] (10m高度ホバリング)
- **制御周期**: 500Hz

### 通信システム
- **ZeroMQ**: REQ/REP pattern
- **メッセージ**: JSON format
- **RTT測定**: マイクロ秒精度
- **タイムアウト**: 5000ms

## ライセンス

MIT License

## 更新履歴

- 2025-09-03: タイムスタンプ付きログ管理、統合分析機能追加
- 2025-09-03: 特定RUN_ID分析機能、シナリオモード対応
- 2025-09-03: 初版作成