#!/usr/bin/env python3
"""
オーバーシュート抑制に特化したPID制御シミュレーション
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


class AntiOvershootPIDController:
    """オーバーシュート抑制PID制御器"""
    
    def __init__(self, kp: float, ki: float, kd: float, setpoint: float):
        self.kp = kp
        self.ki = ki  
        self.kd = kd
        self.setpoint = setpoint
        
        self.error_sum = 0.0
        self.prev_error = None
        self.prev_time = None
        
        # 積分項のwindup防止
        self.integral_limit = 20.0
        
        # オーバーシュート抑制のための設定
        self.overshoot_threshold = 0.1  # 目標値の10%以内に近づいたら積分を停止
        self.derivative_kick_prevention = True  # 微分キック防止
        
    def reset(self):
        """制御器状態をリセット"""
        self.error_sum = 0.0
        self.prev_error = None
        self.prev_time = None
        
    def update(self, measurement: float, dt: float) -> float:
        """オーバーシュート抑制PID制御器の更新"""
        error = self.setpoint - measurement
        
        # 初回呼び出し時の初期化
        if self.prev_error is None:
            self.prev_error = error
            
        # 比例項
        p_term = self.kp * error
        
        # 積分項（オーバーシュート近くでは積分を停止）
        if abs(error) > self.overshoot_threshold * self.setpoint:
            self.error_sum += error * dt
            self.error_sum = np.clip(self.error_sum, -self.integral_limit, self.integral_limit)
        # 目標値に近づいたら積分を凍結してオーバーシュートを防ぐ
        
        i_term = self.ki * self.error_sum
        
        # 微分項（微分キック防止）
        if dt > 0:
            if self.derivative_kick_prevention:
                # 測定値の変化に対してのみ微分を適用（setpoint変化による微分キック防止）
                d_term = -self.kd * (measurement - (self.setpoint - self.prev_error)) / dt
            else:
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


class AntiOvershootSimulation:
    """オーバーシュート抑制PID制御シミュレーション"""
    
    def __init__(self):
        # シミュレーション設定
        self.dt = 0.01  # タイムステップ [s]
        self.sim_time = 20.0  # シミュレーション時間 [s]
        self.steps = int(self.sim_time / self.dt)
        
        # テストするPIDパラメータセット（オーバーシュート抑制重視）
        self.pid_configs = [
            {"name": "Standard", "type": "standard", "kp": 18.0, "ki": 2.5, "kd": 10.0},
            {"name": "Low_Overshoot_1", "type": "standard", "kp": 12.0, "ki": 1.0, "kd": 15.0},  # 高D、低K
            {"name": "Low_Overshoot_2", "type": "standard", "kp": 8.0, "ki": 0.5, "kd": 20.0},   # さらに高D
            {"name": "Anti_Overshoot", "type": "anti_overshoot", "kp": 15.0, "ki": 2.0, "kd": 12.0},  # 特殊制御
            {"name": "Conservative_Plus", "type": "standard", "kp": 10.0, "ki": 0.8, "kd": 18.0}, # バランス重視
        ]
        
        self.target_altitude = 10.0  # 目標高度 [m]
        
    def run_single_simulation(self, pid_config: Dict, verbose: bool = False) -> Dict:
        """単一のPID設定でシミュレーション実行"""
        plant = SimpleAltitudePlant(mass=1.0, gravity=9.81)
        
        # 制御器の選択
        if pid_config["type"] == "anti_overshoot":
            controller = AntiOvershootPIDController(
                kp=pid_config["kp"],
                ki=pid_config["ki"], 
                kd=pid_config["kd"],
                setpoint=self.target_altitude
            )
        else:
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
            max_thrust = 1000.0  # 最大推力 [N]
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
            if verbose and step % 400 == 0:
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
        print("=== オーバーシュート抑制PID制御パラメータ比較テスト ===")
        print(f"目標高度: {self.target_altitude} m")
        print(f"シミュレーション時間: {self.sim_time} s")
        print()
        
        results = []
        
        # 各設定でシミュレーション実行
        for config in self.pid_configs:
            controller_type = "Anti-Overshoot" if config['type'] == 'anti_overshoot' else "Standard"
            print(f"テスト中: {config['name']} ({controller_type}) (Kp={config['kp']}, Ki={config['ki']}, Kd={config['kd']})")
            result = self.run_single_simulation(config, verbose=False)
            results.append(result)
            perf = result['performance']
            print(f"  → 定常誤差: {perf['steady_state_error']:.3f}m, オーバーシュート: {perf['max_overshoot']:.3f}m, 整定時間: {perf['settling_time']:.2f}s")
            print()
        
        # 結果の比較プロット
        self.plot_comparison(results)
        
        # オーバーシュート最小の推薦
        self.recommend_best_config(results)
        
        return results
        
    def plot_comparison(self, results: List[Dict]):
        """結果比較のプロット"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Anti-Overshoot PID Comparison Results', fontsize=16)
        
        colors = ['blue', 'green', 'red', 'purple', 'orange']
        
        for i, result in enumerate(results):
            data = result['data']
            config = result['config']
            color = colors[i % len(colors)]
            ctrl_type = "AO" if config['type'] == 'anti_overshoot' else "Std"
            label = f"{config['name']} ({ctrl_type}) - OS:{result['performance']['max_overshoot']:.2f}m"
            
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
        plt.savefig('anti_overshoot_comparison.png', dpi=150, bbox_inches='tight')
        plt.show()
        
    def recommend_best_config(self, results: List[Dict]):
        """最適な設定を推薦"""
        print("\n=== オーバーシュート抑制設定推薦 ===")
        
        # 各指標での最優秀を探す
        min_overshoot = min(results, key=lambda x: x['performance']['max_overshoot'])
        min_steady_error = min(results, key=lambda x: x['performance']['steady_state_error'])
        min_settling_time = min([r for r in results if r['performance']['settling_time'] is not None], 
                              key=lambda x: x['performance']['settling_time'])
        
        print(f"最小オーバーシュート: {min_overshoot['config']['name']} ({min_overshoot['performance']['max_overshoot']:.3f}m)")
        print(f"最小定常誤差: {min_steady_error['config']['name']} ({min_steady_error['performance']['steady_state_error']:.3f}m)")  
        print(f"最短整定時間: {min_settling_time['config']['name']} ({min_settling_time['performance']['settling_time']:.2f}s)")
        
        # オーバーシュート重視スコア計算
        print(f"\nオーバーシュート重視評価 (オーバーシュート×3 + 定常誤差 + 整定時間/10):")
        for result in results:
            perf = result['performance']
            settling_penalty = perf['settling_time'] / 10.0 if perf['settling_time'] else 2.0
            overshoot_score = 3 * perf['max_overshoot'] + perf['steady_state_error'] + settling_penalty
            print(f"  {result['config']['name']}: {overshoot_score:.3f}")


def main():
    """メイン実行関数"""
    sim = AntiOvershootSimulation()
    results = sim.run_comparison()


if __name__ == "__main__":
    main()