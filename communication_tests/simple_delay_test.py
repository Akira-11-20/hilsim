#!/usr/bin/env python3
"""
シンプル遅延テスト

異なる遅延設定でのRTT変化を短時間で確認
"""

import subprocess
import re
import time

def test_delay_impact():
    """遅延設定の影響を短時間テスト"""

    print("=== 遅延設定のRTTへの影響テスト ===\n")

    # テスト設定
    test_configs = [
        (0, 0, 0, "遅延なし"),
        (10, 5, 2, "軽微遅延"),
        (30, 15, 5, "高遅延"),
    ]

    results = []

    for proc, resp, var, name in test_configs:
        print(f"テスト: {name} (processing={proc}ms, response={resp}ms, variation=±{var}ms)")

        # 設定ファイル更新
        update_delay_config(proc, resp, var)

        # 短時間テスト実行
        try:
            result = run_short_test()
            if result:
                expected_min = 10 + proc + resp - var  # ベース + 設定 - 変動
                expected_max = 10 + proc + resp + var  # ベース + 設定 + 変動

                print(f"  期待RTT: {expected_min:.1f}-{expected_max:.1f}ms")
                print(f"  実測RTT: {result:.1f}ms")
                print(f"  {'✅ 期待範囲内' if expected_min <= result <= expected_max + 10 else '❌ 期待範囲外'}")
                results.append((name, proc + resp, result))
            else:
                print("  ❌ テスト失敗")
                results.append((name, proc + resp, None))
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            results.append((name, proc + resp, None))

        print()
        time.sleep(1)  # テスト間の待機

    # 結果まとめ
    print("=== 結果まとめ ===")
    valid_results = [(name, expected, actual) for name, expected, actual in results if actual is not None]

    if len(valid_results) >= 2:
        print("遅延設定と実測RTTの関係:")
        for name, expected, actual in valid_results:
            overhead = actual - expected - 10  # 基本オーバーヘッド10msを除く
            print(f"  {name}: 設定{expected}ms → 実測{actual:.1f}ms (オーバーヘッド: {overhead:.1f}ms)")

        # 線形性チェック
        if len(valid_results) == 3:
            expected_vals = [r[1] for r in valid_results]
            actual_vals = [r[2] for r in valid_results]

            rtt_increase_12 = actual_vals[1] - actual_vals[0]
            rtt_increase_23 = actual_vals[2] - actual_vals[1]
            setting_increase_12 = expected_vals[1] - expected_vals[0]
            setting_increase_23 = expected_vals[2] - expected_vals[1]

            print(f"\n線形性チェック:")
            print(f"  設定変化1→2: {setting_increase_12}ms, RTT変化: {rtt_increase_12:.1f}ms")
            print(f"  設定変化2→3: {setting_increase_23}ms, RTT変化: {rtt_increase_23:.1f}ms")

            if abs(rtt_increase_12 - setting_increase_12) < 5 and abs(rtt_increase_23 - setting_increase_23) < 5:
                print("  ✅ 遅延設定は線形的にRTTに反映されています")
            else:
                print("  ⚠️ 非線形性またはノイズが存在します")

def update_delay_config(proc_delay, resp_delay, var_delay):
    """Plant通信テストファイルの遅延設定を更新"""

    file_path = "plant/app/test_plant_communication.py"

    with open(file_path, 'r') as f:
        content = f.read()

    # 遅延設定部分を置換
    new_settings = f"""            communicator.configure_delay_simulation(
                enable=True,
                processing_delay_ms={proc_delay},   # {proc_delay}ms処理遅延
                response_delay_ms={resp_delay},     # {resp_delay}ms応答遅延
                delay_variation_ms={var_delay}     # ±{var_delay}ms変動
            )"""

    pattern = r'communicator\.configure_delay_simulation\(\s*enable=True,\s*processing_delay_ms=[\d.]+,.*?delay_variation_ms=[\d.]+\s*\)'
    content = re.sub(pattern, new_settings.strip(), content, flags=re.DOTALL)

    with open(file_path, 'w') as f:
        f.write(content)

def run_short_test():
    """短時間統合テストを実行してRTTを取得"""

    try:
        process = subprocess.Popen(
            ["uv", "run", "python", "test_communication_integration.py", "--duration", "8", "--delay"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = process.communicate(timeout=20)

        # RTT値を抽出
        for line in stderr.split('\n'):
            if "Average RTT:" in line:
                match = re.search(r'Average RTT: ([\d.]+)ms', line)
                if match:
                    return float(match.group(1))

        return None

    except Exception:
        return None

if __name__ == "__main__":
    test_delay_impact()