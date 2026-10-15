import sys
import tempfile
import threading
import unittest
import wave
from array import array
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine

class OutputPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cancel = threading.Event()
    def tearDown(self):
        self.temp.cleanup()
    def test_trailing_dots_and_spaces(self):
        title = "British Intelligence couldn't believe what he found..."
        self.assertEqual(engine.safe_output_name(title + " "), title.rstrip("."))
        self.assertEqual(engine.safe_output_name("BYU coed murder took 25 years to solve..."), "BYU coed murder took 25 years to solve")
    def test_reserved_and_invalid_components(self):
        for name in ("CON", "aux.wav", "LPT1", "com¹"):
            self.assertTrue(engine.safe_output_name(name).startswith("_"))
        self.assertEqual(engine.safe_output_name('a/b\\c:d?e*f|g<h>i"'), "a_b_c_d_e_f_g_h_i_")
        self.assertEqual(engine.safe_output_name("... "), "am_thanh")
    def test_unicode_names_and_long_names(self):
        self.assertEqual(engine.safe_output_name("Anh hùng chỉ"), "Anh hùng chỉ")
        result = engine.safe_output_name("🎵" * 90 + "vietnam", 100)
        self.assertLessEqual(engine.path_units(result), 100)
    def test_normalized_collisions_preserve_existing_results(self):
        first = engine.create_output_folder(self.root, "title...", self.cancel, lambda *_: None)
        marker = first / "existing.txt"
        marker.write_text("keep")
        second = engine.create_output_folder(self.root, "title ", self.cancel, lambda *_: None)
        self.assertNotEqual(first, second)
        self.assertEqual(marker.read_text(), "keep")
        self.assertFalse(first.name.endswith((".", " ")))
    def test_real_ffmpeg_voice_exports_with_reported_title(self):
        source = self.root / "British Intelligence couldn't believe what he found....wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(array("h", [1000, -1000] * 22050).tobytes())
        # Keep actual decode/export and directory creation; inference is unrelated
        # to the reported failure, which happened after separation succeeded.
        with patch.object(engine, "separate_chunks", side_effect=lambda decoded, *args: [decoded, decoded]):
            outputs = engine.process_file(source, self.root / "results", "separate", "wav", "cpu",
                self.cancel, lambda *_: None, lambda *_: None, lambda *_: None)
        self.assertEqual([Path(p).name for p in outputs], ["giong.wav", "nhac_nen.wav"])
        self.assertFalse(Path(outputs[0]).parent.name.endswith("."))
        self.assertTrue(source.is_file())
        for path in outputs:
            with wave.open(path, "rb") as audio:
                self.assertEqual(audio.getnframes(), 44100)
    def test_write_denial_fails_before_decode_or_ai(self):
        source = self.root / "input.wav"
        source.write_bytes(b"source preserved")
        with patch("pathlib.Path.open", side_effect=PermissionError("write denied")):
            with patch.object(engine, "command") as command:
                with self.assertRaisesRegex(RuntimeError, "Không ghi được"):
                    engine.process_file(source, self.root / "results", "separate", "wav", "cpu",
                        self.cancel, lambda *_: None, lambda *_: None, lambda *_: None)
                command.assert_not_called()
        self.assertEqual(source.read_bytes(), b"source preserved")
        self.assertFalse(list((self.root / "results").iterdir()))
    def test_overlong_destination_is_rejected_before_creation(self):
        target = self.root / ("long-" * 50)
        with self.assertRaisesRegex(RuntimeError, "quá dài"):
            engine.create_output_folder(target, "title", self.cancel, lambda *_: None)
        self.assertFalse(target.exists())

if __name__ == "__main__":
    unittest.main()
