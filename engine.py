"""Local media processing; no upload APIs."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import wave
from array import array

SUPPORTED = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma",
             ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts"}
class Cancelled(Exception):
    pass

def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def command(args, cancel, log=lambda message: None):
    """Drain child output to disk to avoid pipe deadlocks and permit cancellation."""
    if cancel.is_set():
        raise Cancelled()
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(a) for a in args], stdout=output,
                                   stderr=subprocess.STDOUT, creationflags=flags)
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
                phase("AI tách giọng / nhạc (lần đầu tải mô hình)", 25)
                # Demucs receives PCM WAV; decoding uses SoundFile with pinned torchaudio.
                command([sys.executable, "-m", "demucs", "-n", "htdemucs",
                         "--two-stems", "vocals", "--device", device,
                         "--shifts", "1", "--segment", "7", "-j", "1",
                         "-o", scratch / "stems", decoded], cancel, log)
                phase("Xuất giọng và nhạc nền", 85)
                stems = scratch / "stems" / "htdemucs" / "input"
                outputs = []
                for stem, name in [("vocals", "giong"), ("no_vocals", "nhac_nen")]:
                    result = folder / f"{name}.{fmt}"
                    convert(stems / f"{stem}.wav", result, fmt, cancel, log)
                    outputs.append(str(result))
            if cancel.is_set():
                raise Cancelled()
            phase("Hoàn tất", 100)
            return outputs
    except BaseException:
        # This directory belongs to this job alone; remove partial results.
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise

