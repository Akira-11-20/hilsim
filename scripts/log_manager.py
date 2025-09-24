#!/usr/bin/env python3
"""
HILS ログ管理システム

日付ベースのログディレクトリ構造管理:
- logs/YYYY-MM-DD/HHMMSS_description/
- 古いログの自動アーカイブ
- ログサイズ監視・制限

Author: Claude Code
Date: 2024-09-24
"""

import os
import shutil
import time
import glob
from datetime import datetime, timedelta
from pathlib import Path
import argparse


class HILSLogManager:
    """HILS ログ管理クラス"""

    def __init__(self, base_log_dir: str = "logs"):
        self.base_log_dir = Path(base_log_dir)
        self.archive_dir = self.base_log_dir / "archive"

    def create_dated_log_dir(self, description: str = "", run_id: str = None) -> str:
        """
        日付ベースのログディレクトリ作成

        Args:
            description: ログの説明（例: "baseline_test", "delay_test"）
            run_id: カスタムRUN_ID（指定しない場合は自動生成）

        Returns:
            作成されたディレクトリパス
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M%S")

        if run_id:
            # カスタムRUN_IDが指定された場合
            if description:
                dir_name = f"{time_str}_{run_id}_{description}"
            else:
                dir_name = f"{time_str}_{run_id}"
        else:
            # デフォルト
            if description:
                dir_name = f"{time_str}_{description}"
            else:
                dir_name = time_str

        log_path = self.base_log_dir / date_str / dir_name
        log_path.mkdir(parents=True, exist_ok=True)

        print(f"Created log directory: {log_path}")
        return str(log_path)

    def organize_existing_logs(self):
        """
        既存のログを日付ベース構造に整理
        """
        print("Organizing existing logs by date...")

        # 既存のログディレクトリをスキャン
        existing_dirs = []
        for item in self.base_log_dir.iterdir():
            if item.is_dir() and item.name != "archive":
                # 日付形式ディレクトリ（YYYY-MM-DD）をスキップ
                if not self._is_date_directory(item.name):
                    existing_dirs.append(item)

        moved_count = 0
        for log_dir in existing_dirs:
            try:
                # ディレクトリの作成日時から日付を判定
                stat_info = log_dir.stat()
                creation_time = datetime.fromtimestamp(stat_info.st_mtime)
                date_str = creation_time.strftime("%Y-%m-%d")

                # 日付ディレクトリ作成
                target_date_dir = self.base_log_dir / date_str
                target_date_dir.mkdir(exist_ok=True)

                # ログディレクトリを移動
                target_path = target_date_dir / log_dir.name
                print(f"Moving {log_dir.name} -> {date_str}/{log_dir.name}")
                shutil.move(str(log_dir), str(target_path))
                moved_count += 1

            except Exception as e:
                print(f"Failed to move {log_dir.name}: {e}")

        print(f"Organized {moved_count} log directories")

    def _is_date_directory(self, dirname: str) -> bool:
        """ディレクトリ名が日付形式（YYYY-MM-DD）かチェック"""
        try:
            datetime.strptime(dirname, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def cleanup_old_logs(self, days_to_keep: int = 7):
        """
        古いログをアーカイブまたは削除

        Args:
            days_to_keep: 保持日数
        """
        print(f"Cleaning up logs older than {days_to_keep} days...")

        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")

        archived_count = 0
        for date_dir in self.base_log_dir.iterdir():
            if date_dir.is_dir() and self._is_date_directory(date_dir.name):
                if date_dir.name < cutoff_str:
                    # アーカイブディレクトリに移動
                    self.archive_dir.mkdir(exist_ok=True)
                    archive_path = self.archive_dir / f"logs_{date_dir.name}"

                    print(f"Archiving {date_dir.name} -> archive/logs_{date_dir.name}")
                    shutil.move(str(date_dir), str(archive_path))
                    archived_count += 1

        print(f"Archived {archived_count} old log directories")

    def get_log_stats(self):
        """ログ統計情報を取得"""
        print("=== HILS Log Statistics ===")

        if not self.base_log_dir.exists():
            print("No logs directory found")
            return

        # 総サイズ
        total_size = sum(f.stat().st_size for f in self.base_log_dir.rglob('*') if f.is_file())
        print(f"Total size: {total_size / (1024*1024):.1f} MB")

        # 日付別統計
        date_dirs = [d for d in self.base_log_dir.iterdir()
                    if d.is_dir() and self._is_date_directory(d.name)]
        date_dirs.sort()

        print(f"Date directories: {len(date_dirs)}")
        for date_dir in date_dirs[-10:]:  # 最新10日分
            log_count = len([d for d in date_dir.iterdir() if d.is_dir()])
            date_size = sum(f.stat().st_size for f in date_dir.rglob('*') if f.is_file())
            print(f"  {date_dir.name}: {log_count} logs, {date_size / (1024*1024):.1f} MB")

        # アーカイブ統計
        if self.archive_dir.exists():
            archive_count = len([d for d in self.archive_dir.iterdir() if d.is_dir()])
            archive_size = sum(f.stat().st_size for f in self.archive_dir.rglob('*') if f.is_file())
            print(f"Archive: {archive_count} directories, {archive_size / (1024*1024):.1f} MB")

    def get_today_log_dir(self, description: str = "") -> str:
        """今日の日付のログディレクトリパスを取得（作成はしない）"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%H%M%S")

        if description:
            dir_name = f"{time_str}_{description}"
        else:
            dir_name = time_str

        return str(self.base_log_dir / date_str / dir_name)


def main():
    parser = argparse.ArgumentParser(description="HILS Log Manager")
    parser.add_argument("action", choices=["organize", "cleanup", "stats", "create"],
                       help="Action to perform")
    parser.add_argument("--description", "-d", default="",
                       help="Log description for create action")
    parser.add_argument("--days", type=int, default=7,
                       help="Days to keep for cleanup action")
    parser.add_argument("--base-dir", default="logs",
                       help="Base log directory")

    args = parser.parse_args()

    manager = HILSLogManager(args.base_dir)

    if args.action == "organize":
        manager.organize_existing_logs()
    elif args.action == "cleanup":
        manager.cleanup_old_logs(args.days)
    elif args.action == "stats":
        manager.get_log_stats()
    elif args.action == "create":
        log_path = manager.create_dated_log_dir(args.description)
        print(f"Log directory: {log_path}")


if __name__ == "__main__":
    main()