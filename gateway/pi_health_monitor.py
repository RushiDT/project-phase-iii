"""
Pi Health Monitor – Raspberry Pi Hardware Stats
================================================
Provides system health metrics for the base station.
Integrated into gateway_service.py via the /pi/health endpoint.
Can also run standalone for debugging.
"""

import os
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [PI-HEALTH] - %(message)s")


def get_cpu_temperature():
    """Read CPU temperature from sysfs (Raspberry Pi)."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_raw = f.read().strip()
            return round(int(temp_raw) / 1000.0, 1)
    except FileNotFoundError:
        return None
    except Exception as e:
        logging.warning(f"Could not read CPU temp: {e}")
        return None


def get_pi_model():
    """Detect Raspberry Pi model."""
    try:
        with open("/proc/device-tree/model", "r") as f:
            return f.read().strip().replace("\x00", "")
    except FileNotFoundError:
        return "Non-Pi Platform"
    except Exception:
        return "Unknown"


def get_system_stats():
    """Get RAM, CPU, and disk usage."""
    stats = {}

    try:
        import psutil

        # RAM
        mem = psutil.virtual_memory()
        stats["ram_total_mb"] = round(mem.total / (1024 * 1024))
        stats["ram_used_mb"] = round(mem.used / (1024 * 1024))
        stats["ram_percent"] = mem.percent

        # CPU
        stats["cpu_percent"] = psutil.cpu_percent(interval=0.5)
        stats["cpu_count"] = psutil.cpu_count()

        # Disk
        disk = psutil.disk_usage("/")
        stats["disk_total_gb"] = round(disk.total / (1024 ** 3), 1)
        stats["disk_used_gb"] = round(disk.used / (1024 ** 3), 1)
        stats["disk_percent"] = round(disk.percent, 1)

        # Uptime
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        stats["uptime"] = f"{hours}h {minutes}m {seconds}s"

        # Network
        net = psutil.net_if_addrs()
        for iface, addrs in net.items():
            if iface in ("wlan0", "eth0"):
                for addr in addrs:
                    if addr.family == 2:  # AF_INET (IPv4)
                        stats[f"ip_{iface}"] = addr.address

    except ImportError:
        stats["error"] = "psutil not installed"

    return stats


def get_health_report():
    """
    Build a complete health report.
    Used by gateway_service.py's /pi/health endpoint.
    """
    report = {
        "pi_model": get_pi_model(),
        "cpu_temperature_c": get_cpu_temperature(),
        "timestamp": int(time.time()),
    }

    # System stats
    sys_stats = get_system_stats()
    report.update(sys_stats)

    # Health assessment
    warnings = []
    temp = report.get("cpu_temperature_c")
    threshold = int(os.getenv("TEMP_WARNING_THRESHOLD", "70"))

    if isinstance(temp, (int, float)) and temp > threshold:
        warnings.append(f"CPU temperature high: {temp}°C (threshold: {threshold}°C)")

    disk_pct = report.get("disk_percent")
    if isinstance(disk_pct, (int, float)) and disk_pct > 90:
        warnings.append(f"Disk usage critical: {disk_pct}%")

    ram_pct = report.get("ram_percent")
    if isinstance(ram_pct, (int, float)) and ram_pct > 90:
        warnings.append(f"RAM usage critical: {ram_pct}%")

    report["warnings"] = warnings
    report["status"] = "warning" if warnings else "healthy"

    return report


# ---- Standalone Mode ----
if __name__ == "__main__":
    import json

    print("\n📟 Raspberry Pi Health Report")
    print("=" * 40)

    report = get_health_report()
    print(json.dumps(report, indent=2))

    if report["warnings"]:
        print("\n⚠️  WARNINGS:")
        for w in report["warnings"]:
            print(f"  - {w}")
    else:
        print("\n✅ All systems healthy")
