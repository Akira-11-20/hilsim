# HILS通信分析レポート

このディレクトリには、HILSシステムの通信構造とRTT変動に関する分析結果が含まれています。

## 分析内容

### 1. 通信構造の理解
- ZeroMQ PUB/SUBパターンによるPlant-Numeric間通信
- 同期タイムスタンプを使用したRTT測定メカニズム
- 遅延シミュレーション機能の実装方式

### 2. RTT変動の原因特定
- **システム基本オーバーヘッド**: ~10ms（ネットワーク+処理）
- **設定遅延**: processing_delay + response_delay
- **意図的変動**: ±delay_variation
- **システム変動**: OS調度、GC、ZeroMQキューイング（5-20ms）

### 3. 遅延設定の効果検証
- 相関係数: 0.9999（設定値と実測値の完璧な線形関係）
- RTT計算式: `RTT = 基本オーバーヘッド + 設定遅延 ± 変動`
- 5つの遅延パターンでの詳細比較分析

## ファイル構成

### 分析結果ファイル
- `delay_pattern_comparison.png` - 遅延パターン別比較チャート（4種類）
- `delay_pattern_comparison.csv` - 数値データ詳細比較表
- `rtt_variation_analysis.png` - RTT変動原因の詳細分析
- `rtt_analysis.png` - 基本RTT分析
- `rtt_data.csv` - 実測データサンプル

### 分析スクリプト
- `communication_flow_analysis.py` - 通信構造とRTT変動原因の総合分析
- `create_delay_comparison.py` - 遅延パターン比較レポート生成
- `analyze_delay_impact.py` - 遅延設定影響の詳細分析

## 主要な結論

### ✅ 検証された事実
1. **遅延設定は確実にRTTに反映される**
2. **設定値と実測値に強い線形関係がある**
3. **RTT振れ幅の主要因が特定された**
4. **通信構造とタイミングメカニズムが理解された**

### 📊 遅延パターン比較結果

| パターン | 設定遅延 | 期待RTT | 実測RTT | システムオーバーヘッド |
|---------|----------|---------|---------|---------------------|
| 遅延なし | 0ms | 8-12ms | 9.8ms | 9.8ms |
| 軽微遅延 | 8ms | 16-20ms | 18.2ms | 10.2ms |
| 中程度遅延 | 15ms | 22-28ms | 24.7ms | 9.7ms |
| 高遅延 | 30ms | 35-45ms | 39.4ms | 9.4ms |
| 極高遅延 | 70ms | 60-90ms | 80.5ms | 10.5ms |

### 🔧 RTT変動の要因

1. **OS スケジューラ干渉**: 5-20ms（プロセス切り替え）
2. **ZeroMQ キューイング**: 1-10ms（非同期メッセージング）
3. **ガベージコレクション**: 10-100ms（Python GC）
4. **同期タイムスタンプずれ**: 0-5ms（time.time()精度）
5. **遅延シミュレーション変動**: 設定値±変動幅（意図的）

## 使用方法

### 分析の再実行
```bash
# 通信構造分析
uv run python communication_flow_analysis.py

# 遅延パターン比較
uv run python create_delay_comparison.py

# 詳細遅延分析
uv run python analyze_delay_impact.py
```

### 結果の確認
- PNGファイル: 各種チャートとグラフ
- CSVファイル: 数値データと統計

## 関連ファイル
- `../communication_tests/` - 通信機能テストスクリプト
- `../plant/app/plant_communication.py` - Plant側通信モジュール
- `../numeric/app/numeric_communication.py` - Numeric側通信モジュール