"""Run the pinned Demucs CLI with direct PCM input, without ffprobe lookup."""
from pathlib import Path

def load_track(track, audio_channels, samplerate):
    import soundfile as sf
    import torch
    from demucs.audio import convert_audio
    path = Path(track)
    if path.suffix.lower() != ".wav":
        raise ValueError("Demucs runner only accepts the application's decoded WAV.")
    samples, rate = sf.read(str(path), dtype="float32", always_2d=True)
    if len(samples) == 0:
        raise ValueError("Decoded WAV contains no audio frames.")
    audio = torch.from_numpy(samples.T.copy())
    return convert_audio(audio, rate, samplerate, audio_channels)

def main():
    from demucs import separate
    # The CLI first tries bare 'ffprobe' on PATH and does not catch PermissionError.
    # All inputs here have already been decoded by the app's bundled FFmpeg.
    separate.load_track = load_track
    separate.main()

if __name__ == "__main__":
    main()
