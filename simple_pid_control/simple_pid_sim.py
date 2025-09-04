#!/usr/bin/env python3
"""
独立したPID制御シミュレーション - 高度制御
ZMQ通信を使わずに、単一プロセスで動作する閉じたシステム
"""

import numpy as np
import matplotlib.pyplot as plt
import time
from typing import List, Tuple

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
        self.integral_limit = 50.0
        
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
        position_noise = np.random.normal(0, 0.01)  # 1cm標準偏差
        velocity_noise = np.random.normal(0, 0.01)  # 1cm/s標準偏差
        
        return (
            self.position + position_noise,
            self.velocity + velocity_noise,
            self.acceleration
        )


class SimplePIDSimulation:
    """PID制御シミュレーション"""
    
    def __init__(self):
        # シミュレーション設定
        self.dt = 0.01  # タイムステップ [s]
        self.sim_time = 20.0  # シミュレーション時間 [s]
        self.steps = int(self.sim_time / self.dt)
        
        # 植物モデル
        self.plant = SimpleAltitudePlant(mass=1.0, gravity=9.81)
        
        # PID制御器（調整しやすいパラメータ）
        self.controller = SimplePIDController(
            kp=15.0,  # 比例ゲイン - 応答の速さ
            ki=2.0,   # 積分ゲイン - 定常誤差の除去
            kd=8.0,   # 微分ゲイン - オーバーシュートの抑制
            setpoint=10.0  # 目標高度 [m]
        )
        
        # データ記録用
        self.time_data = []
        self.position_data = []
        self.velocity_data = []
        self.thrust_data = []
        self.error_data = []
        self.setpoint_data = []
        
    def run_simulation(self) -> None:
        """シミュレーション実行"""
        print("シンプルPID高度制御シミュレーション開始")
        print(f"目標高度: {self.controller.setpoint} m")
        print(f"PIDパラメータ: Kp={self.controller.kp}, Ki={self.controller.ki}, Kd={self.controller.kd}")
        
        # 初期化
        self.plant.reset(initial_position=0.0, initial_velocity=0.0)
        self.controller.reset()
        
        current_time = 0.0
        
        for step in range(self.steps):
            # 植物から現在状態を取得
            measured_position, measured_velocity, acceleration = self.plant.update(0, 0)  # 仮の値
            
            # PID制御器で推力指令を計算
            # 重力補償を含む（mg分を加える）
            pid_output = self.controller.update(measured_position, self.dt)
            thrust_command = pid_output + self.plant.mass * self.plant.gravity
            
            # 推力制限（現実的な範囲）
            max_thrust = 1000.0  # 最大推力 [N]
            thrust_command = np.clip(thrust_command, 0, max_thrust)
            
            # 植物モデルを更新
            measured_position, measured_velocity, acceleration = self.plant.update(thrust_command, self.dt)
            
            # データ記録
            self.time_data.append(current_time)
            self.position_data.append(measured_position)
            self.velocity_data.append(measured_velocity)
            self.thrust_data.append(thrust_command)
            self.error_data.append(self.controller.setpoint - measured_position)
            self.setpoint_data.append(self.controller.setpoint)
            
            current_time += self.dt
            
            # 進捗表示
            if step % 200 == 0:
                print(f"時刻: {current_time:.2f}s, 高度: {measured_position:.2f}m, 推力: {thrust_command:.1f}N")
        
        print("シミュレーション完了")
        
    def plot_results(self) -> None:
        """結果をプロット"""
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        fig.suptitle('PID Altitude Control Simulation Results')
        
        # 高度の時系列
        axes[0, 0].plot(self.time_data, self.position_data, 'b-', label='Actual Altitude')
        axes[0, 0].plot(self.time_data, self.setpoint_data, 'r--', label='Target Altitude')
        axes[0, 0].set_xlabel('Time [s]')
        axes[0, 0].set_ylabel('Altitude [m]')
        axes[0, 0].set_title('Altitude Response')
        axes[0, 0].legend()
        axes[0, 0].grid(True)
        
        # 誤差の時系列
        axes[0, 1].plot(self.time_data, self.error_data, 'g-')
        axes[0, 1].set_xlabel('Time [s]')
        axes[0, 1].set_ylabel('Error [m]')
        axes[0, 1].set_title('Altitude Error')
        axes[0, 1].grid(True)
        
        # 推力指令
        axes[1, 0].plot(self.time_data, self.thrust_data, 'm-')
        axes[1, 0].set_xlabel('Time [s]')
        axes[1, 0].set_ylabel('Thrust [N]')
        axes[1, 0].set_title('Thrust Command')
        axes[1, 0].grid(True)
        
        # 速度
        axes[1, 1].plot(self.time_data, self.velocity_data, 'c-')
        axes[1, 1].set_xlabel('Time [s]')
        axes[1, 1].set_ylabel('Velocity [m/s]')
        axes[1, 1].set_title('Velocity')
        axes[1, 1].grid(True)
        
        plt.tight_layout()
        plt.savefig('simple_pid_results.png', dpi=150, bbox_inches='tight')
        plt.show()
        
    def analyze_performance(self) -> None:
        """制御性能を分析"""
        # 安定時の誤差（最後の20%のデータを使用）
        stable_start = int(0.8 * len(self.error_data))
        stable_errors = self.error_data[stable_start:]
        
        # 性能指標の計算
        steady_state_error = np.mean(np.abs(stable_errors))
        max_overshoot = max(self.position_data) - self.controller.setpoint
        settling_time = None
        
        # 整定時間の計算（誤差が5%以内に収まる時間）
        tolerance = 0.05 * self.controller.setpoint
        for i, error in enumerate(self.error_data):
            if abs(error) <= tolerance:
                settling_time = self.time_data[i]
                break
        
        print("\n=== 制御性能分析 ===")
        print(f"定常状態誤差: {steady_state_error:.3f} m")
        print(f"最大オーバーシュート: {max_overshoot:.3f} m")
        print(f"整定時間 (5%以内): {settling_time:.2f} s" if settling_time else "整定時間: 測定不可")
        print(f"最終高度: {self.position_data[-1]:.3f} m")


def main():
    """メイン実行関数"""
    # シミュレーション作成・実行
    sim = SimplePIDSimulation()
    sim.run_simulation()
    
    # 結果の表示・解析
    sim.analyze_performance()
    sim.plot_results()


if __name__ == "__main__":
    main()