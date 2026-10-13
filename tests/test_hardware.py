import sys
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hardware import choose_profile, validate_platform
from setup_runtime import cuda_candidate

class HardwareTests(unittest.TestCase):
    def profile(self, **kwargs):
        defaults = dict(system="Windows", architecture="AMD64", threads=32,
                        ram=16, available=10)
        defaults.update(kwargs)
        return choose_profile(**defaults)

    def test_cpu_without_gpu(self):
        self.assertEqual(self.profile().device, "cpu")
        self.assertEqual(self.profile().cpu_threads, 8)

    def test_cuda_requires_working_runtime_and_memory(self):
        self.assertEqual(self.profile(gpu="NVIDIA", vram=8, cuda_works=True).device, "cuda")
        self.assertEqual(self.profile(gpu="NVIDIA", vram=1, cuda_works=True).device, "cpu")
        self.assertEqual(self.profile(gpu="NVIDIA", vram=8, cuda_works=False).device, "cpu")

    def test_low_memory_reduces_chunk_and_segment(self):
        profile = self.profile(available=1.5, vram=3, cuda_works=True)
        self.assertEqual((profile.chunk_seconds, profile.segment), (30, 4))

    def test_explicit_cpu_overrides_gpu(self):
        self.assertEqual(self.profile(vram=8, cuda_works=True, requested="cpu").device, "cpu")

    def test_mps_and_requested_gpu_fallback(self):
        self.assertEqual(self.profile(mps_works=True).device, "mps")
        self.assertEqual(self.profile(requested="cuda").device, "cpu")

    def test_unsupported_architecture_reports_error(self):
        with patch("hardware.struct.calcsize", return_value=4):
            with self.assertRaisesRegex(RuntimeError, "64-bit"):
                validate_platform()

    def test_driver_checks(self):
        with patch("setup_runtime.platform.system", return_value="Windows"):
            with patch("setup_runtime.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "550.54\n", "")):
                self.assertTrue(cuda_candidate())
            with patch("setup_runtime.subprocess.run", side_effect=FileNotFoundError):
                self.assertFalse(cuda_candidate())

if __name__ == "__main__":
    unittest.main()
