#!/usr/bin/env python3
"""
RTT不一致の原因調査
通信テストとHILSシステムでのRTT測定の違いを特定
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import yaml

def debug_rtt_mismatch():
    """RTT不一致の原因を詳細調査"""

    print("="*80)
    print("🔍 RTT MISMATCH INVESTIGATION")
    print("="*80)

    # 1. 設定ファイルの確認
    print("\n📋 Configuration Analysis:")

    # Plant設定の確認
    try:
        with open('plant/app/config.yaml', 'r') as f:
            plant_config = yaml.safe_load(f)

        print("Plant config:")
        comm_config = plant_config.get('communication', {})
        print(f"  enable_delay: {comm_config.get('enable_delay', 'not found')}")
        print(f"  processing_delay: {comm_config.get('processing_delay', 'not found')}ms")
        print(f"  response_delay: {comm_config.get('response_delay', 'not found')}ms")
        print(f"  delay_variation: {comm_config.get('delay_variation', 'not found')}ms")

    except Exception as e:
        print(f"Error reading plant config: {e}")

    # Numeric設定の確認
    try:
        with open('numeric/app/config.yaml', 'r') as f:
            numeric_config = yaml.safe_load(f)

        print("\\nNumeric config:")
        print(f"  dt: {numeric_config.get('numeric', {}).get('dt', 'not found')}s")
        print(f"  timeout_ms: {numeric_config.get('numeric', {}).get('timeout_ms', 'not found')}ms")

    except Exception as e:
        print(f"Error reading numeric config: {e}")

    # 2. 実際のログからRTT測定の詳細分析
    print(f"\\n📊 RTT Measurement Analysis:")

    test_cases = [
        ('no_delay_20250923_191436', 'No Delay', 0),
        ('light_delay_20250923_191646', 'Light Delay', 7),
        ('medium_delay_20250923_191914', 'Medium Delay', 28),
        ('heavy_delay_20250923_192151', 'Heavy Delay', 65),
        ('jitter_delay_20250923_192425', 'High Jitter', 40)
    ]

    for run_id, name, expected_rtt in test_cases:
        print(f"\\n--- {name} (Expected: {expected_rtt}ms) ---")

        try:
            # データ読み込み
            numeric_data = pd.read_csv(f'logs/{run_id}/realtime_numeric_log.csv')

            # RTT分析
            rtt_data = numeric_data[numeric_data['rtt_ms'] > 0]['rtt_ms']

            # 基本統計
            if len(rtt_data) > 0:
                print(f"Valid RTT measurements: {len(rtt_data)}/{len(numeric_data)} ({len(rtt_data)/len(numeric_data)*100:.1f}%)")
                print(f"RTT stats: Mean={rtt_data.mean():.1f}ms, Std={rtt_data.std():.1f}ms")
                print(f"RTT range: {rtt_data.min():.1f} - {rtt_data.max():.1f}ms")

                # 時系列での変化
                early_rtt = rtt_data[numeric_data[numeric_data['rtt_ms'] > 0]['sim_time'] <= 10]
                late_rtt = rtt_data[numeric_data[numeric_data['rtt_ms'] > 0]['sim_time'] >= 70]

                if len(early_rtt) > 0 and len(late_rtt) > 0:
                    print(f"Early RTT (0-10s): {early_rtt.mean():.1f}ms")
                    print(f"Late RTT (70-80s): {late_rtt.mean():.1f}ms")

                # 異常値の特定
                q75, q25 = np.percentile(rtt_data, [75, 25])
                iqr = q75 - q25
                outliers = rtt_data[(rtt_data < (q25 - 1.5 * iqr)) | (rtt_data > (q75 + 1.5 * iqr))]
                print(f"Outliers: {len(outliers)} ({len(outliers)/len(rtt_data)*100:.1f}%)")

            else:
                print("No valid RTT measurements")

            # 通信失敗の詳細
            timeouts = len(numeric_data[numeric_data['communication_status'] == 'TIMEOUT'])
            print(f"Communication timeouts: {timeouts}/{len(numeric_data)} ({timeouts/len(numeric_data)*100:.1f}%)")

            # 制御周期の影響
            control_dt = numeric_data['control_dt'] * 1000  # ms
            long_periods = len(control_dt[control_dt > 25])  # 25ms超
            print(f"Long control periods (>25ms): {long_periods}/{len(control_dt)} ({long_periods/len(control_dt)*100:.1f}%)")

        except Exception as e:
            print(f"Error analyzing {run_id}: {e}")

    # 3. RTT計算メカニズムの分析
    print(f"\\n🔧 RTT Calculation Mechanism Analysis:")

    print("RTT is calculated as:")
    print("  1. Numeric sends command with sync_timestamp")
    print("  2. Plant receives command, stores latest_cmd_seq and latest_cmd_timestamp")
    print("  3. Plant sends state data including latest_cmd_seq")
    print("  4. Numeric receives state, calculates RTT = current_sync_timestamp - stored_sync_timestamp")

    # 実際のデータでRTT計算の妥当性確認
    try:
        # No delayケースでサンプル分析
        numeric_data = pd.read_csv('logs/no_delay_20250923_191436/realtime_numeric_log.csv')

        print(f"\\n🔍 Sample RTT Calculation Verification (No Delay case):")

        # 最初の有効なRTT測定をチェック
        valid_rtt_rows = numeric_data[numeric_data['rtt_ms'] > 0]
        if len(valid_rtt_rows) > 0:
            sample_row = valid_rtt_rows.iloc[0]
            print(f"First valid RTT measurement:")
            print(f"  Step: {sample_row['seq']}")
            print(f"  Sim time: {sample_row['sim_time']:.3f}s")
            print(f"  RTT: {sample_row['rtt_ms']:.1f}ms")
            print(f"  Communication status: {sample_row['communication_status']}")

            # タイミングデータ
            print(f"  Step start sync: {sample_row['step_start_sync']:.6f}")
            print(f"  Cmd send sync: {sample_row['cmd_send_sync']:.6f}")
            print(f"  Response recv sync: {sample_row['response_recv_sync']:.6f}")

            # 手動RTT計算
            manual_rtt = (sample_row['response_recv_sync'] - sample_row['cmd_send_sync']) * 1000
            print(f"  Manual RTT calculation: {manual_rtt:.1f}ms")
            print(f"  Difference from logged RTT: {abs(manual_rtt - sample_row['rtt_ms']):.1f}ms")

    except Exception as e:
        print(f"Error in RTT verification: {e}")

    # 4. 可能な原因の分析
    print(f"\\n💡 Possible Causes Analysis:")

    causes = [
        "1. Clock synchronization issues between containers",
        "2. ZMQ message queuing and buffering delays",
        "3. Docker network overhead (bridge vs host networking)",
        "4. Python GIL and threading delays",
        "5. System load and resource contention",
        "6. Incorrect RTT calculation implementation",
        "7. Config not being applied properly",
        "8. Delay simulation not working as expected"
    ]

    for cause in causes:
        print(f"  {cause}")

    print(f"\\n🎯 Next Steps:")
    print("  1. Run HILS with one delay config and inspect real-time logs")
    print("  2. Compare config loading between test and HILS")
    print("  3. Add debug prints to RTT calculation")
    print("  4. Check if delay simulation is actually applied")

    # 5. 簡単なデバッグテスト提案
    print(f"\\n🧪 Debug Test Proposal:")
    print("Run a short test with medium delay and check:")
    print("  - Is delay actually applied in Plant communication?")
    print("  - Are sync timestamps consistent?")
    print("  - What does raw communication timing show?")

if __name__ == "__main__":
    debug_rtt_mismatch()