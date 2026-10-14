import sys
import tempfile
import threading
import unittest
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hardware import choose_profile
from processing_modes import configure
from audio_join import StemJoiner, peak_gain
import engine

class ModeTests(unittest.TestCase):
    def profile(self, device=True, available=16):
        return choose_profile("Windows", "AMD64", 16, 64, available,
                              vram=12 if device else 0, cuda_works=device)
    def test_auto_cpu_is_light_and_gpu_is_balanced(self):
        self.assertEqual(configure(self.profile(False), "auto")[1].key, "light")
        self.assertEqual(configure(self.profile(), "auto")[1].key, "balanced")
    def test_light_limits_resources_without_mutating_detected_profile(self):
        profile = self.profile()
        tuned, settings = configure(profile, "light")
        self.assertLessEqual(tuned.cpu_threads, 2)
        self.assertLessEqual(tuned.chunk_seconds, 30)
        self.assertLessEqual(tuned.segment, 4)
        self.assertEqual(settings.shifts, 0)
        self.assertEqual(profile.cpu_threads, 8)
    def test_natural_and_thorough_use_finetuned_model(self):
        for key, shifts in (("natural", 1), ("thorough", 2)):
            settings = configure(self.profile(), key)[1]
            self.assertEqual(settings.model, "htdemucs_ft")
            self.assertEqual(settings.shifts, shifts)
    def test_insufficient_ram_reports_downgrade(self):
        _, settings = configure(self.profile(available=1.5), "thorough")
        self.assertEqual(settings.model, "htdemucs")
        self.assertTrue(settings.fallback_reason)

class JoinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def join(self, first, second, overlap):
        a, b, result = [self.root / name for name in ("a.wav", "b.wav", "result.wav")]
        sf.write(a, first, 44100, subtype="FLOAT")
        sf.write(b, second, 44100, subtype="FLOAT")
        writer = StemJoiner(result)
        try:
            for path in (a, b):
                writer.append(path, overlap, threading.Event(), engine.Cancelled)
            writer.finish()
        finally:
            writer.close()
        return sf.read(result, dtype="float32")[0]
    def test_aligned_join_preserves_samples_and_length(self):
        samples = np.sin(np.arange(5000, dtype=np.float32) * .03)[:, None] * np.array([[.2, .3]], dtype=np.float32)
        result = self.join(samples[:3000], samples[2800:], 200)
        self.assertEqual(len(result), 5000)
        np.testing.assert_allclose(result, samples, atol=1e-6)
    def test_different_estimates_join_without_abrupt_step(self):
        result = self.join(np.ones((1000, 2), dtype=np.float32),
                           -np.ones((1000, 2), dtype=np.float32), 200)
        self.assertLessEqual(np.max(np.abs(np.diff(result[:, 0]))), .011)
    def test_one_global_gain_avoids_clipping_and_preserves_dynamics(self):
        source, target = self.root / "float.wav", self.root / "export.wav"
        samples = np.tile(np.array([[.2, .2], [2., 2.]], dtype=np.float32), (500, 1))
        sf.write(source, samples, 44100, subtype="FLOAT")
        gain = peak_gain(source)
        self.assertAlmostEqual(gain, .49)
        engine.convert(source, target, "wav", threading.Event(), lambda *_: None, gain)
        result = sf.read(target, dtype="float32")[0]
        self.assertLessEqual(np.max(np.abs(result)), .9801)
        self.assertAlmostEqual(result[0, 0] / result[1, 0], .1, places=3)
    def test_nonfinite_model_audio_is_rejected(self):
        source = self.root / "invalid.wav"
        sf.write(source, np.array([[np.nan, 0]], dtype=np.float32), 44100, subtype="FLOAT")
        with self.assertRaisesRegex(RuntimeError, "không hợp lệ"):
            peak_gain(source)
    def test_peak_scan_can_be_cancelled(self):
        source = self.root / "cancel.wav"
        sf.write(source, np.zeros((1000, 2), dtype=np.float32), 44100, subtype="FLOAT")
        event = threading.Event()
        event.set()
        with self.assertRaises(engine.Cancelled):
            peak_gain(source, event, engine.Cancelled)
