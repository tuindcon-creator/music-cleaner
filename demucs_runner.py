"""Run the pinned Demucs CLI with direct PCM input, without ffprobe lookup."""
from pathlib import Path
import json
import sys
import traceback

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

def serve(reply, separate_module=None):
    """Reuse the exact pinned CLI pipeline and one cached model in this child."""
    if separate_module is None:
        from demucs import separate as separate_module
    original_loader = separate_module.get_model_from_args
    cached = {}
    def cached_loader(args):
        key = (args.name, str(args.repo))
        if key not in cached:
            cached[key] = original_loader(args)
        return cached[key]
    separate_module.get_model_from_args = cached_loader
    temporary = Path(reply).with_suffix(".tmp")
    try:
        for line in sys.stdin:
            request = json.loads(line)
            try:
                separate_module.main(request["args"])
                response = {"id": request["id"], "ok": True}
            except (Exception, SystemExit):
                response = {"id": request["id"], "ok": False,
                            "error": traceback.format_exc()[-6000:]}
            temporary.write_text(json.dumps(response), encoding="utf-8")
            temporary.replace(reply)
    finally:
        separate_module.get_model_from_args = original_loader


def main():
    from demucs import separate
    # WAV is decoded by the app. Do not invoke bare ffprobe on Windows PATH.
    separate.load_track = load_track
    separate.save_audio = save_float_audio
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        serve(Path(sys.argv[2]), separate)
    else:
        separate.main()

def save_float_audio(audio, path, samplerate=44100, **kwargs):
    import soundfile as sf
    target = Path(path)
    if target.suffix.lower() != ".wav":
        raise ValueError("The app uses WAV intermediates only.")
    # No separate gain rescaling for each piece: preserve levels across joins.
    sf.write(str(target), audio.detach().cpu().float().numpy().T, samplerate, subtype="FLOAT")

if __name__ == "__main__":
    main()
