import subprocess
import os
import time
import sys

def run_in_new_window(command, title):
    """Runs a command in a new command prompt window."""
    print(f"Starting {title}...")
    subprocess.Popen(f'start "{title}" cmd /k "{command}"', shell=True)
    time.sleep(1)

def main():
    print("=" * 45)
    print("=== IoT Anomaly Detection System Launcher ===")
    print("=" * 45)
    print("\n[CRITICAL] Ensure Ganache is running on http://127.0.0.1:7545")
    print("[CRITICAL] before continuing, or dashboard may crash!\n")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Server
    server_dir = os.path.join(base_dir, "server")
    run_in_new_window(f"cd {server_dir} && node index.js", "1. Server")
    
    # 2. Gateway
    gateway_dir = os.path.join(base_dir, "gateway")
    run_in_new_window(f"cd {gateway_dir} && python gateway_service.py", "2. Gateway")
    
    # 3. ML Engine
    ml_dir = os.path.join(base_dir, "ml-engine")
    run_in_new_window(f"cd {ml_dir} && python anomaly_detector.py", "3. ML Engine")
    
    # 4. Dashboard
    dashboard_dir = os.path.join(base_dir, "dashboard")
    run_in_new_window(f"cd {dashboard_dir} && npm run dev", "4. Dashboard")
    
    print("\nCalculated initialization time...")
    time.sleep(5)
    
    # 5. Simulator (Ask user)
    start_sim = input("Start IoT Simulator now? (y/n): ")
    if start_sim.lower() == 'y':
        sim_dir = os.path.join(base_dir, "iot-device")
        run_in_new_window(f"cd {sim_dir} && python simulator.py", "5. IoT Simulator")

    print("\nSystem running. Check the separate windows.")
    print("Dashboard: http://localhost:5173")

if __name__ == "__main__":
    main()
