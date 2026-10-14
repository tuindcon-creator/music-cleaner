"""Real pretrained Demucs -> DPDFNet -> three verified output files on Windows."""
import json
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
    with patch.object(engine, "detect", return_value=profile):
        outputs = engine.process_file(source, root / "results", "separate", "wav", "cpu",
            threading.Event(), lambda *args: updates.append(args), lambda *_: None, print,
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
    print("REAL FULL PIPELINE OK: cached Demucs, DPDFNet, original preserved, three verified outputs.", flush=True)
