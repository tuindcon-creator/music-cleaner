"""Hardware choices use tested runtime capabilities, not GPU names alone."""
from dataclasses import dataclass, asdict
import json
import os
import platform
import struct

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
    if probe_gpu:
        try:
            import torch
            if torch.cuda.is_available():
                gpu = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_memory / 2**30
                # Some drivers/architectures report availability but fail to allocate.
                value = torch.ones(1, device="cuda") + 1
                cuda = value.item() == 2
                del value
                torch.cuda.empty_cache()
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                value = torch.ones(1, device="mps") + 1
                mps = value.item() == 2
                gpu = "Apple GPU" if mps else ""
                del value
        except Exception:
            cuda = mps = False
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
    validate_platform()
    print(json.dumps(asdict(detect()), ensure_ascii=False, indent=2))
