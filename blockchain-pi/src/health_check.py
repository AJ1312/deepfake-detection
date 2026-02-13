"""
Health Monitor for Raspberry Pi Node.

Checks CPU, memory, disk, temperature, and service status.
"""

import logging
import os
import time
from typing import Dict

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Monitors Pi node system health.
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.cpu_warn = config.get("cpu_warning_threshold", 85)
        self.mem_warn = config.get("memory_warning_threshold", 80)
        self.disk_warn = config.get("disk_warning_threshold", 90)
        self.temp_warn = config.get("temperature_warning_celsius", 70)

    def check(self) -> Dict:
        """Run all health checks and return status."""
        try:
            import psutil
        except ImportError:
            return {"status": "unknown", "error": "psutil not installed"}

        checks = {}
        warnings = []

        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        checks["cpu_percent"] = cpu_percent
        if cpu_percent > self.cpu_warn:
            warnings.append(f"CPU high: {cpu_percent}%")

        # Memory
        mem = psutil.virtual_memory()
        checks["memory_percent"] = mem.percent
        checks["memory_available_mb"] = round(mem.available / (1024 * 1024))
        if mem.percent > self.mem_warn:
            warnings.append(f"Memory high: {mem.percent}%")

        # Disk
        disk = psutil.disk_usage("/")
        checks["disk_percent"] = disk.percent
        checks["disk_free_gb"] = round(disk.free / (1024 * 1024 * 1024), 1)
        if disk.percent > self.disk_warn:
            warnings.append(f"Disk usage high: {disk.percent}%")

        # Temperature (Pi-specific)
        temp = self._get_cpu_temperature()
        if temp is not None:
            checks["cpu_temperature_c"] = temp
            if temp > self.temp_warn:
                warnings.append(f"Temperature high: {temp}°C")

        # Uptime
        checks["uptime_seconds"] = int(time.time() - psutil.boot_time())

        # Network
        net = psutil.net_io_counters()
        checks["network_bytes_sent"] = net.bytes_sent
        checks["network_bytes_recv"] = net.bytes_recv

        # Status
        checks["status"] = "degraded" if warnings else "healthy"
        checks["warnings"] = warnings

        return checks

    @staticmethod
    def _get_cpu_temperature() -> float:
        """Read CPU temperature (Raspberry Pi)."""
        try:
            # Try psutil first
            import psutil
            temps = psutil.sensors_temperatures()
            if "cpu_thermal" in temps:
                return temps["cpu_thermal"][0].current
            if "cpu-thermal" in temps:
                return temps["cpu-thermal"][0].current
        except Exception:
            pass

        # Fallback: read from Pi thermal zone
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return int(f.read().strip()) / 1000.0
        except (FileNotFoundError, ValueError):
            pass

        return None
