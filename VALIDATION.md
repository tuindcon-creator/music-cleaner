# Kiểm chứng

- 7 kiểm thử xử lý đạt trên Windows/Python 3.11 và Linux/Python 3.12 với FFmpeg: trích video có âm thanh, xuất WAV/MP3/FLAC, tên trùng, waveform, video không có tiếng, hủy tác vụ và dọn file.
- Kiểm thử điều phối Demucs dùng mô hình giả, kiểm tra đường dẫn và xuất hai stem.
- Bộ phụ thuộc cài thành công trên Windows; Demucs CLI chạy được.
- Giao diện PySide6 6.8.3 mở được ở chế độ offscreen trên Windows và Linux.
- Windows workflow: https://github.com/tuindcon-creator/music-cleaner/actions/runs/38398235291
- Chưa chạy tách AI với mô hình thật hoặc bản thu thật; chưa thử nghe trên thiết bị âm thanh Windows thực tế.
- Chưa đo chất lượng tách lời thoại hoặc mức RAM trên file dài.
