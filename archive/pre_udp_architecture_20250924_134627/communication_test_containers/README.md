# Communication Test Containers

アプリケーションレベル遅延制御によるHILS通信検証システム

## 概要

このディレクトリには、HILSシステムの通信検証用テストコンテナが含まれています。
アプリケーションレベルでの遅延・ジッタ制御により、現実的なネットワーク条件をシミュレートできます。

## 検証済み機能

- ✅ 基本RTT測定（Docker bridge: 0.5ms平均）
- ✅ 固定遅延制御（設定30ms → 実測23ms）
- ✅ ジッタ制御（uniform/gaussian/exponential分布）
- ✅ 詳細統計データ取得（CSV/JSON出力）
- ✅ 包括的グラフ分析

## メインファイル

### 🚀 実用スクリプト
- `generate_csv_results.py` - 詳細RTT測定・CSV出力
- `create_graphs.py` - 包括的グラフ生成
- `server/delay_server.py` - 遅延制御サーバー
- `client/enhanced_client.py` - 高精度測定クライアント

### ⚙️ 設定ファイル
- `docker-compose.yml` - 基本テスト構成
- `docker-compose-delay.yml` - 遅延テスト構成

### 📊 検証結果
- `results/rtt_detailed_*.csv` - 詳細測定データ
- `results/rtt_analysis_*.png` - RTT分析グラフ
- `results/rtt_statistics_*.png` - 統計分析グラフ
- `results/performance_summary_*.csv` - パフォーマンスサマリー

## 使用方法

### 基本RTT測定
```bash
docker compose up --build
```

### 遅延・ジッタテスト
```bash
docker compose -f docker-compose-delay.yml --profile fixed up --build
```

### 詳細分析生成
```bash
python generate_csv_results.py
python create_graphs.py
```

## 測定結果サマリー

| 設定 | 平均RTT | 標準偏差 | P95 | P99 |
|------|---------|----------|-----|-----|
| ベースライン | 0.50ms | 0.09ms | 0.67ms | 0.75ms |
| 30ms遅延 | 23.0ms | 1.11ms | 24.9ms | 25.2ms |

## HILSシステムへの統合

この検証結果に基づき、HILSシステム本体の通信モジュールに以下を統合可能：

1. **遅延制御機能**: `delay_server.py`のロジック
2. **統計取得**: 詳細RTTログ機能
3. **リアルタイム監視**: グラフ生成機能

## 推奨事項

- **開発段階**: アプリケーションレベル遅延制御を使用
- **統合テスト**: 本テストフレームワークで事前検証
- **本格運用**: HILSシステム本体に統合して使用