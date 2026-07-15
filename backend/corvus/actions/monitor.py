"""System monitoring helpers (read-only, safe actions)."""

import shutil
import subprocess
from pathlib import Path


def _ps(command: str) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True, text=True, timeout=20,
    )
    return result.stdout.strip()


def battery() -> dict:
    out = _ps(
        "$b=Get-CimInstance Win32_Battery;"
        "if($b){\"$($b.EstimatedChargeRemaining)|$($b.BatteryStatus)\"}else{'none'}"
    )
    if out == "none" or not out:
        return {"present": False}
    pct, status = (out.split("|") + ["", ""])[:2]
    charging = status.strip() == "2"
    return {"present": True, "percent": int(pct or 0), "charging": charging}


def cpu_percent() -> float:
    out = _ps(
        "(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor "
        "| Where-Object {$_.Name -eq '_Total'}).PercentProcessorTime"
    )
    try:
        return float(out)
    except ValueError:
        return 0.0


def ram() -> dict:
    out = _ps(
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "\"$($os.TotalVisibleMemorySize)|$($os.FreePhysicalMemory)\""
    )
    total_kb, free_kb = (out.split("|") + ["0", "0"])[:2]
    total = int(total_kb or 0) / 1024
    free = int(free_kb or 0) / 1024
    used = total - free
    return {
        "total_mb": round(total),
        "used_mb": round(used),
        "free_mb": round(free),
        "used_percent": round(used / total * 100, 1) if total else 0.0,
    }


def disk(path: str = "C:\\") -> dict:
    usage = shutil.disk_usage(path)
    return {
        "total_gb": round(usage.total / 1e9, 1),
        "free_gb": round(usage.free / 1e9, 1),
        "used_percent": round(usage.used / usage.total * 100, 1),
    }


def gpu_temperature() -> dict:
    """NVIDIA GPUs via nvidia-smi; not all machines have it."""
    if not shutil.which("nvidia-smi"):
        return {"available": False}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        )
        temp, util = (result.stdout.strip().split(",") + ["", ""])[:2]
        return {"available": True, "temp_c": int(temp), "util_percent": int(util)}
    except Exception:
        return {"available": False}
