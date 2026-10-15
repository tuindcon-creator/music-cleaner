"""Real pretrained Demucs -> DPDFNet -> three verified output files on Windows."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
from hardware import detect
from windows_file_lock import deny_delete_share

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    t = np.arange(round(2.013 * 44100)) / 44100
    samples = (.08 * np.sin(2 * np.pi * 220 * t) + .02 * np.sin(2 * np.pi * 1400 * t)).astype(np.float32)
    source = root / "Original input.wav"
    sf.write(source, np.column_stack([samples, samples * .9]), 44100)
    before = source.read_bytes()
    profile = detect("cpu")
    profile.chunk_seconds = 1  # exercise reuse and joins in the actual child
    updates = []
    messages, locked = [], []
    real_command = engine.command
    def command_with_locked_progress(args, cancel, log=lambda *_: None, **kwargs):
        if os.name == "nt" and "--progress" in args:
            path = Path(args[args.index("--progress") + 1])
            path.write_text('{"stage":"locked","fraction":0,"message":"lock regression"}', encoding="utf-8")
            locked.append(path.name)
            with deny_delete_share(path):
                return real_command(args, cancel, log, **kwargs)
        return real_command(args, cancel, log, **kwargs)
    def log(message):
        messages.append(message)
        print(message, flush=True)
    with patch.object(engine, "detect", return_value=profile), \
         patch.object(engine, "command", side_effect=command_with_locked_progress):
        outputs = engine.process_file(source, root / "results", "separate", "wav", "cpu",
            threading.Event(), lambda *args: updates.append(args), lambda *_: None, log,
            quality="light", cleanup=12)
    assert outputs.state == "complete", outputs.warning
    assert [Path(p).name for p in outputs] == ["giong.wav", "nhac_nen.wav", "giong_loc.wav"]
    for path in outputs:
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
        assert len(audio) > 0 and audio.shape[1] == 2 and np.isfinite(audio).all()
        assert abs(len(audio)/rate - len(t)/44100) < .002
    assert source.read_bytes() == before
    report = json.loads((Path(outputs[0]).parent / "ket_qua.json").read_text(encoding="utf-8"))
    assert report["state"] == "complete" and report["missing"] == []
    assert any("3/3" in message for message, _ in updates)
    if os.name == "nt":
        assert locked == ["model_progress.json", "speech_progress.json"], locked
        assert any("Progress update unavailable; audio processing continues." in message for message in messages)
        print("REAL WINDOWS LOCK REGRESSION OK: preflight and filter progress locked; all audio outputs verified.", flush=True)
    print("REAL FULL PIPELINE OK: cached Demucs, DPDFNet, original preserved, three verified outputs.", flush=True)
    voice = Path(outputs[0])
    voice_before = voice.read_bytes()
    repeated = engine.process_file(voice, root / "results", "reseparate", "wav", "cpu",
        threading.Event(), lambda *_: None, lambda *_: None, print, quality="light")
    assert repeated.state == "complete", repeated.warning
    assert [Path(p).name for p in repeated] == ["giong_truoc_tach_lai.wav", "giong_tach_lai.wav", "nhac_tach_lai.wav"]
    assert voice.read_bytes() == voice_before
    for path in repeated:
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
        assert audio.shape[1] == 2 and np.isfinite(audio).all()
        assert abs(len(audio)/rate - len(t)/44100) < .002
    report = json.loads((Path(repeated[0]).parent / "ket_qua.json").read_text(encoding="utf-8"))
    assert report["mode"] == "reseparate" and report["missing"] == []
    print("REAL RESEPARATION OK: actual vocal output processed through AI again, before copy and new stems validated.", flush=True)
