import os
import sys
import platform
from typing import Dict, Any

def get_memory_usage() -> float:
    """Returns memory usage percentage (0-100)."""
    try:
        if platform.system() == "Windows":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return float(stat.dwMemoryLoad)
        elif platform.system() == "Linux":
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
            mem_info = {}
            for line in lines:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = int(parts[1].split()[0])
                    mem_info[key] = val
            total = mem_info.get('MemTotal', 1)
            free = mem_info.get('MemFree', 0) + mem_info.get('Buffers', 0) + mem_info.get('Cached', 0)
            return round((1 - free / total) * 100, 1)
    except Exception:
        pass
    return 0.0

def get_scrubbed_env() -> Dict[str, str]:
    """Returns os.environ scrubbed of sensitive credentials."""
    from pyerror.formatting import Formatter
    scrubbed = {}
    keys_to_match = Formatter.DEFAULT_SECRETS
    for k, v in os.environ.items():
        k_lower = k.lower()
        if any(secret in k_lower for secret in keys_to_match):
            scrubbed[k] = "********"
        else:
            scrubbed[k] = Formatter.scrub_text(v, keys_to_match)
    return scrubbed

def get_system_info() -> Dict[str, Any]:
    """
    Returns platform, CPU, memory, Python version, and scrubbed environment 
    information for inclusion in error logs.
    """
    return {
        "os_platform": platform.system(),
        "os_release": platform.release(),
        "os_architecture": platform.machine(),
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "cpu_count": os.cpu_count() or 1,
        "memory_usage_percent": get_memory_usage(),
        "environment": get_scrubbed_env()
    }
