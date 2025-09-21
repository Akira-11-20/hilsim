# Claude Code設定

このファイルには、Claude Code用のプロジェクト固有の設定とメモが含まれています。

## プロジェクト概要

HILS（Hardware-in-the-Loop Simulation）二システムシミュレーションのDocker実装。

## コマンド

### 基本操作
- セットアップ: `make setup` - Python依存関係のuvでのインストール
- 開発環境: `make setup-dev` - 開発用依存関係も含めてインストール
- ビルド: `make build` - Dockerコンテナのビルド
- 実行開始: `make up` - HILSシミュレーションの開始
- 実行停止: `make down` - HILSシミュレーションの停止
- 再起動: `make restart` - シミュレーションの再起動
- 完全再構築: `make rebuild` - クリーンして再ビルド・実行

### ログ・監視
- 全ログ表示: `make logs` - 全サービスのログを表示
- Plant ログ: `make logs-plant` - Plantのみのログ表示
- Numeric ログ: `make logs-numeric` - Numericのみのログ表示
- リアルタイム監視: `make monitor` - パフォーマンス監視ダッシュボード

### 分析・テスト
- ログ分析: `make analyze` - ログの解析と可視化
- ログ状態確認: `make logs-status` - ログファイルの状態表示
- ステータス確認: `make status` - コンテナとサービスの状態確認
- テスト実行: `make test` - 30秒間のテストシミュレーション

### メンテナンス
- クリーンアップ: `make clean` - Docker リソースの削除
- ヘルプ: `make help` - 利用可能コマンドの一覧表示

## プロジェクト構造

### メインHILSシステム (Docker)
- `docker/` - Docker設定ファイル
- `plant/` - Plant（物理シミュレーション）コンテナ
- `numeric/` - Numeric（制御システム）コンテナ
- `logs/` - ログファイル保存ディレクトリ

### 独立PID制御シミュレーション
- `simple_pid_control/` - 改善されたPID制御の検証用
  - `simple_pid_sim.py` - 基本PID制御シミュレーション
  - `optimized_pid_sim.py` - パラメータ比較テスト
  - `README.md` - シミュレーション詳細

## メモ

- メインシステムはDockerコンテナでZMQ通信使用
- simple_pid_control/ は独立した検証用（通信遅延なし）
- PID制御の問題: 現在のゲインが低すぎる（Kp=0.8 → 18.0推奨）