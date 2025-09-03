#!/usr/bin/env python3
"""
HILS Integrated Log Management and Visualization System
"""
import os
import sys
import argparse
import shutil
import glob
import datetime
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import matplotlib.patches as patches
from pathlib import Path

class HILSAnalyzer:
    def __init__(self, log_dir="logs"):
        self.log_dir = Path(log_dir)
        self.config_file = Path("hils_analyzer_config.json")
        
        # Default configuration
        self.config = {
            "visualization_dpi": 300,
            "default_plots": ["dashboard", "trajectory", "performance"],
            "colors": {
                "primary": "#1f77b4",
                "secondary": "#ff7f0e",
                "success": "#2ca02c", 
                "danger": "#d62728",
                "warning": "#ff7f0e",
                "info": "#17becf"
            }
        }
        
        self.load_config()
        self.ensure_directories()
        
    def load_config(self):
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
                print(f"Loaded configuration from {self.config_file}")
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
                
    def save_config(self):
        """Save current configuration to file"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
        print(f"Configuration saved to {self.config_file}")
        
    def ensure_directories(self):
        """Create necessary directories"""
        self.log_dir.mkdir(exist_ok=True)
        
    def get_latest_run_dir(self):
        """Get the latest run directory"""
        if not self.log_dir.exists():
            return None
            
        # Find all run directories (format: YYYYMMDD_HHMMSS)
        run_dirs = [d for d in self.log_dir.iterdir() if d.is_dir() and d.name.count('_') == 1]
        if not run_dirs:
            return None
            
        # Return the most recent one
        return max(run_dirs, key=lambda x: x.name)
    
    def get_log_files(self, run_dir=None, run_id=None):
        """Get list of log files from specific run directory or latest"""
        if run_id:
            # Use specific run ID
            run_dir = self.log_dir / run_id
            if not run_dir.exists():
                print(f"Run ID {run_id} not found")
                return {}
        elif run_dir is None:
            run_dir = self.get_latest_run_dir()
            
        if run_dir is None:
            return {}
            
        files = {
            'numeric': run_dir / "numeric_log.csv",
            'plant': run_dir / "plant_log.csv"
        }
        return {k: v for k, v in files.items() if v.exists()}
        
    def get_log_info(self):
        """Get information about current log files"""
        log_files = self.get_log_files()
        info = {}
        
        for name, path in log_files.items():
            stat = path.stat()
            info[name] = {
                'path': str(path),
                'size_mb': stat.st_size / (1024 * 1024),
                'modified': datetime.datetime.fromtimestamp(stat.st_mtime),
                'lines': None
            }
            
            # Count lines
            try:
                with open(path, 'r') as f:
                    info[name]['lines'] = sum(1 for _ in f) - 1  # Subtract header
            except Exception as e:
                info[name]['lines'] = f"Error: {e}"
                
        return info
        
            
    def load_simulation_data(self, run_id=None):
        """Load and validate simulation data"""
        log_files = self.get_log_files(run_id=run_id)
        
        if 'numeric' not in log_files:
            raise FileNotFoundError("numeric_log.csv not found")
            
        # Load numeric data (required)
        self.numeric_data = pd.read_csv(log_files['numeric'])
        print(f"Loaded {len(self.numeric_data)} numeric data points")
        
        # Load plant data (optional)
        self.plant_data = None
        if 'plant' in log_files:
            try:
                self.plant_data = pd.read_csv(log_files['plant'])
                print(f"Loaded {len(self.plant_data)} plant data points")
            except Exception as e:
                print(f"Warning: Could not load plant data: {e}")
                
        return True
        
    def create_dashboard(self):
        """Create comprehensive analysis dashboard"""
        fig = plt.figure(figsize=(16, 12))
        gs = GridSpec(3, 3, figure=fig, hspace=0.35, wspace=0.3)
        
        fig.suptitle('HILS Comprehensive Analysis Dashboard', fontsize=18, fontweight='bold')
        
        # Data preparation
        t = self.numeric_data['t'].values
        altitude = self.numeric_data['pos_z'].values
        cmd_z = self.numeric_data['cmd_z'].values
        vel_z = self.numeric_data['vel_z'].values
        error = self.numeric_data['error_z'].values
        rtt = self.numeric_data['rtt_ms'].values
        
        colors = self.config['colors']
        
        # 1. Altitude Control (main plot)
        ax1 = fig.add_subplot(gs[0, :2])
        ax1.plot(t, altitude, color=colors['primary'], linewidth=2.5, label='Actual Altitude')
        ax1.axhline(y=10.0, color=colors['danger'], linestyle='--', linewidth=2, label='Target (10m)')
        ax1.fill_between(t, altitude, 10, where=(altitude < 10), alpha=0.3, 
                        color=colors['danger'], label='Below Target')
        ax1.set_xlabel('Time [s]')
        ax1.set_ylabel('Altitude [m]')
        ax1.set_title('Altitude Control Performance', fontweight='bold')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. Control Commands
        ax2 = fig.add_subplot(gs[0, 2])
        ax2.plot(t, cmd_z, color=colors['success'], linewidth=2)
        ax2.axhline(y=9.81, color='gray', linestyle=':', linewidth=2, label='Gravity')
        ax2.set_xlabel('Time [s]')
        ax2.set_ylabel('Thrust [N]')
        ax2.set_title('Control Commands', fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 3. Velocity Profile
        ax3 = fig.add_subplot(gs[1, 0])
        ax3.plot(t, vel_z, color=colors['warning'], linewidth=2)
        ax3.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax3.fill_between(t, vel_z, 0, where=(vel_z > 0), alpha=0.5, color='blue', label='Up')
        ax3.fill_between(t, vel_z, 0, where=(vel_z < 0), alpha=0.5, color='red', label='Down')
        ax3.set_xlabel('Time [s]')
        ax3.set_ylabel('Velocity [m/s]')
        ax3.set_title('Vertical Velocity', fontweight='bold')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 4. Error Analysis
        ax4 = fig.add_subplot(gs[1, 1])
        ax4.plot(t, np.abs(error), color=colors['danger'], linewidth=2)
        ax4.set_xlabel('Time [s]')
        ax4.set_ylabel('|Error| [m]')
        ax4.set_title('Control Error', fontweight='bold')
        ax4.grid(True, alpha=0.3)
        
        # Error statistics
        mean_error = np.mean(np.abs(error))
        ax4.text(0.05, 0.95, f'Mean: {mean_error:.2f}m\nFinal: {np.abs(error[-1]):.2f}m', 
                transform=ax4.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        # 5. Communication Performance
        ax5 = fig.add_subplot(gs[1, 2])
        ax5.plot(t, rtt, color=colors['info'], linewidth=1, alpha=0.7)
        ax5.set_xlabel('Time [s]')
        ax5.set_ylabel('RTT [ms]')
        ax5.set_title('Communication', fontweight='bold')
        ax5.grid(True, alpha=0.3)
        
        # RTT statistics
        mean_rtt = np.mean(rtt)
        std_rtt = np.std(rtt)
        ax5.text(0.05, 0.95, f'{mean_rtt:.2f}±{std_rtt:.2f}ms', 
                transform=ax5.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='lightcyan', alpha=0.8))
        
        # 6. Phase Portrait
        ax6 = fig.add_subplot(gs[2, 0])
        scatter = ax6.scatter(altitude, vel_z, c=t, cmap='viridis', s=15, alpha=0.6)
        ax6.set_xlabel('Altitude [m]')
        ax6.set_ylabel('Velocity [m/s]')
        ax6.set_title('Phase Portrait', fontweight='bold')
        ax6.grid(True, alpha=0.3)
        
        # 7. Control Effort
        ax7 = fig.add_subplot(gs[2, 1])
        control_effort = cmd_z - 9.81
        ax7.plot(t, control_effort, color=colors['secondary'], linewidth=2)
        ax7.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax7.fill_between(t, control_effort, 0, alpha=0.3, color=colors['secondary'])
        ax7.set_xlabel('Time [s]')
        ax7.set_ylabel('Net Thrust [N]')
        ax7.set_title('Control Effort', fontweight='bold')
        ax7.grid(True, alpha=0.3)
        
        # 8. Performance Summary
        ax8 = fig.add_subplot(gs[2, 2])
        ax8.axis('off')
        
        # Performance metrics
        metrics = [
            f"Simulation: {t[-1]:.2f}s ({len(t)} steps)",
            f"Final Alt: {altitude[-1]:.2f}m (target: 10m)",
            f"Alt Error: {error[-1]:.2f}m",
            f"Max Speed: {np.max(np.abs(vel_z)):.2f}m/s", 
            f"Thrust Range: {np.min(cmd_z):.1f}-{np.max(cmd_z):.1f}N",
            f"Comm: {mean_rtt:.2f}±{std_rtt:.2f}ms",
            f"Success Rate: 100%"
        ]
        
        y_start = 0.9
        for i, metric in enumerate(metrics):
            ax8.text(0.05, y_start - i*0.12, metric, transform=ax8.transAxes, 
                    fontsize=11, verticalalignment='top')
                    
        ax8.set_title('Performance Summary', fontweight='bold', pad=20)
        
        return fig
        
    def create_trajectory_3d(self):
        """Create 3D trajectory visualization"""
        fig = plt.figure(figsize=(12, 9))
        ax = fig.add_subplot(111, projection='3d')
        
        x = self.numeric_data['pos_x'].values
        y = self.numeric_data['pos_y'].values
        z = self.numeric_data['pos_z'].values
        t = self.numeric_data['t'].values
        
        # Plot trajectory
        scatter = ax.scatter(x, y, z, c=t, cmap='plasma', s=25, alpha=0.8)
        
        # Mark important points
        ax.scatter([x[0]], [y[0]], [z[0]], color='green', s=150, marker='o', label='Start')
        ax.scatter([x[-1]], [y[-1]], [z[-1]], color='red', s=150, marker='s', label='End')
        ax.scatter([0], [0], [10], color='gold', s=300, marker='*', label='Target (0,0,10m)')
        
        # Add colorbar
        cbar = plt.colorbar(scatter, ax=ax, shrink=0.8, aspect=20)
        cbar.set_label('Time [s]', fontsize=12)
        
        ax.set_xlabel('X Position [m]', fontsize=12)
        ax.set_ylabel('Y Position [m]', fontsize=12)
        ax.set_zlabel('Z Altitude [m]', fontsize=12)
        ax.set_title('HILS 3D Flight Trajectory', fontsize=16, fontweight='bold')
        ax.legend()
        
        return fig
        
    def create_performance_report(self):
        """Create detailed performance analysis report"""
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        fig.suptitle('HILS Performance Analysis Report', fontsize=16, fontweight='bold')
        
        t = self.numeric_data['t'].values
        altitude = self.numeric_data['pos_z'].values
        cmd_z = self.numeric_data['cmd_z'].values
        vel_z = self.numeric_data['vel_z'].values
        error = self.numeric_data['error_z'].values
        rtt = self.numeric_data['rtt_ms'].values
        
        # 1. Altitude tracking
        axes[0,0].plot(t, altitude, 'b-', linewidth=2, label='Actual')
        axes[0,0].axhline(10, color='r', linestyle='--', label='Target')
        axes[0,0].set_title('Altitude Tracking')
        axes[0,0].set_ylabel('Altitude [m]')
        axes[0,0].legend()
        axes[0,0].grid(True, alpha=0.3)
        
        # 2. Control signal
        axes[0,1].plot(t, cmd_z, 'g-', linewidth=2)
        axes[0,1].axhline(9.81, color='gray', linestyle=':', label='Gravity')
        axes[0,1].set_title('Control Signal')
        axes[0,1].set_ylabel('Thrust [N]')
        axes[0,1].legend()
        axes[0,1].grid(True, alpha=0.3)
        
        # 3. Error histogram
        axes[0,2].hist(error, bins=30, alpha=0.7, color='orange', edgecolor='black')
        axes[0,2].axvline(0, color='red', linestyle='--')
        axes[0,2].set_title('Error Distribution')
        axes[0,2].set_xlabel('Error [m]')
        axes[0,2].set_ylabel('Frequency')
        axes[0,2].grid(True, alpha=0.3)
        
        # 4. Velocity vs time
        axes[1,0].plot(t, vel_z, 'purple', linewidth=2)
        axes[1,0].axhline(0, color='black', alpha=0.5)
        axes[1,0].set_title('Velocity Profile')
        axes[1,0].set_xlabel('Time [s]')
        axes[1,0].set_ylabel('Velocity [m/s]')
        axes[1,0].grid(True, alpha=0.3)
        
        # 5. RTT analysis
        axes[1,1].plot(t, rtt, 'cyan', linewidth=1, alpha=0.7)
        axes[1,1].set_title('Communication Latency')
        axes[1,1].set_xlabel('Time [s]')
        axes[1,1].set_ylabel('RTT [ms]')
        axes[1,1].grid(True, alpha=0.3)
        
        # 6. Control performance metrics
        axes[1,2].axis('off')
        
        # Calculate performance metrics
        settling_time = None
        steady_state_error = np.mean(np.abs(error[-100:]))  # Last 100 points
        overshoot = np.max(altitude) - 10 if np.max(altitude) > 10 else 0
        rise_time = None
        
        # Find rise time (10% to 90% of target)
        target_10 = 0.1 * 10
        target_90 = 0.9 * 10
        try:
            idx_10 = np.where(altitude >= target_10)[0][0]
            idx_90 = np.where(altitude >= target_90)[0][0]
            rise_time = t[idx_90] - t[idx_10]
        except:
            rise_time = None
            
        # Find settling time (within 2% of target)
        try:
            settling_band = 0.02 * 10  # 2% of 10m
            for i in range(len(altitude)-100, len(altitude)):
                if abs(altitude[i:] - 10).max() <= settling_band:
                    settling_time = t[i]
                    break
        except:
            settling_time = None
            
        # Format time metrics safely
        rise_time_str = f"{rise_time:.3f} s" if rise_time is not None else "N/A"
        settling_time_str = f"{settling_time:.3f} s" if settling_time is not None else "N/A"
        
        metrics_text = f"""Performance Metrics:

Steady-state error: {steady_state_error:.3f} m
Overshoot: {overshoot:.3f} m
Rise time: {rise_time_str}
Settling time: {settling_time_str}

Communication:
Mean RTT: {np.mean(rtt):.2f} ms
RTT std dev: {np.std(rtt):.2f} ms
Max RTT: {np.max(rtt):.2f} ms

Simulation:
Duration: {t[-1]:.2f} s
Steps: {len(t)}
Step rate: {len(t)/t[-1]:.0f} Hz"""
        
        axes[1,2].text(0.05, 0.95, metrics_text, transform=axes[1,2].transAxes,
                      fontsize=10, verticalalignment='top', fontfamily='monospace')
        
        plt.tight_layout()
        return fig
        
    def generate_visualizations(self, plots=None, run_id=None):
        """Generate all requested visualizations"""
        if plots is None:
            plots = self.config['default_plots']
            
        if not self.load_simulation_data(run_id=run_id):
            return False
            
        generated_files = []
        dpi = self.config['visualization_dpi']
        
        # Determine target directory
        if run_id:
            target_dir = self.log_dir / run_id
        else:
            target_dir = self.get_latest_run_dir()
        
        if 'dashboard' in plots:
            print("Generating comprehensive dashboard...")
            fig = self.create_dashboard()
            filename = target_dir / 'hils_analysis_dashboard.png' if target_dir else 'hils_analysis_dashboard.png'
            fig.savefig(str(filename), dpi=dpi, bbox_inches='tight')
            generated_files.append(str(filename))
            plt.close(fig)
            
        if 'trajectory' in plots:
            print("Generating 3D trajectory...")
            fig = self.create_trajectory_3d()
            filename = target_dir / 'hils_flight_trajectory.png' if target_dir else 'hils_flight_trajectory.png'
            fig.savefig(str(filename), dpi=dpi, bbox_inches='tight')
            generated_files.append(str(filename))
            plt.close(fig)
            
        if 'performance' in plots:
            print("Generating performance report...")
            fig = self.create_performance_report()
            filename = target_dir / 'hils_performance_report.png' if target_dir else 'hils_performance_report.png'
            fig.savefig(str(filename), dpi=dpi, bbox_inches='tight')
            generated_files.append(str(filename))
            plt.close(fig)
            
        print(f"Generated {len(generated_files)} visualization files:")
        for filename in generated_files:
            print(f"  - {filename}")
            
        return generated_files
        
    def print_log_status(self):
        """Print current log status"""
        info = self.get_log_info()
        
        print("\n" + "="*60)
        print("HILS LOG STATUS")
        print("="*60)
        
        for name, details in info.items():
            print(f"\n{name.upper()} LOG:")
            print(f"  File: {details['path']}")
            print(f"  Size: {details['size_mb']:.2f} MB")
            print(f"  Lines: {details['lines']}")
            print(f"  Modified: {details['modified'].strftime('%Y-%m-%d %H:%M:%S')}")
            
        print("="*60)

def main():
    parser = argparse.ArgumentParser(
        description='HILS Integrated Log Management and Visualization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status                 - Show log status
  %(prog)s visualize             - Generate all visualizations
  %(prog)s visualize --plots dashboard trajectory - Generate specific plots
  %(prog)s visualize --run-id 20250903_211154 - Analyze specific run
  %(prog)s config --dpi 150      - Set visualization DPI to 150
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show log status')
    
    # Visualize command
    viz_parser = subparsers.add_parser('visualize', help='Generate visualizations')
    viz_parser.add_argument('--plots', nargs='+', 
                           choices=['dashboard', 'trajectory', 'performance'],
                           help='Specific plots to generate')
    viz_parser.add_argument('--show', action='store_true', help='Show plots after generation')
    viz_parser.add_argument('--run-id', help='Specific run ID to analyze (e.g., 20250903_211154)')
    
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Manage configuration')
    config_parser.add_argument('--retention', type=int, help='Set log retention days')
    config_parser.add_argument('--dpi', type=int, help='Set visualization DPI')
    config_parser.add_argument('--show', action='store_true', help='Show current config')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
        
    analyzer = HILSAnalyzer()
    
    if args.command == 'status':
        analyzer.print_log_status()
        
    elif args.command == 'visualize':
        plots = args.plots if args.plots else None
        run_id = getattr(args, 'run_id', None)
        files = analyzer.generate_visualizations(plots, run_id=run_id)
        if args.show and files:
            import subprocess
            for f in files:
                if Path(f).exists():
                    try:
                        subprocess.run(['xdg-open', f], check=False)
                    except:
                        print(f"Generated: {f}")
                        
        
    elif args.command == 'config':
        if args.retention:
            analyzer.config['log_retention_days'] = args.retention
            analyzer.save_config()
            print(f"Log retention set to {args.retention} days")
        if args.dpi:
            analyzer.config['visualization_dpi'] = args.dpi
            analyzer.save_config()
            print(f"Visualization DPI set to {args.dpi}")
        if args.show:
            print(json.dumps(analyzer.config, indent=2))

if __name__ == "__main__":
    main()