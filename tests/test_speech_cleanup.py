import hashlib
import io
import json
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
        self.assertLessEqual(max(lengths), int(30.63 * 48000))
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
            with patch.object(engine, "check_speech_model"), patch.object(engine, "clean_voice", side_effect=fail):
                outputs = engine.process_file(source, self.root / "results", "separate", "wav", "cpu",
                    event, lambda *_: None, lambda *_: None, lambda *_: None, cleanup=12)
        self.assertEqual([Path(p).name for p in outputs], ["giong.wav", "nhac_nen.wav"])
        self.assertTrue(all(Path(p).is_file() for p in outputs))
        self.assertTrue(source.exists())
        self.assertEqual(outputs.state, "cancelled" if cancelled else "partial")
        report = json.loads((Path(outputs[0]).parent / "ket_qua.json").read_text(encoding="utf-8"))
        self.assertEqual(report["missing"], ["giong_loc.wav"])
        self.assertEqual(report["state"], outputs.state)
    def test_optional_failure_keeps_completed_voice(self):
        self.process_optional(RuntimeError("model download failed"))
    def test_optional_cancel_keeps_completed_voice(self):
        self.process_optional(engine.Cancelled(), True)

    def test_frame_quantized_model_handles_fractional_and_short_recordings(self):
        class QuantizedModel:
            def run(self, samples, rate):
                frames = round(len(samples) * 48000 / rate) // 480 * 480
                return SimpleNamespace(samples=np.full(frames, .1, np.float32), sample_rate=48000)
        for rate, duration in [(44100, .001), (44100, 30.001), (44100, 65.013), (22050, .013)]:
            source, target = self.root / "fraction.wav", self.root / "filtered.wav"
            n = round(rate * duration)
            sf.write(source, np.full((n, 2), .1, np.float32), rate, subtype="FLOAT")
            speech.clean(source, target, model_factory=QuantizedModel)
            result = sf.read(target, dtype="float32", always_2d=True)[0]
            self.assertEqual(result.shape, (round(n * 48000 / rate), 2))
            self.assertTrue(np.isfinite(result).all())
            np.testing.assert_allclose(result, .1, atol=1e-6)

    def test_missing_prediction_is_rejected_instead_of_filled_with_silence(self):
        source = self.root / "source.wav"
        sf.write(source, np.zeros((48000, 2), np.float32), 48000)
        class TruncatedModel:
            def run(self, samples, rate):
                return SimpleNamespace(samples=np.zeros(10, np.float32), sample_rate=48000)
        with self.assertRaisesRegex(RuntimeError, "không hợp lệ"):
            speech.clean(source, self.root / "filtered.wav", model_factory=TruncatedModel)

    def test_speech_failure_preserves_before_filter_file_and_reports_missing_output(self):
        source = self.root / "source.wav"
        sf.write(source, np.zeros((44100, 2), np.float32), 44100)
        with patch.object(engine, "check_speech_model", side_effect=RuntimeError("model unavailable")):
            result = engine.process_file(source, self.root / "results", "speech", "wav", "cpu",
                threading.Event(), lambda *_: None, lambda *_: None, lambda *_: None, cleanup=12)
        self.assertEqual(result.state, "partial")
        self.assertEqual([Path(p).name for p in result], ["giong_goc.wav"])
        self.assertTrue(Path(result[0]).is_file())

    def test_failed_model_preflight_does_not_start_expensive_separation(self):
        source = self.root / "source.wav"
        sf.write(source, np.zeros((44100, 2), np.float32), 44100)
        with patch.object(engine, "check_speech_model", side_effect=RuntimeError("model unavailable")), \
             patch.object(engine, "separate_chunks") as separate:
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                engine.process_file(source, self.root / "results", "separate", "wav", "cpu",
                    threading.Event(), lambda *_: None, lambda *_: None, lambda *_: None, cleanup=12)
            separate.assert_not_called()

    def test_filtered_export_is_validated_and_atomically_published(self):
        import shutil
        source = self.root / "source.wav"
        sf.write(source, np.zeros((44100, 2), np.float32), 44100)
        real_command = engine.command
        def stub(args, cancel, log, **kwargs):
            if str(args[1]).endswith("speech_cleanup.py"):
                shutil.copyfile(source, args[args.index("--output") + 1])
            else:
                real_command(args, cancel, log, **kwargs)
        with patch.object(engine, "command", side_effect=stub):
            result = engine.clean_voice(source, self.root, self.root, "wav", 12,
                threading.Event(), lambda *_: None, lambda *_: None)
        self.assertTrue(Path(result).is_file())
        self.assertEqual(sf.info(result).frames, 44100)
        self.assertFalse(list(self.root.glob("*.pending.*")))

    def test_truncated_export_does_not_create_finished_filename(self):
        source = self.root / "source.wav"
        sf.write(source, np.zeros((44100, 2), np.float32), 44100)
        real_command = engine.command
        def stub(args, cancel, log, **kwargs):
            if str(args[1]).endswith("speech_cleanup.py"):
                sf.write(str(args[args.index("--output") + 1]), np.zeros((100, 2), np.float32), 48000)
            else:
                real_command(args, cancel, log, **kwargs)
        with patch.object(engine, "command", side_effect=stub):
            with self.assertRaisesRegex(RuntimeError, "thời lượng"):
                engine.clean_voice(source, self.root, self.root, "wav", 12,
                    threading.Event(), lambda *_: None, lambda *_: None)
        self.assertFalse((self.root / "giong_loc.wav").exists())
        self.assertFalse(list(self.root.glob("*.pending.*")))

    def test_report_does_not_claim_success_if_requested_file_is_missing(self):
        voice = self.root / "giong.wav"
        sf.write(voice, np.zeros((100, 2), np.float32), 44100)
        outputs = engine.ProcessingResult([str(voice)])
        engine.write_report(self.root, outputs, "separate", "wav", 12)
        self.assertEqual(outputs.state, "partial")
        self.assertIn("giong_loc.wav", outputs.warning)
        report = json.loads((self.root / "ket_qua.json").read_text(encoding="utf-8"))
        self.assertEqual(report["missing"], ["nhac_nen.wav", "giong_loc.wav"])
