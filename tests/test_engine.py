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
from hardware import choose_profile


class StubWorker:
    def __init__(self, scratch, cancel, log, env=None):
        self.cancel, self.log, self.env = cancel, log, env
    def run(self, args):
        engine.command([sys.executable, "demucs_runner.py", *args], self.cancel, self.log, self.env)
    def restart(self):
        pass
    def close(self):
        pass


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
        self.worker_patch = patch.object(engine, "ModelWorker", StubWorker)
        self.worker_patch.start()
        self.addCleanup(self.worker_patch.stop)

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
        def stub(args, cancel, log=lambda *a: None, env=None):
            if len(args) > 1 and str(args[1]).endswith("demucs_runner.py"):
                import shutil
                destination = Path(args[args.index("-o")+1]) / "htdemucs" / "chunk"
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
    def test_child_logs_preserve_vietnamese_utf8(self):
        messages = []
        engine.command([sys.executable, "-c", "print('Giọng nói tiếng Việt')"],
                       self.cancel, messages.append)
        self.assertIn("Giọng nói tiếng Việt", "".join(messages))

    def test_final_child_progress_is_read_even_for_short_task(self):
        progress_path = self.root / "progress.json"
        updates = []
        code = "import json,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(json.dumps({'stage':'filtering','fraction':1,'message':'done'}),encoding='utf-8')"
        engine.command([sys.executable, "-c", code, progress_path], self.cancel,
                       progress_path=progress_path, on_progress=updates.append)
        self.assertEqual(updates[-1]["fraction"], 1)
        self.assertEqual(len(updates), 1)

    def test_multi_chunk_merge_and_gpu_failure_retries_on_cpu(self):
        real_command = engine.command
        devices = []
        profile = choose_profile("Windows", "AMD64", 4, 8, 4, vram=4, cuda_works=True)
        profile.chunk_seconds = 0.35
        def stub(args, cancel, log=lambda *a: None, env=None):
            if len(args) > 1 and str(args[1]).endswith("demucs_runner.py"):
                devices.append(args[args.index("--device") + 1])
                if len(devices) == 1:
                    raise RuntimeError("CUDA out of memory")
                import shutil
                dest = Path(args[args.index("-o")+1]) / "htdemucs" / "chunk"
                dest.mkdir(parents=True, exist_ok=True)
                for name in ("vocals", "no_vocals"):
                    shutil.copyfile(args[-1], dest / (name + ".wav"))
            else:
                real_command(args, cancel, log)
        with patch.object(engine, "detect", return_value=profile):
            with patch.object(engine, "command", side_effect=stub):
                results = self.process(mode="separate")
        self.assertEqual(devices, ["cuda", "cpu", "cpu", "cpu"])
        with wave.open(results[0]) as audio:
            self.assertAlmostEqual(audio.getnframes()/audio.getframerate(), 1, delta=0.01)

    def test_model_error_cleans_outputs(self):
        real_command = engine.command
        def stub(args, cancel, log=lambda *a: None, env=None):
            if len(args) > 1 and str(args[1]).endswith("demucs_runner.py"):
                raise RuntimeError("Model download failed")
            real_command(args, cancel, log)
        with patch.object(engine, "command", side_effect=stub):
            with self.assertRaisesRegex(RuntimeError, "download"):
                self.process(mode="separate")
        self.assertFalse(list((self.root / "out").iterdir()))

    def test_thorough_mode_uses_finetuned_stem_directory(self):
        real_command = engine.command
        calls = []
        profile = choose_profile("Windows", "AMD64", 4, 16, 10)
        def stub(args, cancel, log=lambda *a: None, env=None):
            if len(args) > 1 and str(args[1]).endswith("demucs_runner.py"):
                import shutil
                calls.append(args)
                model = args[args.index("-n") + 1]
                dest = Path(args[args.index("-o") + 1]) / model / "chunk"
                dest.mkdir(parents=True, exist_ok=True)
                for name in ("vocals", "no_vocals"):
                    shutil.copyfile(args[-1], dest / (name + ".wav"))
            else:
                real_command(args, cancel, log, env)
        with patch.object(engine, "detect", return_value=profile):
            with patch.object(engine, "command", side_effect=stub):
                outputs = engine.process_file(self.source, self.root / "out", "separate", "wav", "cpu",
                    self.cancel, lambda *_: None, lambda *_: None, lambda *_: None, quality="thorough")
        self.assertEqual(calls[0][calls[0].index("-n") + 1], "htdemucs_ft")
        self.assertEqual(calls[0][calls[0].index("--shifts") + 1], "2")
        self.assertTrue(all(Path(path).is_file() for path in outputs))

if __name__ == "__main__":
    unittest.main()
