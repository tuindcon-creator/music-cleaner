import hashlib
import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import speech_cleanup as speech
import engine

class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_bounded_chunks_preserve_stereo_length_and_overlap(self):
        source, target = self.root / "source.wav", self.root / "filtered.wav"
        data = np.sin(np.arange(48000 * 31 + 12000, dtype=np.float32)[:, None] * .01) * np.array([[.2, .3]], dtype=np.float32)
        sf.write(source, data, 48000, subtype="FLOAT")
        lengths = []
        class IdentityModel:
            def run(self, samples, rate):
                lengths.append(len(samples))
                return SimpleNamespace(samples=samples.copy(), sample_rate=48000)
        speech.clean(source, target, model_factory=IdentityModel)
        result, rate = sf.read(target, dtype="float32", always_2d=True)
        self.assertEqual(rate, 48000)
        self.assertLessEqual(max(lengths), int(30.5 * 48000))
        self.assertEqual(result.shape, data.shape)
        np.testing.assert_allclose(result, data, atol=1e-6)
    def test_verified_cache_does_not_download(self):
        model = self.root / speech.MODEL_NAME
        model.write_bytes(b"verified model")
        with patch.object(speech, "MODEL_SHA256", hashlib.sha256(model.read_bytes()).hexdigest()):
            with patch("speech_cleanup.urllib.request.urlopen") as download:
                self.assertEqual(speech.ensure_model(self.root), model)
                download.assert_not_called()
    def test_bad_download_is_never_activated(self):
        with patch.object(speech, "MODEL_SHA256", hashlib.sha256(b"valid").hexdigest()):
            with patch("speech_cleanup.urllib.request.urlopen", return_value=io.BytesIO(b"wrong")):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    speech.ensure_model(self.root)
        self.assertFalse((self.root / speech.MODEL_NAME).exists())
        self.assertFalse(list(self.root.glob("*.download")))
    def test_invalid_samples_are_rejected(self):
        source = self.root / "source.wav"
        sf.write(source, np.zeros((48000, 2), np.float32), 48000)
        class BadModel:
            def run(self, samples, rate):
                return SimpleNamespace(samples=np.full_like(samples, np.nan), sample_rate=48000)
        with self.assertRaisesRegex(RuntimeError, "không hợp lệ"):
            speech.clean(source, self.root / "bad.wav", model_factory=BadModel)
    def process_optional(self, error, cancelled=False):
        source = self.root / "voice.wav"
        sf.write(source, np.zeros((44100, 2), np.float32), 44100)
        event = threading.Event()
        def fail(*args, **kwargs):
            if cancelled:
                event.set()
            raise error
        with patch.object(engine, "separate_chunks", side_effect=lambda decoded, *a: [decoded, decoded]):
            with patch.object(engine, "clean_voice", side_effect=fail):
                outputs = engine.process_file(source, self.root / "results", "separate", "wav", "cpu",
                    event, lambda *_: None, lambda *_: None, lambda *_: None, cleanup=12)
        self.assertEqual([Path(p).name for p in outputs], ["giong.wav", "nhac_nen.wav"])
        self.assertTrue(all(Path(p).is_file() for p in outputs))
        self.assertTrue(source.exists())
    def test_optional_failure_keeps_completed_voice(self):
        self.process_optional(RuntimeError("model download failed"))
    def test_optional_cancel_keeps_completed_voice(self):
        self.process_optional(engine.Cancelled(), True)
