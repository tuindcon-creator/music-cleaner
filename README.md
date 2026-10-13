# Music Cleaner — tự cấu hình máy

Ứng dụng tách giọng/nhạc nền, trích âm thanh từ video và xử lý hàng loạt, giao diện tiếng Việt.

## Chạy trên Windows

1. Tải ZIP ở nhánh music-cleaner-app và giải nén vào thư mục có quyền ghi.
2. Mở **run_windows.bat**. Lần đầu chương trình tự chạy bộ cài nếu thiếu thư viện.
3. Bộ cài tìm Python 3.11 x64; nếu chưa có, thử cài cho người dùng hiện tại bằng winget.
4. Bộ cài kiểm tra driver NVIDIA, chọn PyTorch CUDA 12.1 hoặc CPU và thử GPU thực tế.
5. Chọn file → chức năng → thư mục xuất → Bắt đầu. Giữ thiết bị **Tự động**.

Có thể mở install_windows.bat riêng để cài lại thư viện hoặc sửa môi trường.
Nếu winget không có hoặc bị quản trị viên chặn, cài Python 3.11 64-bit từ python.org rồi chạy lại.
Không cần cài FFmpeg riêng. Cần Internet cho bộ cài và lần đầu tải mô hình AI.
Sau khi thư viện và mô hình đã có trên máy, xử lý được offline; không tải media lên dịch vụ.

## Tự nhận diện cấu hình

- Đọc hệ điều hành, kiến trúc, số luồng CPU, tổng RAM và RAM còn trống.
- Chỉ dùng CUDA khi PyTorch cấp phát và tính toán được trên GPU, VRAM ít nhất 2 GB.
- AMD/Intel hoặc NVIDIA không tương thích dùng CPU.
- GPU thiếu bộ nhớ/lỗi CUDA hoặc MPS khi tách sẽ thử lại đoạn đó trên CPU.
- Chọn đoạn AI nội bộ 4 hoặc 7 giây và chia file dài thành phần 30/60/90 giây theo RAM trống.
- Chạy hàng đợi tuần tự; giới hạn luồng tính toán tối đa 8.
- Kiểm tra dung lượng ổ đĩa trước bước AI; báo lỗi thay vì giữ kết quả chưa hoàn tất.
- Thông tin lựa chọn hiện trong nhật ký. system_report.json ghi cấu hình lúc cài, không chứa mật khẩu.

Nếu đã cài bản CPU trước đây và muốn tự phát hiện NVIDIA lại, chạy install_windows.bat.
Khi chép ứng dụng sang máy khác, không chép .venv; chạy run_windows.bat để cài theo máy mới.
PowerShell ExecutionPolicy Bypass chỉ áp dụng cho tiến trình bộ cài; không đổi chính sách hệ thống.

## Nền tảng hỗ trợ

Windows 10/11 x64 là mục tiêu chính, có kiểm tra CI. Cần ổ đĩa đủ chỗ cho thư viện và WAV tạm.
Khuyên dùng RAM từ 4 GB cho CPU; dưới mức này có thể không đủ bộ nhớ cho mô hình.
Không bảo đảm chạy trên mọi máy: Windows 32-bit, Windows cũ và Windows ARM native chưa hỗ trợ.
Máy không có quyền cài phần mềm, mạng bị chặn hoặc quá thiếu bộ nhớ cần xử lý điều kiện đó trước.

Linux x64 và macOS Apple Silicon có script bổ sung: cài Python 3.11 rồi chạy
`sh install_unix.sh`, sau đó `.venv/bin/python app.py`.
Hai nền tảng này chưa có bộ cài tự cài Python; Mac Intel/ARM Linux chưa được hỗ trợ bởi bộ phiên bản ghim.
Apple GPU được thử qua MPS, nhưng Demucs có thể cần quay về CPU.

## Kết quả và chất lượng

Xuất WAV, MP3 192 kbps hoặc FLAC. Tách AI xuất giong và nhac_nen; trích âm thanh xuất am_thanh.
Mỗi file có thư mục riêng, thêm hậu tố khi tên trùng; file lỗi không chặn hàng đợi.
Có nghe thử bản gốc/kết quả, sóng âm, nhật ký và nút dừng.

Demucs tách nguồn vocals/accompaniment, không bảo đảm lời thoại sạch tuyệt đối.
Bản này tách toàn bộ file, chưa tự nhận diện từng đoạn có nhạc theo hình tham khảo.
Việc chia file để tiết kiệm RAM có thể tạo khác biệt tại ranh giới các phần.
Sóng âm là của file vừa xử lý; tiến độ theo giai đoạn, không phải phần trăm suy luận chính xác.
File nhiều giờ vẫn cần nhiều dung lượng đĩa; WAV PCM16 tạm có giới hạn kích thước RIFF khoảng 4 GB.
Không xuất lại video đã thay giọng. Bản nguồn dùng Python, chưa phải EXE độc lập.

## Kiểm thử

`python -m unittest discover -s tests -v`

Windows CI kiểm tra bộ cài thật, Demucs CLI, xử lý FFmpeg, chọn cấu hình, fallback và GUI offscreen.
Mô hình giả dùng trong kiểm thử điều phối; không thay thế việc kiểm chứng chất lượng trên bản thu thật.
