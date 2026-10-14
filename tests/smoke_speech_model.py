"""Real ONNX, full child-process/export path, fractional tails and formats."""
import json
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
    cases = [(44100, 30.001, "wav"), (44100, 65.013, "wav"),
             (44100, .01, "wav"), (22050, 1.013, "flac"),
             (48000, 1.023, "mp3")]
    for rate, duration, fmt in cases:
        source = root / f"synthetic_{rate}_{duration}.wav"
        frames = round(duration * rate)
        samples = (.1 * np.sin(2 * np.pi * 220 * np.arange(frames) / rate)).astype(np.float32)
        sf.write(source, np.column_stack([samples, samples * .8]), rate, subtype="FLOAT")
        updates = []
        outputs = engine.process_file(source, root / "results", "speech", fmt, "cpu",
            threading.Event(), lambda *args: updates.append(args), lambda *_: None, print, cleanup=12)
        assert outputs.state == "complete", outputs.warning
        assert [Path(p).name for p in outputs] == [f"giong_goc.{fmt}", f"giong_loc.{fmt}"]
        for path in outputs:
            audio, exported_rate = sf.read(path, dtype="float32", always_2d=True)
            assert audio.shape[1] == 2 and np.isfinite(audio).all()
            assert abs(len(audio)/exported_rate - frames/rate) < (.1 if fmt == "mp3" else .002)
        report = json.loads((Path(outputs[0]).parent / "ket_qua.json").read_text(encoding="utf-8"))
        assert report["state"] == "complete" and not report["missing"]
        assert any("đoạn" in message for message, _ in updates), updates
        print(f"REAL ONNX EXPORT OK: {rate} Hz, {duration}s, {fmt}", flush=True)
    print("Actual speech model: fractional tails, multichunk inference and WAV/FLAC/MP3 exports OK.")
