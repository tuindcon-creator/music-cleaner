"""Real ONNX inference on synthetic audio only; no user media is uploaded."""
import sys
import tempfile
import threading
from pathlib import Path
import numpy as np
import soundfile as sf
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / "synthetic.wav"
    samples = (.1 * np.sin(2 * np.pi * 220 * np.arange(48000) / 48000)).astype(np.float32)
    sf.write(source, np.column_stack([samples, samples]), 48000)
    outputs = engine.process_file(source, root / "results", "speech", "wav", "cpu",
        threading.Event(), lambda *args: print(args, flush=True), lambda *_: None, print, cleanup=12)
    assert [Path(p).name for p in outputs] == ["giong_goc.wav", "giong_loc.wav"]
    for path in outputs:
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
        assert audio.shape[1] == 2 and np.isfinite(audio).all()
        assert abs(len(audio)/rate - 1) < .01
    print("Actual speech model: load, inference, stereo duration and export OK.")
