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
import re
import unicodedata
from hardware import detect, summary
from processing_modes import configure
from array import array

SUPPORTED = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma",
             ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts"}
class Cancelled(Exception):
    pass

def path_units(text):
    return len(str(text).encode("utf-16-le")) // 2

def safe_output_name(stem, max_units=100):
    """Portable directory component; keep original media names untouched."""
    name = unicodedata.normalize("NFC", str(stem))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip(" .")
    reserved = {"CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$"}
    reserved.update(f"{prefix}{number}" for prefix in ("COM", "LPT")
                    for number in ("1", "2", "3", "4", "5", "6", "7", "8", "9", "¹", "²", "³"))
    if name.split(".")[0].upper() in reserved:
        name = "_" + name
    trimmed = ""
    for character in name:
        if path_units(trimmed + character) > max_units:
            break
        trimmed += character
    return trimmed.rstrip(" .") or "am_thanh"

def create_output_folder(root, stem, cancel, log):
    root = Path(root).expanduser().resolve()
    # Leave space for suffixes and the longest result filename, without a
    # registry change or the extended-path syntax unsupported by some tools.
    budget = min(100, 240 - path_units(root) - 2 - len("nhac_nen.flac") - 12)
    if budget < 8:
        raise RuntimeError("Đường dẫn thư mục xuất quá dài. Chọn thư mục ngắn hơn, ví dụ D:\\MusicOutput.")
    name = safe_output_name(stem, budget)
    if name != stem:
        log(f"Đã chuẩn hóa tên thư mục xuất: {name}")
    root.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        if cancel.is_set():
            raise Cancelled()
        folder = root / (name if index == 1 else f"{name}_{index}")
        try:
            folder.mkdir()
            break
        except FileExistsError:
            index += 1
    try:
        probe = folder / ".write-check"
        with probe.open("xb") as stream:
            stream.write(b"Music Cleaner output check")
        probe.unlink()
    except OSError as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise RuntimeError(f"Không ghi được vào thư mục xuất: {folder}. Chọn thư mục khác. {error}") from error
    return folder

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
    runtime_env = {**os.environ, **(env or {}), "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen([str(a) for a in args], stdout=output,
                                   stderr=subprocess.STDOUT, creationflags=flags, env=runtime_env)
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

def convert(source, target, fmt, cancel, log, gain=1.):
    codec = {"wav": ["-c:a", "pcm_s16le"], "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
             "flac": ["-c:a", "flac"]}[fmt]
    volume = ["-af", f"volume={gain:.12g}"] if gain < 1 else []
    command([ffmpeg(), "-nostdin", "-y", "-i", source, "-map", "0:a:0", "-vn", *volume,
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

def separate_chunks(decoded, scratch, profile, cancel, phase, log, settings=None):
    """Bound Demucs' full-file loading to short pieces, then stream the stems."""
    with wave.open(str(decoded), "rb") as source:
        duration = source.getnframes() / source.getframerate()
    if duration <= 0:
        raise RuntimeError("File không có mẫu âm thanh.")
    if settings is None:
        profile, settings = configure(profile, "balanced")
    chunks = max(1, math.ceil(duration / profile.chunk_seconds))
    from audio_join import StemJoiner
    overlap = min(settings.join_seconds, profile.chunk_seconds / 4)
    overlap_frames = round(overlap * 44100)
    input_path = scratch / "chunk.wav"
    stems = scratch / "stems" / settings.model / "chunk"
    destinations = [scratch / "vocals.wav", scratch / "no_vocals.wav"]
    writers = [StemJoiner(path) for path in destinations]
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = str(profile.cpu_threads)
    env["MKL_NUM_THREADS"] = str(profile.cpu_threads)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        for index in range(chunks):
            phase(f"AI: đoạn {index+1}/{chunks} • {profile.device.upper()}",
                  25 + int(55 * index / chunks))
            start = max(0, index * profile.chunk_seconds - (overlap if index else 0))
            length = profile.chunk_seconds + (overlap if index else 0)
            command([ffmpeg(), "-nostdin", "-y", "-ss", str(start),
                     "-i", decoded, "-t", str(length), "-c:a", "pcm_s16le",
                     input_path], cancel, log)
            def run_model():
                command([sys.executable, Path(__file__).with_name("demucs_runner.py"), "-n", settings.model,
                    "--two-stems", "vocals", "--device", profile.device,
                    "--shifts", str(settings.shifts), "--overlap", str(settings.overlap),
                    "--segment", str(profile.segment), "-j", "1",
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
                writer.append(stems / (stem + ".wav"), overlap_frames, cancel, Cancelled)
        for writer in writers:
            writer.finish()
    finally:
        for writer in writers:
            writer.close()
    return destinations

def process_file(source, root, mode, fmt, device, cancel, phase, waveform, log,
                 quality="balanced", preview_seconds=None, preview_start=0, cleanup=0):
    if cleanup not in (0, 12, 18):
        raise ValueError("Mức lọc lời thoại không hợp lệ.")
    source, root = Path(source), Path(root).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy: {source}")
    folder = create_output_folder(root, ("Thu_30s_" if preview_seconds else "") + source.stem, cancel, log)
    log(f"Thư mục kết quả: {folder}")
    try:
        with tempfile.TemporaryDirectory(prefix="music-cleaner-") as scratch:
            final_status = "Hoàn tất"
            scratch = Path(scratch)
            phase("Trích xuất âm thanh", 5)
            decoded = scratch / "input.wav"
            position = ["-ss", str(max(0, preview_start))] if preview_seconds else []
            limit = ["-t", str(preview_seconds)] if preview_seconds else []
            command([ffmpeg(), "-nostdin", "-y", *position, "-i", source, *limit, "-map", "0:a:0", "-vn",
                     "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", decoded], cancel, log)
            phase("Vẽ sóng âm", 15)
            peaks, duration = read_waveform(decoded, cancel, log)
            waveform(peaks, duration)
            if mode == "extract":
                phase("Xuất âm thanh", 85)
                result = folder / f"am_thanh.{fmt}"
                convert(decoded, result, fmt, cancel, log)
                outputs = [str(result)]
            elif mode == "speech":
                from audio_join import peak_gain
                result = folder / f"giong_goc.{fmt}"
                convert(decoded, result, fmt, cancel, log)
                outputs = [str(result)]
                try:
                    outputs.append(clean_voice(decoded, scratch, folder, fmt, cleanup or 12, cancel, phase, log))
                except Cancelled:
                    (folder / f"giong_loc.{fmt}").unlink(missing_ok=True)
                    log("Đã dừng lọc bổ sung; giữ bản giọng trước lọc.")
                    phase("Giữ bản trước lọc; đã dừng", 100)
                    return outputs
            else:
                profile = detect(device, probe_gpu=device != "cpu")
                profile, settings = configure(profile, quality)
                log(summary(profile))
                log(f"Chế độ: {settings.label} • {settings.model} • {settings.shifts} lượt tăng cường • {profile.cpu_threads} luồng")
                if settings.fallback_reason:
                    log(settings.fallback_reason)
                # Decode/stems/export need disk, even when RAM usage is bounded.
                reserve = (512 if settings.model == "htdemucs_ft" else 128) * 2**20
                needed = decoded.stat().st_size * 6 + reserve
                if shutil.disk_usage(scratch).free < needed or shutil.disk_usage(root).free < needed:
                    raise RuntimeError("Không đủ dung lượng trống để tách file. Chọn ổ có nhiều chỗ trống hơn.")
                separated = separate_chunks(decoded, scratch, profile, cancel, phase, log, settings)
                phase("Xuất giọng và nhạc nền", 85)
                outputs = []
                for stem_path, name in zip(separated, ("giong", "nhac_nen")):
                    result = folder / f"{name}.{fmt}"
                    from audio_join import peak_gain
                    gain = peak_gain(stem_path, cancel, Cancelled)
                    if gain < 1:
                        log(f"Giảm mức âm toàn file {name} để tránh clipping (gain={gain:.3f}).")
                    convert(stem_path, result, fmt, cancel, log, gain=gain)
                    outputs.append(str(result))
                if cleanup:
                    try:
                        outputs.append(clean_voice(separated[0], scratch, folder, fmt,
                                                   cleanup, cancel, phase, log))
                    except Cancelled:
                        (folder / f"giong_loc.{fmt}").unlink(missing_ok=True)
                        log("Đã dừng lọc bổ sung; giữ kết quả tách giọng và nhạc nền.")
                        phase("Đã tách; đã dừng lọc", 100)
                        return outputs
                    except Exception as error:
                        # Separation is already complete. Preserve usable unfiltered
                        # results if optional model download/denoising fails.
                        (folder / f"giong_loc.{fmt}").unlink(missing_ok=True)
                        log(f"Lọc bổ sung chưa hoàn tất: {error}. Đã giữ giọng và nhạc nền trước lọc.")
                        final_status = "Đã tách; lọc bổ sung lỗi"
            if cancel.is_set():
                raise Cancelled()
            phase(final_status, 100)
            return outputs
    except BaseException:
        # This directory belongs to this job alone; remove partial results.
        shutil.rmtree(folder, ignore_errors=True)
        raise

def clean_voice(source, scratch, folder, fmt, strength, cancel, phase, log):
    from audio_join import peak_gain
    phase("Lọc lời thoại bổ sung trên CPU (lần đầu tải mô hình)", 90)
    filtered = scratch / "speech_filtered.wav"
    command([sys.executable, Path(__file__).with_name("speech_cleanup.py"),
             "--input", source, "--output", filtered, "--strength", strength,
             "--threads", "2"], cancel, log)
    result = folder / f"giong_loc.{fmt}"
    convert(filtered, result, fmt, cancel, log, gain=peak_gain(filtered, cancel, Cancelled))
    return str(result)

