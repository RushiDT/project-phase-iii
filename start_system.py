import subprocess
import os
import time
import sys
import requests

def run_in_new_window(command, title, cwd=None):
    """Runs a command in a new command prompt window."""
    print(f"  Starting {title}...")
    
    # Get venv activation path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_activate = os.path.join(base_dir, ".venv", "Scripts", "activate.bat")
    
    # For Python commands, activate venv first
    if command.startswith("python") and os.path.exists(venv_activate):
        full_command = f'"{venv_activate}" && {command}'
    else:
        full_command = command
    
    if cwd:
        subprocess.Popen(f'start "{title}" cmd /k "cd /D {cwd} && {full_command}"', shell=True)
    else:
        subprocess.Popen(f'start "{title}" cmd /k "{full_command}"', shell=True)
    time.sleep(1.5)

def check_health(name, url, timeout=2):
    """Check if a service is responding."""
    try:
        # Ganache uses JSON-RPC, not HTTP GET
        if "7545" in url:
            response = requests.post(url, json={"jsonrpc": "2.0", "method": "net_version", "params": [], "id": 1}, timeout=timeout)
        else:
            response = requests.get(url, timeout=timeout)
        if response.status_code in [200, 404]:  # 404 is OK for some endpoints
            return True, "✓ Running"
    except:
        pass
    return False, "✗ Not responding"

def print_status_table(services):
    """Print a formatted status table."""
    print("\n" + "=" * 60)
    print("  SERVICE STATUS")
    print("=" * 60)
    print(f"  {'Component':<20} {'URL':<25} {'Status':<15}")
    print("-" * 60)
    for name, url, status in services:
        status_color = status if "✓" in status else status
        print(f"  {name:<20} {url:<25} {status_color:<15}")
    print("=" * 60)

def main():
    print("\n")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       IoT Anomaly Detection System Launcher              ║")
    print("║                 with Health Checks                       ║")
    print("╚══════════════════════════════════════════════════════════╝")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Architecture choice
    print("\n[Architecture Selection]")
    is_remote_gateway = input("      Is the Gateway running on a Raspberry Pi? (y/n): ").lower() == 'y'
    gateway_ip = "localhost"
    if is_remote_gateway:
        gateway_ip = input("      Enter Raspberry Pi IP Address: ")

    # 0. Start Ganache (blockchain)
    print("\n[0/6] Starting Ganache blockchain...")
    run_in_new_window("npx ganache --port 7545 --deterministic", "0. Ganache (Port 7545)", base_dir)
    time.sleep(3)  # Give Ganache time to start
    
    # 1. Server
    print("\n[1/4] Starting services...")
    server_dir = os.path.join(base_dir, "server")
    run_in_new_window("node index.js", "1. Server (Port 5002)", server_dir)
    
    # 2. Gateway (Skip if remote)
    if not is_remote_gateway:
        gateway_dir = os.path.join(base_dir, "gateway")
        run_in_new_window("python gateway_service.py", "2. Gateway (Port 8090)", gateway_dir)
    else:
        print(f"  [i] Skipping local Gateway startup (Remote at {gateway_ip})")
    
    # 3. ML Engine
    ml_dir = os.path.join(base_dir, "ml-engine")
    run_in_new_window("python anomaly_detector.py", "3. ML Engine (Port 5001)", ml_dir)
    
    # 4. Dashboard
    dashboard_dir = os.path.join(base_dir, "dashboard")
    run_in_new_window("npm run dev", "4. Dashboard (Port 5173)", dashboard_dir)
    
    print("\n[2/4] Waiting for services to initialize (8s)...")
    for i in range(8, 0, -1):
        print(f"  {i}s...", end="\r")
        time.sleep(1)
    print("       ")
    
    # 3. Health checks
    print("[3/4] Running health checks...")
    services = [
        ("Server", "http://localhost:5002/api/logs", check_health("Server", "http://localhost:5002/api/logs")[1]),
        ("Gateway", f"http://{gateway_ip}:8090/status", check_health("Gateway", f"http://{gateway_ip}:8090/status")[1]),
        ("ML Engine", "http://localhost:5001/health", check_health("ML Engine", "http://localhost:5001/health")[1]),
        ("Dashboard", "http://localhost:5173", check_health("Dashboard", "http://localhost:5173")[1]),
        ("Ganache", "http://localhost:7545", check_health("Ganache", "http://localhost:7545")[1])
    ]
    print_status_table(services)
    
    # Auto-deploy blockchain if Ganache is running
    ganache_healthy = "✓" in services[4][2]  # Check if Ganache is running
    
    # Get venv python for internal calls
    venv_python = os.path.join(base_dir, ".venv", "Scripts", "python.exe") if os.name == 'nt' else \
                  os.path.join(base_dir, ".venv", "bin", "python")
    python_exe = venv_python if os.path.exists(venv_python) else sys.executable

    if ganache_healthy:
        print("\n[3.5/5] Deploying Smart Contract...")
        blockchain_dir = os.path.join(base_dir, "blockchain")
        result = subprocess.run(
            [python_exe, "deploy_and_interact.py"],
            cwd=blockchain_dir,
            capture_output=True,
            text=True
        )
        if "Contract Deployed" in result.stdout:
            print("  ✓ Smart Contract deployed successfully!")
            
            # --- Proactive Registration ---
            registry_path = os.path.join(base_dir, "server", "devices.json")
            if os.path.exists(registry_path):
                print("  [i] Pre-registering devices on Blockchain...")
                try:
                    import json
                    with open(registry_path, 'r') as f:
                        devices = json.load(f)
                    for dev in devices:
                        reg_res = subprocess.run(
                            [python_exe, "deploy_and_interact.py", "register_device", dev["id"], "IOT_SENSOR", "server_admin"],
                            cwd=blockchain_dir,
                            capture_output=True,
                            text=True
                        )
                        if reg_res.returncode == 0:
                            print(f"    ✓ Registered {dev['id']}")
                        else:
                            print(f"    ✗ Failed to register {dev['id']}: {reg_res.stderr.strip() or reg_res.stdout.strip()}")
                except Exception as e:
                    print(f"  ✗ Error in pre-registration: {e}")
            # -------------------------------
        else:
            print("  ⚠ Blockchain deployment failed. Run manually if needed.")
            error_msg: str = str(result.stderr or result.stdout or "")
            if error_msg.strip():
                print(f"    {error_msg[:100]}")
    
    # Summary
    print("\n[4/4] System Ready!")
    print("=" * 60)
    print("  Quick Links:")
    print("  • Dashboard:    http://localhost:5173")
    print("  • Server API:   http://localhost:5002/api")
    print(f"  • Gateway:      http://{gateway_ip}:8090")
    print("  • ML Engine:    http://localhost:5001")
    print("  • Ganache:      http://localhost:7545")
    print("=" * 60)
    print("\n  Press Ctrl+C in each terminal window to stop services.")
    print("  Or close all windows to shutdown.\n")

if __name__ == "__main__":
    main()
