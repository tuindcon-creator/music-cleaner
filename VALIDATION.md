# Kiểm chứng

- Windows trước bản sửa ffprobe: bộ cài thật, 16 kiểm thử và GUI offscreen đạt.
- Lỗi thực tế: Demucs CLI gọi ffprobe trên PATH; Windows trả PermissionError WinError 5 sau một số đoạn đã tách thành công trên RTX 3060.
- Bản sửa dùng SoundFile đọc WAV đã giải mã và Demucs convert_audio, không gọi ffprobe.
- Có kiểm thử hồi quy giả lập ffprobe bị từ chối quyền và kiểm tra kênh/tần số mẫu.
- 16 kiểm thử xử lý và cấu hình đạt trên Linux; kiểm thử đọc WAV trực tiếp cần bộ PyTorch/Demucs đầy đủ, được chạy trên Windows CI.
- Giao diện lỗi và trạng thái kết thúc đã kiểm tra offscreen.
- Chưa chạy lại bản thu 26 phút của người dùng hoặc thử trên GPU vật lý sau bản sửa.
