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
AI đọc trực tiếp WAV đã giải mã, không gọi ffprobe trên PATH của Windows.
Sau khi thư viện và mô hình đã có trên máy, xử lý được offline; không tải media lên dịch vụ.

## Giao diện mới

Bố cục theo ảnh tham khảo: thông tin file ở trên, sóng âm có mốc thời gian, hàng đợi và khung nghe thử, phần xuất kết quả với nút xanh lớn.
Sóng âm được đọc ngay sau khi chọn file và giữ đúng theo file đang chọn trong danh sách.
Chỉnh âm lượng ở khung nghe thử. Chọn WAV/MP3/FLAC ở phần xuất file.
Bấm **Tùy chọn** để đổi sang trích âm thanh hoặc chọn thiết bị; mặc định AI và thiết bị tự động.
Bấm **Nhật ký xử lý** để xem chi tiết; nhật ký tự mở khi có lỗi.
Tên file kết quả chỉ hiển thị, không phải ô đổi tên; mỗi file vẫn có thư mục xuất riêng.
Bảng hiển thị hàng đợi, không phải các đoạn phát hiện nhạc. Không tô các vùng xanh/đỏ nhận diện nhạc khi chưa có chức năng này.

## Chế độ tách và ưu tiên giữ giọng

Chọn chế độ ngay ở phần xuất file:

| Chế độ | Cách xử lý | Tài nguyên |
| --- | --- | --- |
| Tự động | Cân bằng trên GPU, Nhẹ trên CPU | Theo cấu hình |
| Nhẹ | htdemucs, không tăng cường dịch chuyển, đoạn ngắn, tối đa 2 luồng | Thấp hơn |
| Cân bằng | htdemucs, 1 lượt tăng cường, tối đa 4 luồng | Vừa |
| Ưu tiên giọng | htdemucs_ft gồm nhiều mô hình tinh chỉnh, 1 lượt tăng cường | Chậm hơn |
| Lọc kỹ | htdemucs_ft, 2 lượt tăng cường | Chậm nhất trong các lựa chọn |

Với lời thoại trên RTX 3060, nên bắt đầu bằng Ưu tiên giọng rồi bấm **Thử 30 giây**.
Nếu cần nhẹ, chọn Nhẹ hoặc Tự động. Không có chế độ vừa mạnh nhất vừa nhanh/nhẹ nhất.
htdemucs_ft cần tải thêm các trọng số ở lần đầu, sau đó dùng cache offline.
RAM trống dưới 3 GB sẽ tự hạ chế độ tinh chỉnh về Cân bằng và ghi lý do trong nhật ký.

**Thử 30 giây** chỉ xử lý file đang chọn, xuất vào thư mục có tiền tố Thu_30s_.
Khi nghe bản gốc, mẫu thử bắt đầu từ vị trí hiện tại trên thanh nghe thử; khi chọn kết quả, thử từ đầu file.
Kết quả thử xuất tối đa 30 giây; file ngắn hơn sẽ có thời lượng ngắn hơn.
Mẫu thử không đổi sóng âm/thông tin thời lượng toàn file và không thay thế kết quả cả file.
Chọn giong.wav (thử 30s) trong khung nghe thử để đối chiếu với bản gốc.

Không thêm cắt tần số, EQ, noise gate hoặc lọc phổ mạnh. AI vẫn có thể làm đổi giọng hoặc còn nhạc;
không thể bảo đảm tuyệt đối hết nhạc và giữ nguyên giọng. Tên Ưu tiên giọng thể hiện cách chọn mô hình, không phải cam kết không biến dạng.
Ghép đoạn bằng chồng lấn/crossfade có căn thời gian. Trung gian giữ WAV float, tránh thay đổi mức âm mỗi đoạn.
Nếu có mẫu vượt biên PCM, giảm một mức âm cố định cho toàn stem trước xuất; không dùng limiter/compressor.
Khuyên xuất WAV hoặc FLAC khi cần so sánh chất lượng, giữ bản gốc để đối chiếu.

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
Tên thư mục kết quả được chuẩn hóa cho Windows: bỏ dấu chấm/khoảng trắng cuối tên, thay ký tự cấm, tránh tên dành riêng và rút ngắn tên dài. Không đổi tên video/audio gốc.
Kiểm tra ghi vào thư mục xuất trước khi giải mã hoặc chạy AI; đường dẫn quá dài cần chọn thư mục ngắn hơn.
Có nghe thử bản gốc/kết quả, sóng âm, nhật ký và nút dừng.
Nếu lỗi, nguyên nhân hiện phía trên nhật ký; dùng Lưu nhật ký lỗi để xuất thông tin chẩn đoán.

Demucs tách nguồn vocals/accompaniment, không bảo đảm lời thoại sạch tuyệt đối.
Bản này tách toàn bộ file, chưa tự nhận diện từng đoạn có nhạc theo hình tham khảo.
Chồng lấn/crossfade giảm chuyển tiếp đột ngột ở ranh giới phần; vẫn có thể còn khác biệt do dự đoán AI.
Sóng âm là của file vừa xử lý; tiến độ theo giai đoạn, không phải phần trăm suy luận chính xác.
File nhiều giờ vẫn cần nhiều dung lượng đĩa; WAV PCM16 tạm có giới hạn kích thước RIFF khoảng 4 GB.
Không xuất lại video đã thay giọng. Bản nguồn dùng Python, chưa phải EXE độc lập.

## Kiểm thử

`python -m unittest discover -s tests -v`

Windows CI kiểm tra bộ cài thật, Demucs CLI, xử lý FFmpeg, chọn cấu hình, fallback và GUI offscreen.
Mô hình giả dùng trong kiểm thử điều phối; không thay thế việc kiểm chứng chất lượng trên bản thu thật.
