import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech_cleanup import ProgressReporter, clean
from windows_file_lock import deny_delete_share

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
    def tearDown(self):
        self.scratch.cleanup()

    def test_permission_denied_on_replace_is_nonfatal_and_next_update_recovers(self):
        path = self.root / "speech_progress.json"
        path.write_text('{"stage":"old"}')
        reporter = ProgressReporter(path)
        with contextlib.redirect_stderr(io.StringIO()) as warnings:
            with patch.object(Path, "replace", side_effect=PermissionError("WinError 5")):
                for i in range(2000):
                    self.assertFalse(reporter("filtering", i / 2000, "processing"))
            self.assertEqual(warnings.getvalue().count("audio processing continues"), 1)
        self.assertEqual(json.loads(path.read_text()), {"stage": "old"})
        self.assertTrue(reporter("filtering", 1., "done"))
        self.assertEqual(json.loads(path.read_text())["fraction"], 1.)
        self.assertFalse(path.with_suffix(".tmp").exists())

    def test_write_and_cleanup_permission_errors_are_also_nonfatal(self):
        reporter = ProgressReporter(self.root / "progress.json")
        with patch.object(Path, "write_text", side_effect=PermissionError("denied")), \
             patch.object(Path, "unlink", side_effect=PermissionError("also denied")), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(reporter("loading", 0., "loading"))

    def test_audio_output_errors_are_not_swallowed(self):
        source = self.root / "input.wav"
        sf.write(source, np.zeros((480, 2), np.float32), 48000)
        class Identity:
            def run(self, audio, rate):
                from types import SimpleNamespace
                return SimpleNamespace(samples=audio, sample_rate=rate)
        with self.assertRaises(sf.LibsndfileError):
            clean(source, self.root / "missing-folder" / "output.wav", model_factory=Identity,
                  progress=ProgressReporter(None))

    @unittest.skipUnless(os.name == "nt", "Requires real Windows handle sharing")
    def test_real_windows_lock_reproduces_old_failure_and_new_reporter_continues(self):
        path = self.root / "speech_progress.json"
        path.write_text('{"stage":"old"}')
        temporary = path.with_suffix(".tmp")
        reporter = ProgressReporter(path)
        with deny_delete_share(path), contextlib.redirect_stderr(io.StringIO()):
            temporary.write_text('{"stage":"new"}')
            with self.assertRaises(PermissionError) as failure:
                temporary.replace(path)  # exact failing operation from the user's traceback
            self.assertIn(failure.exception.winerror, (5, 32))
            for index in range(500):
                self.assertFalse(reporter("filtering", index / 500, "processing"))
        self.assertTrue(reporter("filtering", 1., "done"))
        self.assertEqual(json.loads(path.read_text())["message"], "done")
