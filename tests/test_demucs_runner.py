import importlib.util
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demucs_runner import load_track, save_float_audio

@unittest.skipUnless(importlib.util.find_spec("torch") and importlib.util.find_spec("demucs"),
                     "Requires installed Demucs/PyTorch; exercised by Windows CI")
class DirectInputTests(unittest.TestCase):
    def test_load_wav_when_ffprobe_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "âm thanh.wav"
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(22050)
                audio.writeframes(array("h", [1000, -1000] * 11025).tobytes())
            with patch("demucs.audio._read_info", side_effect=PermissionError("WinError 5: ffprobe denied")) as probe:
                result = load_track(path, 2, 44100)
            probe.assert_not_called()
            self.assertEqual(tuple(result.shape), (2, 44100))
            self.assertTrue(result.isfinite().all().item())
    def test_intermediate_preserves_peaks_without_chunk_rescaling(self):
        import torch
        import soundfile as sf
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stem.wav"
            original = torch.tensor([[.2, 1.5, -.4], [.3, 1.8, -.5]])
            save_float_audio(original, path, 44100)
            samples, _ = sf.read(path, dtype="float32")
            self.assertEqual(sf.info(path).subtype, "FLOAT")
            torch.testing.assert_close(torch.from_numpy(samples.T.copy()), original)

    def test_cached_worker_matches_original_cli_audio(self):
        import io
        import json
        import random
        import torch
        from demucs import separate
        from demucs.apply import BagOfModels
        from demucs_runner import serve

        class TinyModel(torch.nn.Module):
            sources = ["drums", "bass", "other", "vocals"]
            samplerate = 44100
            audio_channels = 2
            segment = 1
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.tensor(.25))
            def forward(self, audio):
                return audio[:, None].repeat(1, 4, 1, 1) * self.weight

        loads = []
        def loader(_):
            loads.append(1)
            return BagOfModels([TinyModel(), TinyModel()])
        saved = []
        def save(audio, path, **_):
            saved.append(audio.clone())
        original_main = separate.main
        def deterministic_main(args):
            random.seed(123)
            original_main(args)
        with tempfile.TemporaryDirectory() as scratch:
            scratch = Path(scratch)
            track = scratch / "audio.wav"
            with wave.open(str(track), "wb") as audio:
                audio.setnchannels(2)
                audio.setsampwidth(2)
                audio.setframerate(44100)
                audio.writeframes(array("h", [1000, -700, -1000, 700] * 2205).tobytes())
            opts = ["-n", "htdemucs", "--two-stems", "vocals", "--device", "cpu",
                    "--shifts", "2", "--overlap", ".5", "--segment", "1",
                    "-o", str(scratch / "stems"), str(track)]
            with patch.object(separate, "get_model_from_args", side_effect=loader), \
                 patch.object(separate, "load_track", side_effect=load_track), \
                 patch.object(separate, "save_audio", side_effect=save), \
                 patch.object(separate, "main", side_effect=deterministic_main):
                deterministic_main(opts)
                deterministic_main(opts)
                expected = saved[:]
                saved.clear()
                self.assertEqual(len(loads), 2)
                loads.clear()
                requests = "".join(json.dumps({"id": i, "args": opts}) + "\n" for i in (1, 2))
                with patch("sys.stdin", io.StringIO(requests)):
                    serve(scratch / "reply.json", separate)
                self.assertEqual(len(loads), 1)
                self.assertTrue(json.loads((scratch / "reply.json").read_text())["ok"])
            self.assertEqual(len(saved), len(expected))
            for actual, before in zip(saved, expected):
                torch.testing.assert_close(actual, before, rtol=0, atol=0)
