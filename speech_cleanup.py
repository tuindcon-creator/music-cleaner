"""Optional local speech denoising. Preserve the unfiltered voice separately."""
import argparse
import hashlib
from pathlib import Path
import tempfile
import urllib.request
import numpy as np
import soundfile as sf
from audio_join import StemJoiner

MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/speech-enhancement-models/dpdfnet2_48khz_hr.onnx"
MODEL_NAME = "dpdfnet2_48khz_hr.onnx"
MODEL_SHA256 = "0b399f8a58dc4d70d8cd97541f5c39869406145193b957d00a03b66070944928"

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def ensure_model(cache=None):
    directory = Path(cache) if cache else Path.home() / ".cache" / "music-cleaner" / "models"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / MODEL_NAME
    if target.is_file() and digest(target) == MODEL_SHA256:
        return target
    with tempfile.NamedTemporaryFile(dir=directory, suffix=".download", delete=False) as file:
        temporary = Path(file.name)
    try:
        request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "MusicCleaner/1.1"})
        with urllib.request.urlopen(request, timeout=45) as response, temporary.open("wb") as file:
            size = 0
            while True:
                data = response.read(1024 * 1024)
                if not data:
                    break
                size += len(data)
                if size > 32 * 1024 * 1024:
                    raise RuntimeError("Mô hình vượt kích thước dự kiến.")
                file.write(data)
        if digest(temporary) != MODEL_SHA256:
            raise RuntimeError("Mô hình tải về không đúng checksum; chưa sử dụng file này.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target

def clean(source, target, strength=12, threads=2, model_path=None, model_factory=None):
    if strength not in (12, 18):
        raise ValueError("Chỉ hỗ trợ mức 12 hoặc 18 dB.")
    if model_factory is None:
        import sherpa_onnx
        config = sherpa_onnx.OfflineSpeechDenoiserConfig(
            model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
                dpdfnet=sherpa_onnx.OfflineSpeechDenoiserDpdfNetModelConfig(
                    model=str(model_path or ensure_model()), attenuation_limit_db=strength),
                num_threads=max(1, min(threads, 2)), provider="cpu"))
        denoiser = sherpa_onnx.OfflineSpeechDenoiser(config)
    else:
        denoiser = model_factory()
    with sf.SoundFile(str(source)) as audio:
        rate, channels, frames = audio.samplerate, audio.channels, len(audio)
        if not frames:
            raise RuntimeError("Không có mẫu âm thanh để lọc.")
        step = rate * 30
        overlap = rate // 2
        writer = StemJoiner(target, rate=48000, channels=channels)
        try:
            # Keep intermediates under the caller's job directory, so the parent
            # can remove them even when this child is terminated for cancellation.
            with tempfile.TemporaryDirectory(prefix="speech-parts-", dir=Path(target).parent) as scratch:
                part = Path(scratch) / "part.wav"
                for index, offset in enumerate(range(0, frames, step)):
                    start = max(0, offset - (overlap if index else 0))
                    audio.seek(start)
                    data = audio.read(min(step + (overlap if index else 0), frames - start),
                                      dtype="float32", always_2d=True)
                    results = []
                    for channel in range(channels):
                        result = denoiser.run(data[:, channel], rate)
                        if result.sample_rate != 48000:
                            raise RuntimeError("Mô hình lời thoại trả sai tần số mẫu.")
                        samples = np.asarray(result.samples, dtype=np.float32)
                        expected = round(len(data) * 48000 / rate)
                        if abs(len(samples) - expected) > 2 or not np.isfinite(samples).all():
                            raise RuntimeError("Kết quả lọc lời thoại không hợp lệ.")
                        samples = np.pad(samples, (0, max(0, expected - len(samples))))[:expected]
                        results.append(samples)
                    sf.write(str(part), np.column_stack(results), 48000, subtype="FLOAT")
                    writer.append(part, 24000, _NeverCancelled(), RuntimeError)
                    print(f"Lọc lời thoại: đoạn {index+1}", flush=True)
            writer.finish()
        finally:
            writer.close()

class _NeverCancelled:
    def is_set(self):
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--strength", type=int, choices=(12, 18), default=12)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    clean(args.input, args.output, args.strength, args.threads)

if __name__ == "__main__":
    main()
