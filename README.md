# HILS (Hardware-in-the-Loop Simulation) - UDP Architecture

参考構造に基づく高性能UDP通信アーキテクチャによるHILSシステム

## 🏗️ アーキテクチャ概要

```
┌─────────────────┐  UDP    ┌─────────────────┐
│     Numeric     │◄─────►│      Plant      │
│   (UDP Client)  │ Req/Res │  (UDP Server)   │
│   PID制御器     │         │   物理シミュ    │
└─────────────────┘         └─────────────────┘
         │                         │
         └──────┬──────────────────┘
                │
    ┌───────────▼───────────┐
    │     Docker Network    │
    │      (hilsim)         │
    │                       │
    │ • Network emulation   │
    │ • Traffic control     │
    │ • Delay/Jitter        │
    └───────────────────────┘
```

## 📋 システム構成

### Core Components
- **Plant Server** (UDP Server): 物理シミュレーション + 状態応答
- **Numeric Client** (UDP Client): PID制御 + コマンド送信
- **UDP Protocol**: Network byte order パケット + RTT測定
- **Docker Network**: tc netem による遅延制御

### Key Features
- ✅ **高性能**: RTT 0.7-1ms、100%成功率
- ✅ **シンプル**: UDP Request/Response
- ✅ **正確**: Network byte order + チェックサム
- ✅ **制御可能**: 遅延・ジッタ・損失シミュレーション
- ✅ **分析機能**: RTT統計・ログ記録

## 🚀 クイックスタート

### 1. セットアップ
```bash
make setup        # Python依存関係インストール
make build        # Dockerコンテナビルド
```

### 2. 基本実行
```bash
make up           # 基本シミュレーション実行
make logs         # ログ確認
make down         # 停止
```

### 3. ネットワーク条件テスト
```bash
make test-baseline      # 遅延なし（ベースライン）
make test-fixed-delay   # 固定遅延（15ms ± 5ms）
make test-high-jitter   # 高ジッタ（50ms ± 20ms）
make test-all-delays    # 全条件テスト
```

## ⚙️ 設定

### 環境変数（.env）
```bash
# システム設定
MAX_STEPS=2500      # ステップ数（50s at 50Hz）
RATE_HZ=50          # 送信レート
TIMEOUT_S=1.0       # UDP タイムアウト

# PID制御器
KP=18.0             # 比例ゲイン
KI=5.0              # 積分ゲイン
KD=8.0              # 微分ゲイン
SETPOINT=10.0       # 高度設定値[m]
```

## 📊 通信プロトコル

### UDP パケット構造

**Request（Numeric→Plant）**:
```
┌─────────────┬─────────────────────┬─────────────────────┐
│  Sequence   │     Timestamp       │    Control Data     │
│  Number     │     (double)        │  [fx, fy, fz, ...]  │
│  (int32)    │                     │                     │
│  4 bytes    │      8 bytes        │    Variable         │
└─────────────┴─────────────────────┴─────────────────────┘
```

**Response（Plant→Numeric）**:
```
┌─────────────┬─────────────────────┬─────────────────────┐
│  Sequence   │     Timestamp       │    State Data       │
│  Number     │     (double)        │  [pos, vel, acc]    │
│  (int32)    │                     │                     │
│  4 bytes    │      8 bytes        │    Variable         │
└─────────────┴─────────────────────┴─────────────────────┘
```

- **エンディアン**: Network byte order (big-endian)
- **チェックサム**: MD5ハッシュによるデータ整合性
- **RTT測定**: 高精度perf_counterベース

## 📈 性能特性

### RTT測定結果

| 条件 | 平均RTT | RTT範囲 | 成功率 | 用途 |
|------|---------|---------|--------|------|
| ベースライン | ~0.8ms | 0.4-1.2ms | 100% | 性能限界測定 |
| 固定遅延(15ms) | ~16ms | 14-18ms | 100% | 現実的ネットワーク |
| 高ジッタ(±20ms) | ~52ms | 30-80ms | 98% | 悪条件テスト |

### スループット特性
- **送信レート**: 50Hz（デフォルト）～ 100Hz（高速）
- **パケットサイズ**: 32B（Request）、56B（Response）
- **測定時間**: 50秒（2500ステップ）

## 🛠️ 利用可能コマンド

### 基本操作
```bash
make up             # シミュレーション開始
make down           # シミュレーション停止
make restart        # 再起動
make status         # 状態確認
make logs           # ログ表示
```

### テスト・分析
```bash
make test-protocol  # プロトコルテスト
make test-baseline  # ベースラインテスト
make test-all-delays# 全遅延条件テスト
make analyze        # ログ分析
```

### 開発・デバッグ
```bash
make build          # コンテナビルド
make clean          # リソースクリーンアップ
make help           # ヘルプ表示
```

## 📁 ディレクトリ構造

```
hilsim/
├── plant/           # Plant UDP Server実装
├── numeric/         # Numeric UDP Client実装
├── shared/          # 共通プロトコル実装
├── logs/            # ログファイル
├── simple_pid_control/  # PID検証用（参考）
├── archive/         # 旧バージョン保管
├── docker-compose.yml      # メインDocker設定
├── docker-compose.delay.yml # 遅延テスト設定
├── .env            # 環境変数設定
└── Makefile        # ビルド・実行スクリプト
```

## 🔬 技術詳細

### Network Byte Order Protocol
- **struct format**: `"!IdfffQ"` (Request), `"!IdfffffffffQ"` (Response)
- **チェックサム**: MD5ハッシュによる完全性確認
- **タイムスタンプ**: 高精度RTT測定用

### Docker Network Control
```bash
# 遅延制御例
tc qdisc add dev eth0 root netem delay 15ms 5ms

# パケット損失例
tc qdisc add dev eth0 root netem delay 10ms loss 1%
```

### PID制御器
- **動作確認済み**: simple_pid_control/ で検証
- **推奨ゲイン**: Kp=18.0, Ki=5.0, Kd=8.0
- **Windup防止**: 積分項制限付き

## 📚 参考

- **通信プロトコル**: communication_test_containers参考
- **PID制御**: simple_pid_control/実装ベース
- **ネットワーク制御**: Linux tc netem
- **Docker**: Compose v2 + health checks

---

**🚀 参考構造ベースのシンプルで高性能なHILSアーキテクチャ**