"""Hardware choices use tested runtime capabilities, not GPU names alone."""
from dataclasses import dataclass, asdict
import json
import os
import platform
import struct
import subprocess
import sys
import time
from pathlib import Path

_GPU_CACHE = None
_GPU_CACHE_TIME = 0.

def gpu_capabilities():
    info = dict(gpu="", vram=0., cuda=False, mps=False)
    try:
        import torch
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
            info["vram"] = torch.cuda.get_device_properties(0).total_memory / 2**30
            value = torch.ones(1, device="cuda") + 1
            info["cuda"] = value.item() == 2
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            value = torch.ones(1, device="mps") + 1
            info["mps"] = value.item() == 2
            info["gpu"] = "Apple GPU" if info["mps"] else ""
    except Exception:
        info["cuda"] = info["mps"] = False
    return info

def probe_gpu_subprocess():
    global _GPU_CACHE, _GPU_CACHE_TIME
    if _GPU_CACHE is not None and time.monotonic() - _GPU_CACHE_TIME < 300:
        return _GPU_CACHE.copy()
    info = dict(gpu="", vram=0., cuda=False, mps=False)
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--gpu-probe"],
            capture_output=True, text=True, timeout=30, creationflags=flags)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            info.update(gpu=str(data.get("gpu", "")), vram=float(data.get("vram", 0)),
                        cuda=bool(data.get("cuda")), mps=bool(data.get("mps")))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    _GPU_CACHE, _GPU_CACHE_TIME = info, time.monotonic()
    return info.copy()

@dataclass
class Profile:
    system: str
    architecture: str
    cpu_threads: int
    ram_gb: float
    available_gb: float
    device: str = "cpu"
    gpu: str = ""
    vram_gb: float = 0
    segment: int = 4
    chunk_seconds: int = 30
    reason: str = ""

def choose_profile(system, architecture, threads, ram, available, gpu="", vram=0,
                   cuda_works=False, mps_works=False, requested="auto"):
    device = "cpu"
    reason = "CPU tương thích"
    if requested in ("auto", "cuda") and cuda_works and vram >= 2:
        device, reason = "cuda", "GPU NVIDIA đã kiểm tra CUDA"
    elif requested in ("auto", "mps") and mps_works:
        device, reason = "mps", "Apple GPU đã kiểm tra MPS"
    elif requested not in ("auto", "cpu"):
        reason = "GPU yêu cầu không dùng được; tự chuyển CPU"
    elif gpu and not cuda_works:
        reason = "Có GPU nhưng CUDA chưa dùng được; chạy CPU"
    segment = 7 if device == "cuda" and vram >= 6 and available >= 4 else 4
    chunk = 90 if available >= 8 else 60 if available >= 4 else 30
    return Profile(system, architecture, max(1, min(threads, 8)), ram, available,
                   device, gpu, vram, segment, chunk, reason)

def detect(requested="auto", probe_gpu=True):
    import psutil
    memory = psutil.virtual_memory()
    gpu, vram, cuda, mps = "", 0, False, False
    if probe_gpu and requested != "cpu":
        info = probe_gpu_subprocess()
        gpu, vram, cuda, mps = info["gpu"], info["vram"], info["cuda"], info["mps"]
    return choose_profile(platform.system(), platform.machine(), os.cpu_count() or 1,
                          memory.total / 2**30, memory.available / 2**30,
                          gpu, vram, cuda, mps, requested)

def summary(profile):
    return (f"{profile.system} {profile.architecture} • RAM {profile.ram_gb:.1f} GB "
            f"(trống {profile.available_gb:.1f} GB) • {profile.device.upper()} "
            f"{profile.gpu if profile.device != 'cpu' else ''} • {profile.reason}")

def validate_platform():
    if struct.calcsize("P") != 8:
        raise RuntimeError("Cần Python và hệ điều hành 64-bit.")
    if platform.system() == "Windows" and platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Bộ cài Windows hiện hỗ trợ x64; ARM cần môi trường x64 giả lập.")

if __name__ == "__main__":
    if "--gpu-probe" in sys.argv:
        print(json.dumps(gpu_capabilities()))
    else:
        validate_platform()
        print(json.dumps(asdict(detect()), ensure_ascii=False, indent=2))
