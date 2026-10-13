# Kiểm chứng

- Bản tự cấu hình: 16 kiểm thử đạt trên Linux/Python 3.12, gồm trích video, xuất định dạng, tên trùng, hủy/dọn file, chọn cấu hình, chia/ghép file và GPU lỗi quay về CPU.
- GUI mở được offscreen và mặc định chọn thiết bị tự động.
- Nhánh Windows mới kiểm tra setup_windows.ps1 thật, môi trường .venv, Demucs CLI, kiểm thử và GUI. Xem trạng thái tại GitHub Actions.
- Bản trước đã cài thư viện và chạy 7 kiểm thử cùng GUI smoke check trên Windows/Python 3.11.
- Chưa kiểm thử trên GPU vật lý, Mac, Windows không có Python/winget, hoặc tách mô hình thật trên bản thu thật.
- Không bảo đảm chất lượng tách lời thoại hoặc chạy trên máy không đủ RAM/đĩa.
