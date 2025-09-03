# HILS Integrated Log Management & Visualization System

統合されたログ管理と視覚化システムの使用ガイド

## 概要

`hils_analyzer.py`は、HILSシミュレーションのログ管理と視覚化を統合したツールです。ログの状態確認、自動アーカイブ、高度な可視化機能を提供します。

## 主な機能

### 📊 **統合分析・可視化**
- 包括的なダッシュボード生成
- 3D飛行軌道の可視化
- 詳細な性能レポート
- カスタマイズ可能な設定

### 📁 **ログ管理**
- ログファイルの状態監視
- 自動アーカイブ機能
- 古いアーカイブの自動削除
- タイムスタンプベースの整理

### ⚙️ **設定管理**
- JSON設定ファイル
- DPI、保持期間などのカスタマイズ
- デフォルトプロット選択

## コマンドリファレンス

### 基本コマンド（Makefile経由）

```bash
# 統合分析実行（推奨）
make analyze

# ログ状態確認
make logs-status

# ログアーカイブ
make archive

# 古いアーカイブ削除
make clean-archives
```

### 直接コマンド実行

```bash
# 全体的な状態確認
python3 hils_analyzer.py status

# すべての可視化を生成
python3 hils_analyzer.py visualize

# 特定のプロットのみ生成
python3 hils_analyzer.py visualize --plots dashboard trajectory

# タグ付きアーカイブ
python3 hils_analyzer.py archive --tag experiment1

# 設定変更
python3 hils_analyzer.py config --retention 7 --dpi 300
```

## 生成される可視化

### 1. **Comprehensive Dashboard** (`hils_analysis_dashboard.png`)
- 高度制御性能
- 制御コマンド分析
- 垂直速度プロファイル
- 制御誤差の可視化
- 通信性能
- 位相図
- 制御努力
- 性能サマリー

### 2. **3D Flight Trajectory** (`hils_flight_trajectory.png`)
- 3次元飛行軌道
- 時間に基づく色分け
- 開始・終了・目標点の表示

### 3. **Performance Report** (`hils_performance_report.png`)
- 詳細な性能メトリクス
- 立上り時間、整定時間分析
- 通信遅延統計
- エラー分布分析

## 設定ファイル

`hils_analyzer_config.json`で動作をカスタマイズ：

```json
{
  "log_retention_days": 30,
  "auto_archive": true,
  "max_log_size_mb": 100,
  "visualization_dpi": 300,
  "default_plots": ["dashboard", "trajectory", "performance"],
  "colors": {
    "primary": "#1f77b4",
    "secondary": "#ff7f0e",
    "success": "#2ca02c",
    "danger": "#d62728"
  }
}
```

## ディレクトリ構造

```
hilsim/
├── hils_analyzer.py           # 統合分析ツール
├── hils_analyzer_config.json  # 設定ファイル
├── logs/                      # 現在のログ
│   ├── numeric_log.csv
│   └── plant_log.csv
├── logs_archive/              # アーカイブ
│   └── logs_YYYYMMDD_HHMMSS/
└── hils_*.png                 # 生成された可視化
```

## ワークフロー例

### 日常的な解析
```bash
# シミュレーション実行
make up

# 結果の分析
make analyze

# ログ状態確認
make logs-status
```

### 実験結果の保存
```bash
# タグ付きでアーカイブ
python3 hils_analyzer.py archive --tag pid_tuning_v2

# 特定の可視化のみ生成
python3 hils_analyzer.py visualize --plots performance

# 設定調整
python3 hils_analyzer.py config --dpi 600
```

### メンテナンス
```bash
# 古いアーカイブ削除
make clean-archives

# 設定確認
python3 hils_analyzer.py config --show
```

## 従来機能との互換性

従来の`visualize.py`、`visualize_simple.py`、`visualize_advanced.py`は引き続き利用可能：

```bash
make visualize          # シンプル版
make visualize-advanced # 高度版（旧）
```

## トラブルシューティング

### よくある問題

1. **ログファイルが見つからない**
   ```bash
   make logs-status  # 状態確認
   make up           # シミュレーション実行
   ```

2. **可視化エラー**
   ```bash
   pip install matplotlib pandas numpy seaborn
   ```

3. **設定の問題**
   ```bash
   python3 hils_analyzer.py config --show
   rm hils_analyzer_config.json  # 設定リセット
   ```

## パフォーマンス最適化

- 大きなログファイル（>100MB）は自動的に検出・警告
- DPI設定による画像品質とサイズの調整
- 選択的プロット生成による高速化

## 拡張性

新しい可視化やメトリクスの追加は`HILSAnalyzer`クラスを拡張：

```python
def create_custom_analysis(self):
    # カスタム分析の実装
    pass
```

---

**統合システムにより、HILSシミュレーションの分析とログ管理が一元化されました！**