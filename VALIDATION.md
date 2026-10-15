# Kiểm chứng bản 1.4

- Các kiểm thử hồi quy gồm đường dẫn Windows, xử lý hàng loạt, hủy tác vụ, float/crossfade, chế độ và nghe thử.
- Bổ sung kiểm thử bộ lọc lời thoại theo phần, stereo/thời lượng, checksum cache, mẫu không hợp lệ, giữ kết quả đã tách khi lọc lỗi/hủy, GPU probe tách tiến trình.
- Windows CI chạy bộ cài thật, GUI offscreen, mô hình lời thoại ONNX thật trên âm thanh tổng hợp và biên dịch launcher/đóng gói ZIP.
- Mẫu giong.wav 30 giây được thử xử lý cục bộ, không đưa vào GitHub. Trong môi trường thử: khoảng 12,5–13,8 giây CPU 2 luồng, peak RSS khoảng 227 MB. Đây không phải cam kết hiệu năng trên mọi máy.
- Nhận dạng lời nói thử cho cùng nội dung trước/sau lọc trên mẫu đó, nhưng không chứng minh giọng không méo hoặc nhạc đã hết.
- Không kiểm chứng chất lượng nghe bằng thước đo có track giọng sạch làm chuẩn; không bảo đảm sạch nhạc tuyệt đối.

- Bản 1.2 kiểm tra dùng lại mô hình/tiến trình giữa nhiều đoạn, giữ nguyên tham số CLI, lỗi GPU/chuyển CPU, hủy và đóng tiến trình, lỗi tiến trình con. Tốc độ RTX 3060 chưa được đo trong CI CPU.

- Tái hiện bằng DPDFNet thật: trước sửa, file 30,001 s, 65,013 s và 0,01 s lỗi kiểm tra số mẫu; sau sửa, cả ba xuất đúng thời lượng và stereo. Mẫu riêng giong.wav 30 s được chạy qua tiến trình con và xuất giong_loc.wav; không commit hoặc tải mẫu lên dịch vụ.
- Bổ sung hồi quy phần lẻ/rất ngắn, không bù dự đoán lỗi bằng im lặng, file giọng lọc xuất nguyên tử, kiểm tra thời lượng/kênh, preflight, giữ bản trước lọc, thống kê hàng loạt không đánh dấu thành công khi thiếu giọng lọc.
- Windows CI chạy mô hình lời thoại thật ở 44,1/48/22,05 kHz, file nhiều phần, phần lẻ/rất ngắn và xuất WAV/MP3/FLAC; thêm thử đầy đủ với Demucs pretrained thật → DPDFNet → ba file kết quả. Các tín hiệu này là tổng hợp để kiểm tra phần mềm, không chứng minh chất lượng nghe.

- Bản 1.3.1: nhật ký người dùng xác nhận PermissionError WinError 5 tại thao tác thay speech_progress.json sau đoạn 63. Không commit nhật ký hoặc đường dẫn riêng của người dùng.
- Kiểm thử ép 2.000 lần lỗi thay file tiến độ, lỗi ghi/xóa file phụ và phục hồi sau lỗi; lỗi xuất âm thanh vẫn phải được báo.
- Kiểm thử Windows dùng CreateFileW không có FILE_SHARE_DELETE: thao tác cũ thực sự phát sinh PermissionError, bộ báo tiến độ mới bỏ qua và tiếp tục. Thử mô hình thật giữ khóa file tiến độ qua toàn bộ preflight/lọc, xác nhận đủ ba file, đúng stereo/thời lượng và giữ nguyên đầu vào.

- Bản 1.4: hồi quy tách lại chạy đúng một lượt AI, giữ bản trước và file nguồn, thư mục không ghi đè, báo cáo chế độ/tên file, giữ kết quả khi lọc bổ sung lỗi, thử 30 giây và tách lại hàng loạt. Kiểm tra nút một file chỉ xử lý file đang nghe và không xóa kết quả các hàng khác.
- Kiểm tra mô hình thật trên Windows: lấy giong.wav do lượt Demucs đầu xuất ra, chạy lại bằng chế độ tách lại, xác nhận đủ ba file mới, đúng stereo/thời lượng và nguồn giữ nguyên. Không khẳng định tách nhiều lượt luôn cải thiện chất lượng giọng hoặc nhạc.
