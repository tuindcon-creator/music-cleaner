"""Local media processing; no upload APIs."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import wave
import shutil
import math
from hardware import detect, summary
from array import array

SUPPORTED = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma",
             ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts"}
class Cancelled(Exception):
    pass

def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def command(args, cancel, log=lambda message: None, env=None):
    """Drain child output to disk to avoid pipe deadlocks and permit cancellation."""
    if cancel.is_set():
        raise Cancelled()
    args = list(args)
    if Path(str(args[0])).name.lower().startswith("ffmpeg"):
        args[1:1] = ["-hide_banner", "-loglevel", "error", "-nostats"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(a) for a in args], stdout=output,
                                   stderr=subprocess.STDOUT, creationflags=flags, env=env)
        try:
            while process.poll() is None:
                if cancel.wait(0.15):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise Cancelled()
            output.seek(0)
            message = output.read().decode("utf-8", errors="replace")
            if process.returncode:
                raise RuntimeError(message[-6000:] or f"Lệnh thất bại: {process.returncode}")
            if message:
                log(message[-1800:])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

def convert(source, target, fmt, cancel, log):
    codec = {"wav": ["-c:a", "pcm_s16le"], "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
             "flac": ["-c:a", "flac"]}[fmt]
    command([ffmpeg(), "-nostdin", "-y", "-i", source, "-map", "0:a:0", "-vn",
             *codec, target], cancel, log)

def read_waveform(source, cancel, log, bins=900):
    # Separate, low-rate file keeps visualization memory bounded.
    with tempfile.TemporaryDirectory(prefix="wave-") as scratch:
        target = Path(scratch) / "preview.wav"
        command([ffmpeg(), "-nostdin", "-y", "-i", source, "-map", "0:a:0",
                 "-vn", "-ac", "1", "-ar", "1000", "-c:a", "pcm_s16le", target], cancel, log)
        with wave.open(str(target), "rb") as audio:
            count, rate = audio.getnframes(), audio.getframerate()
            duration = count / rate
            stride = max(1, (count + bins - 1) // bins)
            peaks = []
            while True:
                if cancel.is_set():
                    raise Cancelled()
                raw = audio.readframes(stride)
                if not raw:
                    break
                samples = array("h", raw)
                if sys.byteorder != "little":
                    samples.byteswap()
                peaks.append(max(abs(n) for n in samples) / 32768)
        return peaks, duration

def recoverable_device_error(error):
    text = str(error).lower()
    return any(s in text for s in ("out of memory", "cuda error", "cuda is not",
        "no nvidia", "not compiled with cuda", "mps backend", "mps device"))

def separate_chunks(decoded, scratch, profile, cancel, phase, log):
    """Bound Demucs' full-file loading to short pieces, then stream the stems."""
    with wave.open(str(decoded), "rb") as source:
        duration = source.getnframes() / source.getframerate()
    if duration <= 0:
        raise RuntimeError("File không có mẫu âm thanh.")
    chunks = max(1, math.ceil(duration / profile.chunk_seconds))
    input_path = scratch / "chunk.wav"
    stems = scratch / "stems" / "htdemucs" / "chunk"
    destinations = [scratch / "vocals.wav", scratch / "no_vocals.wav"]
    writers = [wave.open(str(path), "wb") for path in destinations]
    for writer in writers:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(44100)
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(profile.cpu_threads)
    env["MKL_NUM_THREADS"] = str(profile.cpu_threads)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        for index in range(chunks):
            phase(f"AI: đoạn {index+1}/{chunks} • {profile.device.upper()}",
                  25 + int(55 * index / chunks))
            command([ffmpeg(), "-nostdin", "-y", "-ss", str(index * profile.chunk_seconds),
                     "-i", decoded, "-t", str(profile.chunk_seconds), "-c:a", "pcm_s16le",
                     input_path], cancel, log)
            def run_model():
                command([sys.executable, Path(__file__).with_name("demucs_runner.py"), "-n", "htdemucs",
                    "--two-stems", "vocals", "--device", profile.device,
                    "--shifts", "1", "--segment", str(profile.segment), "-j", "1",
                    "-o", scratch / "stems", input_path], cancel, log, env=env)
            try:
                run_model()
            except RuntimeError as error:
                if profile.device == "cpu" or not recoverable_device_error(error):
                    raise
                log("GPU không đủ bộ nhớ hoặc không tương thích. Thử lại đoạn này bằng CPU.")
                profile.device, profile.segment = "cpu", 4
                run_model()
            for stem, writer in zip(("vocals", "no_vocals"), writers):
                # Normalize to PCM16 for wave module on every platform.
                pcm = scratch / (stem + "_part.wav")
                command([ffmpeg(), "-nostdin", "-y", "-i", stems / (stem + ".wav"),
                         "-c:a", "pcm_s16le", "-ac", "2", "-ar", "44100", pcm], cancel, log)
                with wave.open(str(pcm), "rb") as part:
                    while True:
                        if cancel.is_set():
                            raise Cancelled()
                        frames = part.readframes(44100)
                        if not frames:
                            break
                        writer.writeframesraw(frames)
    finally:
        for writer in writers:
            writer.close()
    return destinations

def process_file(source, root, mode, fmt, device, cancel, phase, waveform, log):
    source, root = Path(source), Path(root)
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy: {source}")
    root.mkdir(parents=True, exist_ok=True)
    # mkdir is atomic: repeated filenames, batches and concurrent runs never overwrite.
    index = 1
    while True:
        folder = root / (source.stem if index == 1 else f"{source.stem}_{index}")
        try:
            folder.mkdir()
            break
        except FileExistsError:
            index += 1
    try:
        with tempfile.TemporaryDirectory(prefix="music-cleaner-") as scratch:
            scratch = Path(scratch)
            phase("Trích xuất âm thanh", 5)
            decoded = scratch / "input.wav"
            command([ffmpeg(), "-nostdin", "-y", "-i", source, "-map", "0:a:0", "-vn",
                     "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", decoded], cancel, log)
            phase("Vẽ sóng âm", 15)
            peaks, duration = read_waveform(decoded, cancel, log)
            waveform(peaks, duration)
            if mode == "extract":
                phase("Xuất âm thanh", 85)
                result = folder / f"am_thanh.{fmt}"
                convert(decoded, result, fmt, cancel, log)
                outputs = [str(result)]
            else:
                profile = detect(device, probe_gpu=device != "cpu")
                log(summary(profile))
                # Decode/stems/export need disk, even when RAM usage is bounded.
                needed = decoded.stat().st_size * 4 + 128 * 2**20
                if shutil.disk_usage(scratch).free < needed or shutil.disk_usage(root).free < needed:
                    raise RuntimeError("Không đủ dung lượng trống để tách file. Chọn ổ có nhiều chỗ trống hơn.")
                separated = separate_chunks(decoded, scratch, profile, cancel, phase, log)
                phase("Xuất giọng và nhạc nền", 85)
                outputs = []
                for stem_path, name in zip(separated, ("giong", "nhac_nen")):
                    result = folder / f"{name}.{fmt}"
                    convert(stem_path, result, fmt, cancel, log)
                    outputs.append(str(result))
            if cancel.is_set():
                raise Cancelled()
            phase("Hoàn tất", 100)
            return outputs
    except BaseException:
        # This directory belongs to this job alone; remove partial results.
        shutil.rmtree(folder, ignore_errors=True)
        raise

