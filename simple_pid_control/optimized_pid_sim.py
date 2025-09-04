#!/usr/bin/env python3
"""
最適化されたPID制御シミュレーション - 複数のパラメータセットをテスト
"""

import numpy as np
import matplotlib.pyplot as plt
import time
from typing import List, Tuple, Dict

class SimplePIDController:
    """シンプルなPID制御器"""
    
    def __init__(self, kp: float, ki: float, kd: float, setpoint: float):
        self.kp = kp
        self.ki = ki  
        self.kd = kd
        self.setpoint = setpoint
        
        self.error_sum = 0.0
        self.prev_error = None
        self.prev_time = None
        
        # 積分項のwindup防止
        self.integral_limit = 30.0
        
    def reset(self):
        """制御器状態をリセット"""
        self.error_sum = 0.0
        self.prev_error = None
        self.prev_time = None
        
    def update(self, measurement: float, dt: float) -> float:
        """PID制御器の更新"""
        error = self.setpoint - measurement
        
        # 初回呼び出し時の初期化
        if self.prev_error is None:
            self.prev_error = error
            
        # 比例項
        p_term = self.kp * error
        
        # 積分項（windup防止付き）
        self.error_sum += error * dt
        self.error_sum = np.clip(self.error_sum, -self.integral_limit, self.integral_limit)
        i_term = self.ki * self.error_sum
        
        # 微分項
        if dt > 0:
            d_term = self.kd * (error - self.prev_error) / dt
        else:
            d_term = 0.0
            
        # PID出力
        output = p_term + i_term + d_term
        
        # 次回のために保存
        self.prev_error = error
        
        return output


class SimpleAltitudePlant:
    """シンプルな高度植物モデル（質点の1次元運動）"""
    
    def __init__(self, mass: float = 1.0, gravity: float = 9.81):
        self.mass = mass
        self.gravity = gravity
        
        # 状態変数
        self.position = 0.0    # 高度 [m]
        self.velocity = 0.0    # 速度 [m/s]
        self.acceleration = 0.0 # 加速度 [m/s²]
        
    def reset(self, initial_position: float = 0.0, initial_velocity: float = 0.0):
        """植物状態をリセット"""
        self.position = initial_position
        self.velocity = initial_velocity
        self.acceleration = 0.0
        
    def update(self, thrust: float, dt: float) -> Tuple[float, float, float]:
        """植物モデルの更新"""
        # 力の計算: F_thrust - mg = ma
        # thrust: 上向き正、gravity: 下向き正
        net_force = thrust - self.mass * self.gravity
        
        # 加速度の計算
        self.acceleration = net_force / self.mass
        
        # オイラー積分で状態更新
        self.velocity += self.acceleration * dt
        self.position += self.velocity * dt
        
        # センサーノイズを追加（現実的に）
        position_noise = np.random.normal(0, 0.005)  # 0.5cm標準偏差
        velocity_noise = np.random.normal(0, 0.005)  # 0.5cm/s標準偏差
        
        return (
            self.position + position_noise,
            self.velocity + velocity_noise,
            self.acceleration
        )


class OptimizedPIDSimulation:
    """最適化PID制御シミュレーション"""
    
    def __init__(self):
        # シミュレーション設定
        self.dt = 0.01  # タイムステップ [s]
        self.sim_time = 15.0  # シミュレーション時間 [s]
        self.steps = int(self.sim_time / self.dt)
        
        # テストするPIDパラメータセット
        self.pid_configs = [
            {"name": "Conservative", "kp": 8.0, "ki": 0.5, "kd": 6.0},
            {"name": "Balanced", "kp": 12.0, "ki": 1.5, "kd": 8.0},
            {"name": "Aggressive", "kp": 18.0, "ki": 2.5, "kd": 10.0},
            {"name": "Optimized", "kp": 10.0, "ki": 1.0, "kd": 7.5},  # 実験的に最適化
        ]
        
        self.target_altitude = 10.0  # 目標高度 [m]
        
    def run_single_simulation(self, pid_config: Dict, verbose: bool = False) -> Dict:
        """単一のPID設定でシミュレーション実行"""
        plant = SimpleAltitudePlant(mass=1.0, gravity=9.81)
        controller = SimplePIDController(
            kp=pid_config["kp"],
            ki=pid_config["ki"], 
            kd=pid_config["kd"],
            setpoint=self.target_altitude
        )
        
        # データ記録用
        time_data = []
        position_data = []
        velocity_data = []
        thrust_data = []
        error_data = []
        
        # 初期化
        plant.reset(initial_position=0.0, initial_velocity=0.0)
        controller.reset()
        
        current_time = 0.0
        
        for step in range(self.steps):
            # 植物から現在状態を取得
            measured_position, measured_velocity, acceleration = plant.update(0, 0)  # 仮の値
            
            # PID制御器で推力指令を計算
            # 重力補償を含む（mg分を加える）
            pid_output = controller.update(measured_position, self.dt)
            thrust_command = pid_output + plant.mass * plant.gravity
            
            # 推力制限（現実的な範囲）
            max_thrust = 40.0  # 最大推力 [N]
            thrust_command = np.clip(thrust_command, 0, max_thrust)
            
            # 植物モデルを更新
            measured_position, measured_velocity, acceleration = plant.update(thrust_command, self.dt)
            
            # データ記録
            time_data.append(current_time)
            position_data.append(measured_position)
            velocity_data.append(measured_velocity)
            thrust_data.append(thrust_command)
            error_data.append(self.target_altitude - measured_position)
            
            current_time += self.dt
            
            # 進捗表示
            if verbose and step % 300 == 0:
                print(f"[{pid_config['name']}] 時刻: {current_time:.1f}s, 高度: {measured_position:.2f}m")
        
        # 性能指標の計算
        performance = self.analyze_performance(time_data, position_data, error_data, verbose)
        
        return {
            'config': pid_config,
            'performance': performance,
            'data': {
                'time': time_data,
                'position': position_data,
                'velocity': velocity_data,
                'thrust': thrust_data,
                'error': error_data
            }
        }
        
    def analyze_performance(self, time_data: List[float], position_data: List[float], 
                          error_data: List[float], verbose: bool = False) -> Dict:
        """制御性能を分析"""
        # 安定時の誤差（最後の30%のデータを使用）
        stable_start = int(0.7 * len(error_data))
        stable_errors = error_data[stable_start:]
        
        # 性能指標の計算
        steady_state_error = np.mean(np.abs(stable_errors))
        max_overshoot = max(position_data) - self.target_altitude
        rise_time = None
        settling_time = None
        
        # 立ち上がり時間の計算（目標値の90%に到達する時間）
        target_90_percent = 0.9 * self.target_altitude
        for i, pos in enumerate(position_data):
            if pos >= target_90_percent:
                rise_time = time_data[i]
                break
        
        # 整定時間の計算（誤差が5%以内に収まる時間）
        tolerance = 0.05 * self.target_altitude
        for i, error in enumerate(error_data):
            if abs(error) <= tolerance:
                settling_time = time_data[i]
                break
        
        # RMS誤差の計算
        rms_error = np.sqrt(np.mean(np.array(stable_errors)**2))
        
        performance = {
            'steady_state_error': steady_state_error,
            'max_overshoot': max_overshoot,
            'rise_time': rise_time,
            'settling_time': settling_time,
            'rms_error': rms_error,
            'final_altitude': position_data[-1]
        }
        
        if verbose:
            print(f"定常状態誤差: {steady_state_error:.3f} m")
            print(f"最大オーバーシュート: {max_overshoot:.3f} m")
            print(f"立ち上がり時間: {rise_time:.2f} s" if rise_time else "立ち上がり時間: 測定不可")
            print(f"整定時間 (5%): {settling_time:.2f} s" if settling_time else "整定時間: 測定不可")
            print(f"RMS誤差: {rms_error:.3f} m")
            print(f"最終高度: {performance['final_altitude']:.3f} m")
        
        return performance
        
    def run_comparison(self):
        """複数のPID設定を比較"""
        print("=== PID制御パラメータ比較テスト ===")
        print(f"目標高度: {self.target_altitude} m")
        print(f"シミュレーション時間: {self.sim_time} s")
        print()
        
        results = []
        
        # 各設定でシミュレーション実行
        for config in self.pid_configs:
            print(f"テスト中: {config['name']} (Kp={config['kp']}, Ki={config['ki']}, Kd={config['kd']})")
            result = self.run_single_simulation(config, verbose=False)
            results.append(result)
            perf = result['performance']
            print(f"  → 定常誤差: {perf['steady_state_error']:.3f}m, オーバーシュート: {perf['max_overshoot']:.3f}m, 整定時間: {perf['settling_time']:.2f}s")
            print()
        
        # 結果の比較プロット
        self.plot_comparison(results)
        
        # 最適設定の推薦
        self.recommend_best_config(results)
        
        return results
        
    def plot_comparison(self, results: List[Dict]):
        """結果比較のプロット"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('PID Parameter Comparison Results', fontsize=16)
        
        colors = ['blue', 'green', 'red', 'purple']
        
        for i, result in enumerate(results):
            data = result['data']
            config = result['config']
            color = colors[i % len(colors)]
            label = f"{config['name']} (Kp={config['kp']}, Ki={config['ki']}, Kd={config['kd']})"
            
            # 高度の時系列
            axes[0, 0].plot(data['time'], data['position'], color=color, label=label, linewidth=2)
            
            # 誤差の時系列
            axes[0, 1].plot(data['time'], data['error'], color=color, label=label, linewidth=2)
            
            # 推力指令
            axes[1, 0].plot(data['time'], data['thrust'], color=color, label=label, linewidth=2)
            
            # 速度
            axes[1, 1].plot(data['time'], data['velocity'], color=color, label=label, linewidth=2)
        
        # 目標高度ライン
        axes[0, 0].axhline(y=self.target_altitude, color='black', linestyle='--', label='Target')
        axes[0, 1].axhline(y=0, color='black', linestyle='--', alpha=0.5)
        
        # ラベルとフォーマット
        axes[0, 0].set_xlabel('Time [s]')
        axes[0, 0].set_ylabel('Altitude [m]')
        axes[0, 0].set_title('Altitude Response')
        axes[0, 0].legend()
        axes[0, 0].grid(True)
        
        axes[0, 1].set_xlabel('Time [s]')
        axes[0, 1].set_ylabel('Error [m]')
        axes[0, 1].set_title('Altitude Error')
        axes[0, 1].grid(True)
        
        axes[1, 0].set_xlabel('Time [s]')
        axes[1, 0].set_ylabel('Thrust [N]')
        axes[1, 0].set_title('Thrust Command')
        axes[1, 0].grid(True)
        
        axes[1, 1].set_xlabel('Time [s]')
        axes[1, 1].set_ylabel('Velocity [m/s]')
        axes[1, 1].set_title('Velocity')
        axes[1, 1].grid(True)
        
        plt.tight_layout()
        plt.savefig('pid_comparison_results.png', dpi=150, bbox_inches='tight')
        plt.show()
        
    def recommend_best_config(self, results: List[Dict]):
        """最適な設定を推薦"""
        print("\n=== 設定推薦 ===")
        
        # 各指標での最優秀を探す
        min_steady_error = min(results, key=lambda x: x['performance']['steady_state_error'])
        min_overshoot = min(results, key=lambda x: x['performance']['max_overshoot'])
        min_settling_time = min([r for r in results if r['performance']['settling_time'] is not None], 
                              key=lambda x: x['performance']['settling_time'])
        min_rms_error = min(results, key=lambda x: x['performance']['rms_error'])
        
        print(f"最小定常誤差: {min_steady_error['config']['name']} ({min_steady_error['performance']['steady_state_error']:.3f}m)")
        print(f"最小オーバーシュート: {min_overshoot['config']['name']} ({min_overshoot['performance']['max_overshoot']:.3f}m)")
        print(f"最短整定時間: {min_settling_time['config']['name']} ({min_settling_time['performance']['settling_time']:.2f}s)")
        print(f"最小RMS誤差: {min_rms_error['config']['name']} ({min_rms_error['performance']['rms_error']:.3f}m)")
        
        # 総合スコア計算（重み付き）
        print(f"\n総合評価 (定常誤差×2 + オーバーシュート + RMS誤差×2):")
        for result in results:
            perf = result['performance']
            # 正規化のために最大値で割る
            max_steady = max(r['performance']['steady_state_error'] for r in results)
            max_overshoot = max(r['performance']['max_overshoot'] for r in results)
            max_rms = max(r['performance']['rms_error'] for r in results)
            
            normalized_steady = perf['steady_state_error'] / max_steady
            normalized_overshoot = perf['max_overshoot'] / max_overshoot  
            normalized_rms = perf['rms_error'] / max_rms
            
            composite_score = 2*normalized_steady + normalized_overshoot + 2*normalized_rms
            print(f"  {result['config']['name']}: {composite_score:.3f}")
        
        
def main():
    """メイン実行関数"""
    sim = OptimizedPIDSimulation()
    results = sim.run_comparison()


if __name__ == "__main__":
    main()