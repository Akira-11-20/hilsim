# HILS 二系統シミュレーション Docker システム

HILSシミュレーションシステムのDocker実装です。同一モデルの2系統（Plant/HILS側とNumeric/Simulator側）をTCPベースの同期通信で結合し、統合された分析・ログ管理システムを提供します。

## システム構成

```
Plant Container (A)     <--TCP-->     Numeric Container (B)
- REP Server                          - REQ Client  
- 物理シミュレーション                      - 制御ロジック
- センサ模擬                            - シナリオ実行
```

## クイックスタート

```bash
# システムの構築と起動
make build
make up

# 統合分析実行（推奨）
make analyze

# ログの確認・管理
make logs-status
make archive

# 基本的な動作確認
make test

# 停止
make down
```

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
├── logs/               # 現在のログファイル
├── logs_archive/       # アーカイブされたログ
└── Makefile           # ビルド・実行自動化
```

## 設定

### 環境変数 (docker/.env)
- `STEP_DT=0.002` - シミュレーションステップ間隔 (s)
- `MAX_STEPS=1000` - 最大ステップ数
- `PLANT_ENDPOINT=tcp://plant:5555` - Plant接続エンドポイント

### 通信プロトコル
- **ZeroMQ REQ/REP** パターンでロックステップ同期
- **JSON形式** でメッセージ交換
- **TCP/IP** による通信 (将来はgRPCに移行予定)

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
# 基本操作
make build      # コンテナビルド
make up         # システム起動
make down       # システム停止
make restart    # 再起動
make rebuild    # 完全再構築

# 統合分析・ログ管理（新機能）
make analyze    # 統合分析と可視化
make logs-status # ログファイル状態確認
make archive    # ログのアーカイブ
make clean-archives # 古いアーカイブ削除

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

## パフォーマンスチューニング

### 低遅延モード
`docker/compose.yaml` で以下の設定に切り替え:
```yaml
network_mode: host  # bridge から host に変更
```

### CPUアフィニティ設定
```yaml
deploy:
  resources:
    reservations:
      cpus: "1.0"
cpuset: "2"  # 特定CPUコアに固定
```

## トラブルシューティング

### よくある問題

1. **接続エラー**: Plant側の起動を確認
```bash
make logs-plant
```

2. **タイムアウト**: `STEP_DT` を大きくするか、`timeout_ms` を調整

3. **ログが出力されない**: `logs/` ディレクトリの権限を確認

### デバッグ方法

```bash
# コンテナ内での実行
docker exec -it hils-plant /bin/bash
docker exec -it hils-numeric /bin/bash

# ネットワーク確認
docker network ls
docker network inspect hilsim_hilsnet
```

## 拡張計画

- [ ] gRPC対応 (`shared/schemas/messages.proto`)
- [ ] 可視化コンテナ (`hils-viz`)  
- [ ] ログ処理コンテナ (`hils-logger`)
- [ ] Protobuf/FlatBuffers対応
- [ ] ROS 2 DDS対応

## ライセンス

MIT License

## 更新履歴

- 2025-09-02: 初版作成