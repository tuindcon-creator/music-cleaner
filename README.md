# Music Cleaner — Windows 10/11

Ứng dụng Python chạy local, giao diện tiếng Việt màu tối theo ảnh tham khảo.

## Chức năng

- Nhập nhiều file âm thanh hoặc video, hoặc thêm các file trong một thư mục.
- AI tách toàn bộ file thành `giong` và `nhac_nen` bằng Demucs htdemucs.
- Trích âm thanh từ video mà không tách nguồn.
- Xuất WAV, MP3 192 kbps hoặc FLAC.
- Nghe thử bản gốc và kết quả, sóng âm, nhật ký, dừng tác vụ.
- File lỗi không chặn cả hàng đợi. Tự tạo thư mục có số hậu tố khi trùng tên.
- File đầu vào không bị sửa. Kết quả chưa hoàn tất bị xóa khi dừng hoặc lỗi.

## Cài đặt và chạy trên Windows

1. Cài **Python 3.11 64-bit** từ https://www.python.org/downloads/ (bao gồm Python Launcher).
2. Giải nén bộ mã vào thư mục có quyền ghi; không chạy bên trong ZIP.
3. Mở `install_windows.bat`. Cài CPU mặc định, tải vài GB thư viện; cần Internet.
4. Mở `run_windows.bat`.
5. Chọn nhiều file → chức năng → định dạng → thư mục xuất → Bắt đầu.
6. Chọn hàng trong bảng để nghe file gốc hoặc kết quả; bấm Mở thư mục để xem file.

FFmpeg đi kèm gói imageio-ffmpeg; không cần cài riêng.
Lần chạy AI đầu tiên cần tải mô hình từ máy chủ Demucs (dl.fbaipublicfiles.com).
Sau khi mô hình đã lưu cache, xử lý được offline trên chính máy đó.
Cache mặc định của PyTorch thường ở `%USERPROFILE%\.cache\torch\hub\checkpoints`.
Ứng dụng không tải video/âm thanh của bạn lên dịch vụ bên ngoài.

## GPU NVIDIA (tùy chọn)

Bộ cài mặc định dùng CPU. Để dùng NVIDIA với driver phù hợp, trong thư mục ứng dụng chạy:

```bat
.venv\Scripts\python.exe -m pip install --force-reinstall torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
```

Sau đó chọn GPU trong ứng dụng. Nếu không có CUDA phù hợp, chọn CPU.
Không chọn GPU cho card AMD/Intel bằng bản này.

## Chất lượng và giới hạn

Demucs là mô hình tách nguồn âm nhạc (vocals / accompaniment), không bảo đảm lời thoại sạch tuyệt đối.
Giọng hát và giọng nói đều có thể vào nhánh giọng. Hiệu ứng, tiếng vang và nhạc có thể còn sót.
Bản này **không tự nhận diện các đoạn có nhạc và không giữ nguyên từng đoạn không có nhạc**
như lời mô tả trong ảnh; nó tách toàn bộ file. Không tô vùng xanh/đỏ giả.
Sóng âm hiển thị file vừa xử lý, không phải kết quả nhận diện nhạc của file đang chọn.
Tiến độ theo giai đoạn và số file, không phải phần trăm suy luận AI chính xác.
Xử lý tuần tự để hạn chế bộ nhớ; CPU có thể chậm hơn thời lượng file.
Demucs vẫn nạp toàn bộ âm thanh; file nhiều giờ có thể cần RAM lớn.
Nên có khoảng 8 GB RAM trở lên và nhiều dung lượng trống cho WAV tạm.
Chế độ xuất WAV/FLAC giữ dạng lossless sau giải mã; không cải thiện chất lượng nguồn.
Video không có track âm thanh hoặc file hỏng sẽ có lỗi trong nhật ký.
Không xuất lại video đã thay giọng trong bản này.

## Kiểm thử phát triển

```sh
python -m unittest discover -s tests -v
```

Cần cài imageio-ffmpeg để chạy kiểm thử tích hợp FFmpeg.
Giao diện có thể kiểm tra bằng QT_QPA_PLATFORM=offscreen trên Linux.
Bản nguồn chưa phải EXE độc lập. Bộ thư viện được ghim để tránh torchaudio mới chuyển sang TorchCodec.

