import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
import time
import unittest
import wave
from unittest.mock import patch
from array import array
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from app import Window, STYLE
import engine

class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.files = []
        for duration in (1, 2):
            path = self.root / f"mau_{duration}.wav"
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(array("h", [2000, -2000] * (8000 * duration)).tobytes())
            self.files.append(str(path.resolve()))
        self.window = Window()
        self.window.show()
        self.app.processEvents()
    def wait_for(self, condition, timeout=15):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertTrue(condition(), "Qt job did not finish before timeout")
    def tearDown(self):
        window = self.window
        window.cancel_previews()
        if window.worker and window.worker.isRunning():
            window.worker.cancel.set()
            window.worker.wait(10000)
        for worker in list(window.preview_workers):
            worker.wait(10000)
        self.app.processEvents()
        window.close()
        self.assertTrue(window.player.source().isEmpty())
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()
    def test_selected_file_waveform_and_error_remain_consistent(self):
        window = self.window
        window.append_files(self.files)
        self.wait_for(lambda: self.files[1] in window.wave_cache)
        self.assertAlmostEqual(window.waveform.duration, 2, places=2)
        window.table.selectRow(0)
        self.wait_for(lambda: self.files[0] in window.wave_cache)
        self.assertAlmostEqual(window.waveform.duration, 1, places=2)
        window.handle_wave(1, [0.3, 0.4], 2)
        self.assertAlmostEqual(window.waveform.duration, 1, places=2)
        self.assertEqual(window.file_name.text(), "mau_1.wav")
        window.show_error(0, "PermissionError: [WinError 5] Access is denied")
        self.assertTrue(window.log_toggle.isChecked())
        self.assertIn("WinError 5", window.error_message.text())
    def test_extract_batch_from_redesigned_screen(self):
        window = self.window
        window.append_files(self.files)
        window.dest.setText(str(self.root / "results"))
        window.mode.setCurrentIndex(1)
        window.fmt.setCurrentText("FLAC")
        self.assertEqual(window.output_names.text(), "am_thanh.flac")
        self.assertIn("2 file", window.start.text())
        window.run_batch()
        self.wait_for(lambda: not window.worker.isRunning() and window.start.isEnabled())
        self.assertEqual(len(window.outputs), 2)
        self.assertTrue(all(Path(paths[0]).is_file() for paths in window.outputs.values()))
        self.assertIn("2 thành công", window.progress.format())
        self.assertTrue(all(window.table.item(row, 1).text() == "Hoàn tất" for row in range(2)))

    def test_trial_uses_selected_row_and_keeps_full_waveform(self):
        window = self.window
        window.append_files(self.files)
        self.wait_for(lambda: self.files[1] in window.wave_cache)
        window.dest.setText(str(self.root / "trial"))
        window.mode.setCurrentIndex(1)
        window.run_batch(True)
        self.wait_for(lambda: not window.worker.isRunning() and window.start.isEnabled())
        self.assertEqual(set(window.outputs), {1})
        self.assertTrue(Path(window.outputs[1][0]).parent.name.startswith("Thu_30s_"))
        self.assertEqual(window.table.item(0, 1).text(), "Chờ xử lý")
        self.assertAlmostEqual(window.wave_cache[self.files[1]][1], 2, places=2)
        self.assertIn("Thử 30s", window.progress.format())
    def test_speech_mode_exposes_safe_comparison_outputs(self):
        window = self.window
        self.assertEqual(window.cleanup.currentData(), 0)
        window.mode.setCurrentIndex(2)
        self.assertEqual(window.cleanup.currentData(), 12)
        self.assertFalse(window.quality.isEnabled())
        self.assertFalse(window.device.isEnabled())
        self.assertIn("giong_goc", window.output_names.text())
        self.assertIn("giong_loc", window.output_names.text())
        window.mode.setCurrentIndex(1)
        self.assertFalse(window.cleanup.isEnabled())

    def test_missing_filtered_voice_is_not_counted_as_success(self):
        window = self.window
        window.append_files(self.files)
        window.dest.setText(str(self.root / "results"))
        window.cleanup.setCurrentIndex(1)
        def partial(source, *args, **kwargs):
            return engine.ProcessingResult([source], state="partial", warning="Chưa tạo giong_loc.wav: model failed")
        with patch("app.process_file", side_effect=partial), patch("app.detect", return_value=engine.detect("cpu")):
            window.run_batch()
            self.wait_for(lambda: not window.worker.isRunning() and window.start.isEnabled())
        self.assertIn("0 thành công", window.progress.format())
        self.assertIn("2 chưa đủ kết quả", window.progress.format())
        self.assertIn("Thiếu giọng lọc", window.table.item(0, 1).text())
        self.assertTrue(window.error_message.isVisible())
        self.assertTrue(window.log_toggle.isChecked())

    def test_partial_failure_does_not_stop_remaining_batch(self):
        window = self.window
        window.append_files(self.files)
        calls = []
        def process(source, *args, **kwargs):
            calls.append(source)
            return engine.ProcessingResult([source], state="partial" if len(calls) == 1 else "complete", warning="Chưa tạo giong_loc.wav")
        with patch("app.process_file", side_effect=process), patch("app.detect", return_value=engine.detect("cpu")):
            window.run_batch()
            self.wait_for(lambda: not window.worker.isRunning() and window.start.isEnabled())
        self.assertEqual(calls, self.files)
        self.assertIn("1 thành công", window.progress.format())
        self.assertIn("1 chưa đủ kết quả", window.progress.format())

if __name__ == "__main__":
    unittest.main()
