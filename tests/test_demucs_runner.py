import importlib.util
import sys
import tempfile
import unittest
import wave
from array import array
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from demucs_runner import load_track

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
