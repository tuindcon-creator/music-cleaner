"""One cancellable Demucs process per file; reuse loaded weights between chunks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


class ModelWorker:
    def __init__(self, scratch, cancel, log, env=None):
        self.cancel, self.log = cancel, log
        self.reply = Path(scratch) / "demucs_reply.json"
        self.runtime_env = {**os.environ, **(env or {}),
                            "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        self.process = None
        self.output = None
        self.serial = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            if self.process.stdin:
                self.process.stdin.close()
            self.process = None
        if self.output is not None:
            self.output.close()
            self.output = None
        self.reply.unlink(missing_ok=True)
        self.reply.with_suffix(".tmp").unlink(missing_ok=True)

    def restart(self):
        # A CUDA failure may poison its context. Start clean for the CPU retry.
        self.close()

    def _start(self):
        self.output = tempfile.TemporaryFile()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name("demucs_runner.py")),
                 "--worker", str(self.reply)], stdin=subprocess.PIPE,
                stdout=self.output, stderr=subprocess.STDOUT,
                creationflags=flags, env=self.runtime_env)
        except BaseException:
            self.close()
            raise

    def _logs(self):
        self.output.seek(0)
        data = self.output.read().decode("utf-8", errors="replace")
        return data[-6000:]

    def run(self, args):
        from engine import Cancelled
        if self.cancel.is_set():
            raise Cancelled()
        if self.process is None:
            self._start()
        self.serial += 1
        token = self.serial
        self.reply.unlink(missing_ok=True)
        try:
            payload = json.dumps({"id": token, "args": [str(a) for a in args]},
                                 ensure_ascii=True).encode("utf-8") + b"\n"
            self.process.stdin.write(payload)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            if self.cancel.is_set():
                raise Cancelled() from error
            raise RuntimeError(self._logs() or "Tiến trình AI đã dừng.") from error
        while True:
            if self.cancel.is_set():
                self.close()
                raise Cancelled()
            if self.reply.is_file():
                response = json.loads(self.reply.read_text(encoding="utf-8"))
                if response.get("id") == token:
                    self.reply.unlink(missing_ok=True)
                    if not response.get("ok"):
                        raise RuntimeError(response.get("error") or "AI không trả kết quả.")
                    return
            if self.process.poll() is not None:
                raise RuntimeError(self._logs() or f"Tiến trình AI dừng: {self.process.returncode}")
            self.cancel.wait(.05)
