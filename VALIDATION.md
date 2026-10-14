# Kiểm chứng bản 1.1

- Các kiểm thử hồi quy gồm đường dẫn Windows, xử lý hàng loạt, hủy tác vụ, float/crossfade, chế độ và nghe thử.
- Bổ sung kiểm thử bộ lọc lời thoại theo phần, stereo/thời lượng, checksum cache, mẫu không hợp lệ, giữ kết quả đã tách khi lọc lỗi/hủy, GPU probe tách tiến trình.
- Windows CI chạy bộ cài thật, GUI offscreen, mô hình lời thoại ONNX thật trên âm thanh tổng hợp và biên dịch launcher/đóng gói ZIP.
- Mẫu giong.wav 30 giây được thử xử lý cục bộ, không đưa vào GitHub. Trong môi trường thử: khoảng 12,5–13,8 giây CPU 2 luồng, peak RSS khoảng 227 MB. Đây không phải cam kết hiệu năng trên mọi máy.
- Nhận dạng lời nói thử cho cùng nội dung trước/sau lọc trên mẫu đó, nhưng không chứng minh giọng không méo hoặc nhạc đã hết.
- Không kiểm chứng chất lượng nghe bằng thước đo có track giọng sạch làm chuẩn; không bảo đảm sạch nhạc tuyệt đối.
