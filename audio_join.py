"""Bounded-memory aligned crossfade; keep AI intermediates in float PCM."""
from pathlib import Path
import numpy as np
import soundfile as sf

class StemJoiner:
    def __init__(self, path, rate=44100, channels=2):
        self.rate, self.channels = rate, channels
        self.writer = sf.SoundFile(str(path), "w", samplerate=rate, channels=channels, subtype="FLOAT")
        self.pending = np.empty((0, channels), dtype=np.float32)
        self.frames = 0
    def write(self, samples):
        self.writer.write(samples)
        self.frames += len(samples)
    def append(self, path, overlap_frames, cancel, cancelled_error):
        with sf.SoundFile(str(path)) as source:
            if source.samplerate != self.rate or source.channels != self.channels:
                raise RuntimeError("Định dạng stem AI không khớp với âm thanh đã giải mã.")
            if len(self.pending):
                head = source.read(len(self.pending), dtype="float32", always_2d=True)
                if len(head) != len(self.pending):
                    raise RuntimeError("Đoạn AI quá ngắn để ghép âm thanh.")
                fade = np.linspace(0, 1, len(head), endpoint=False, dtype=np.float32)[:, None]
                self.write(self.pending * (1 - fade) + head * fade)
            remaining = len(source) - source.tell()
            reserve = min(overlap_frames, remaining)
            body = remaining - reserve
            while body > 0:
                if cancel.is_set():
                    raise cancelled_error()
                samples = source.read(min(body, self.rate), dtype="float32", always_2d=True)
                self.write(samples)
                body -= len(samples)
            self.pending = source.read(reserve, dtype="float32", always_2d=True)
    def finish(self):
        self.write(self.pending)
        self.pending = np.empty((0, self.channels), dtype=np.float32)
        self.writer.close()
    def close(self):
        self.writer.close()

def peak_gain(path, cancel=None, cancelled_error=RuntimeError):
    """One constant gain for the whole recording; no limiter or per-chunk pumping."""
    peak = 0.
    with sf.SoundFile(str(path)) as audio:
        for block in audio.blocks(blocksize=44100, dtype="float32", always_2d=True):
            if cancel is not None and cancel.is_set():
                raise cancelled_error()
            if not np.isfinite(block).all():
                raise RuntimeError("AI tạo ra mẫu âm thanh không hợp lệ.")
            peak = max(peak, float(np.max(np.abs(block))) if block.size else 0.)
    return min(1., .98 / peak) if peak else 1.
