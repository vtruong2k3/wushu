# Thiết bị quay đã dùng

- Phiên bản: 0.1, ngày 2026-11-17. File này viết tay: `Docs/hardware_inventory.md` do `tools/env_check.py` sinh ra và sẽ bị ghi đè khi chạy lại, nên điện thoại không ghi ở đó (BUG-0076).
- Ghi: model điện thoại, hệ điều hành, tên và phiên bản ứng dụng quay, cài đặt đã chạy được. **Không ghi** số seri, mã IMEI, tên chủ máy, tài khoản hay vị trí.
- Mỗi dòng do người quay điền sau buổi thử (task P1.09). Giá trị nào chưa đo thì để "chưa đo", không đoán.
- Cách dùng: protocol (mục 11 và phiên bản 1.1), P1.05, P2.07 và P9.02 đọc file này để biết máy nào quay ra file nào.

## 1. Điện thoại

Đã biết (2026-11-17): một iPhone 14 Pro Max. Máy thứ hai chưa biết; chưa gán máy nào là `camA` hay `camB`; hệ điều hành và ứng dụng quay chưa ghi.

| Máy (`camera_id`) | Model | Hệ điều hành và phiên bản | Ứng dụng quay và phiên bản | Buổi đã dùng |
| --- | --- | --- | --- | --- |
| `camA` | chưa quay | chưa quay | chưa quay | chưa quay |
| `camB` | chưa quay | chưa quay | chưa quay | chưa quay |

## 2. Cài đặt đã chạy được (điền sau P1.09a và P1.09b)

| Mục | `camA` | `camB` | Ghi chú |
| --- | --- | --- | --- |
| Độ phân giải thực của file | chưa đo | chưa đo | `probe_video` |
| Tốc độ khung hình đặt và tốc độ đo được (Hz) | chưa đo | chưa đo | `scan_pts`; có phải VFR không |
| Codec và container | chưa đo | chưa đo | Có đọc được bằng `probe_video` và `scan_pts` không |
| Có tiếng không, tiếng bắt đầu trễ bao nhiêu so với hình (ms) | chưa đo | chưa đo | `probe_video`, `extract_audio` |
| Thẻ vị trí và sao lưu đám mây đã tắt | chưa kiểm | chưa kiểm | Phiếu quay thử, mục 2 |
| Tay có bị mờ ở 30 fps không | chưa quay | chưa quay | Chỉ nhìn được với người tập (P1.09b) |

## 3. Lịch sử

| Ngày | Thay đổi |
| --- | --- |
| 2026-11-17 | Tạo file trống theo Q7 của P1.09; chưa có buổi quay |
