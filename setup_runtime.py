"""Install a machine-appropriate PyTorch build inside the app venv."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def run(args):
    subprocess.run(args, check=True, cwd=ROOT)

def cuda_candidate():
    if platform.system() not in ("Windows", "Linux"):
        return False
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=driver_version",
            "--format=csv,noheader"], capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        version = tuple(int(x) for x in result.stdout.strip().splitlines()[0].split(".")[:2])
        minimum = (527, 41) if os.name == "nt" else (525, 60)
        return result.returncode == 0 and version >= minimum
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return False

def install_torch(cuda):
    index = "cu121" if cuda else "cpu"
    run([sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall",
         "--no-deps", "torch==2.5.1", "torchaudio==2.5.1",
         "--index-url", "https://download.pytorch.org/whl/" + index])

def installed_torch():
    code = ("import torch,torchaudio,json; "
            "ok=torch.__version__.startswith('2.5.1') and torchaudio.__version__.startswith('2.5.1'); "
            "cuda=torch.cuda.is_available(); "
            "cuda=cuda and (torch.ones(1,device='cuda')+1).item()==2; "
            "print(json.dumps(dict(ready=ok,cuda=cuda,cuda_build=torch.version.cuda is not None)))")
    try:
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}

def main():
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("Please run the installer to create .venv first.")
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError("Setup requires Python 3.11 64-bit.")
    from hardware import validate_platform
    validate_platform()
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    existing = installed_torch()
    cuda = cuda_candidate() or existing.get("cuda", False)
    if platform.system() != "Darwin":
        try:
            if existing.get("ready") and existing.get("cuda_build") == cuda and (not cuda or existing.get("cuda")):
                print("Keeping the existing working PyTorch installation.", flush=True)
            else:
                install_torch(cuda)
        except subprocess.CalledProcessError:
            if not cuda:
                raise
            print("CUDA install failed; falling back to CPU.", flush=True)
            install_torch(False)
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    if cuda:
        probe = subprocess.run([sys.executable, "-c",
            "import torch; assert torch.cuda.is_available(); "
            "assert (torch.ones(1,device='cuda')+1).item()==2"], cwd=ROOT)
        if probe.returncode:
            print("CUDA runtime check failed; reinstalling CPU wheels.", flush=True)
            install_torch(False)
    report = subprocess.check_output([sys.executable, "hardware.py"], cwd=ROOT, text=True,
        encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    json.loads(report)
    (ROOT / "system_report.json").write_text(report, encoding="utf-8")
    run([sys.executable, "-m", "pip", "check"])
    print("Setup complete. Open run_windows.bat.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Setup failed:", error, flush=True)
        sys.exit(1)

