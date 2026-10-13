import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from array import array

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "âm thanh mẫu.wav"
        with wave.open(str(self.source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(array("h", [1000, -1000] * 22050).tobytes())
        self.cancel = threading.Event()

    def tearDown(self):
        self.temp.cleanup()

    def process(self, mode="extract", fmt="wav"):
        return engine.process_file(self.source, self.root / "out", mode, fmt, "cpu",
            self.cancel, lambda *args: None, lambda *args: None, lambda *args: None)

    def test_extract_formats_and_unique_directories(self):
        for fmt in ["wav", "mp3", "flac"]:
            outputs = self.process(fmt=fmt)
            self.assertTrue(Path(outputs[0]).is_file())
            self.assertGreater(Path(outputs[0]).stat().st_size, 100)
        self.assertEqual(len(list((self.root / "out").iterdir())), 3)
        with wave.open(str(self.source)) as original:
            self.assertEqual(original.getnframes(), 44100)

    def test_waveform_duration_and_bounds(self):
        peaks, duration = engine.read_waveform(self.source, self.cancel, lambda *args: None)
        self.assertAlmostEqual(duration, 1, places=2)
        self.assertLessEqual(len(peaks), 900)
        self.assertTrue(all(0 <= peak <= 1 for peak in peaks))

    def test_cancel_removes_partial_output(self):
        self.cancel.set()
        with self.assertRaises(engine.Cancelled):
            self.process()
        self.assertFalse(list((self.root / "out").iterdir()))

    def test_no_audio_video_is_rejected(self):
        video = self.root / "silent.mp4"
        engine.command([engine.ffmpeg(), "-nostdin", "-y", "-f", "lavfi", "-i",
            "color=size=64x64:rate=10", "-t", "1", "-an", video], self.cancel)
        self.source = video
        with self.assertRaises(RuntimeError):
            self.process()
        self.assertFalse(list((self.root / "out").iterdir()))

    def test_extract_video_audio(self):
        video = self.root / "video.mp4"
        engine.command([engine.ffmpeg(), "-nostdin", "-y", "-f", "lavfi", "-i",
            "color=size=64x64:rate=10", "-i", self.source, "-t", "1",
            "-c:a", "aac", video], self.cancel)
        self.source = video
        result = self.process()
        with wave.open(result[0]) as output:
            self.assertAlmostEqual(output.getnframes()/output.getframerate(), 1, delta=0.1)

    def test_demucs_orchestration_with_stubbed_model(self):
        real_command = engine.command
        def stub(args, cancel, log=lambda *a: None):
            if len(args) > 2 and args[1:3] == ["-m", "demucs"]:
                import shutil
                destination = Path(args[args.index("-o")+1]) / "htdemucs" / "input"
                destination.mkdir(parents=True)
                for stem in ["vocals", "no_vocals"]:
                    shutil.copyfile(args[-1], destination / (stem + ".wav"))
            else:
                real_command(args, cancel, log)
        with patch.object(engine, "command", side_effect=stub):
            results = self.process(mode="separate")
        self.assertEqual([Path(p).name for p in results], ["giong.wav", "nhac_nen.wav"])
        self.assertTrue(all(Path(p).is_file() for p in results))

    def test_cancel_running_subprocess(self):
        timer = threading.Timer(0.2, self.cancel.set)
        timer.start()
        try:
            with self.assertRaises(engine.Cancelled):
                engine.command([sys.executable, "-c", "import time; time.sleep(30)"], self.cancel)
        finally:
            timer.cancel()

if __name__ == "__main__":
    unittest.main()
