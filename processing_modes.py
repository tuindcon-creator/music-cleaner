"""Separation choices only; no EQ, gates or destructive speech cleanup."""
from dataclasses import dataclass, replace

MODES = {
    "auto": ("Tự động", "Cân bằng trên GPU; Nhẹ trên CPU. Giọng gốc luôn có thể nghe đối chiếu."),
    "light": ("Nhẹ", "Ít tài nguyên, chạy nhanh hơn; có thể còn nhạc nền."),
    "balanced": ("Cân bằng", "Một mô hình, mức xử lý vừa phải. Nên nghe thử trước."),
    "natural": ("Ưu tiên giọng", "Mô hình tinh chỉnh, không thêm bộ lọc khử nhiễu. Chạy chậm hơn; lần đầu tải thêm mô hình."),
    "thorough": ("Lọc kỹ", "Mô hình tinh chỉnh và nhiều lượt tách hơn. Tốn thời gian hơn; nên thử 30 giây trước."),
}

@dataclass
class Settings:
    key: str
    label: str
    model: str
    shifts: int
    overlap: float
    join_seconds: float
    fallback_reason: str = ""

def configure(profile, key="auto"):
    if key not in MODES:
        raise ValueError("Chế độ xử lý không hợp lệ.")
    if key == "auto":
        key = "balanced" if profile.device in ("cuda", "mps") and profile.available_gb >= 3 else "light"
    reason = ""
    if key in ("natural", "thorough") and profile.available_gb < 3:
        key = "balanced"
        reason = "RAM trống dưới 3 GB; chuyển Cân bằng để hạn chế thiếu bộ nhớ."
    profile = replace(profile)
    if key == "light":
        profile.cpu_threads = min(profile.cpu_threads, 2)
        profile.chunk_seconds = min(profile.chunk_seconds, 30)
        profile.segment = min(profile.segment, 4)
        settings = Settings(key, MODES[key][0], "htdemucs", 0, .15, .25, reason)
    elif key == "balanced":
        profile.cpu_threads = min(profile.cpu_threads, 4)
        profile.chunk_seconds = min(profile.chunk_seconds, 60)
        settings = Settings(key, MODES[key][0], "htdemucs", 1, .25, .5, reason)
    else:
        profile.cpu_threads = min(profile.cpu_threads, 4)
        profile.chunk_seconds = min(profile.chunk_seconds, 60)
        settings = Settings(key, MODES[key][0], "htdemucs_ft",
                            1 if key == "natural" else 2, .5, .5, reason)
    return profile, settings
