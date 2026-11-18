# Phiếu quay thử (phụ lục của protocol quay 2 camera, mục 7)

- Phiên bản: 0.1, ngày 2026-11-17, dành cho task P1.09 (P1.09a tập dượt, P1.09b take thử).
- Đi kèm: `Docs/capture_protocol.md` (phiên bản 1.0). Phiếu này chỉ thêm những gì buổi thử cần đo; mọi quy tắc khác của protocol vẫn đúng.
- Không ghi tên thật, số điện thoại, địa chỉ hay vị trí GPS vào phiếu này. Bản đã điền có thể có tên người tập bên cạnh mã `P00`:
  bản đó do O giữ ngoài kho mã nguồn và ngoài git. Bản trong kho chỉ là mẫu trống.

## 1. Hai phần của buổi thử

| | P1.09a: tập dượt | P1.09b: take thử |
| --- | --- | --- |
| Có người tập không | Không. Chỉ tay cầm đèn, tiếng vỗ tay, một cây sào và bảng checkerboard | Có một người tập đã ký phiếu đồng ý |
| Cần phiếu đồng ý đã ký | Không | Có, và O đã ghi ngày duyệt pháp lý của mẫu (task P1.06) |
| Buổi (`session_id`) | `S99` | `S00` |
| Mã người | `P99` (người thử, chỉ có trong thư mục thử bỏ đi, không vào CSDL thật) | `P00` |
| Mã take | `S99-P99-T01` | `S00-P00-T01` (dự phòng `S00-P00-T02`) |
| Mã bảng | `S99-CB-T01` | `S00-CB-T01` |
| Người xem hình và nghe tiếng | Người của dự án. Trợ lý AI chỉ xem một đoạn khi người xem đã xác nhận đoạn đó không có mặt người và không có tiếng nói | Chỉ maintainer hoặc O, tại máy này; trợ lý AI không xem gì |

Hình và tiếng của người tập không gửi cho ai và không đưa lên dịch vụ nào, kể cả cho trợ lý AI. Trợ lý chỉ nhận các con số
(độ dài, số khung hình, độ sáng, số lần đèn nhấp...) do chương trình tính; mọi việc xem hình và nghe tiếng do người làm.

## 2. Trước khi quay (O, trên cả hai điện thoại)

- ☐ Ứng dụng quay: **tắt gắn thẻ vị trí** (geotag, "location tags") và không cấp quyền vị trí cho ứng dụng.
- ☐ Thư viện ảnh: **tắt tự động sao lưu lên đám mây** (cả ảnh và video). Sau buổi quay kiểm lại rằng không có file mới trên đám mây.
- ☐ Làm đúng mục 4 của protocol (1080p, 30 fps cố định, khóa phơi sáng, lấy nét, zoom; tắt chống rung, HDR, làm đẹp; khóa hướng ngang;
  bật micro; không làm phiền; tắt tiết kiệm pin).
- ☐ Ghi model điện thoại, hệ điều hành, tên và phiên bản ứng dụng vào `Docs/capture_devices.md`. Không ghi số seri hay tên chủ máy.
- ☐ Dung lượng trống từ 32 GB mỗi máy, pin đầy, hai chân máy, thước dây.

### Nếu là iPhone (ví dụ iPhone 14 Pro Max)

Tên mục có thể khác theo bản iOS và chưa được kiểm trên máy thật: buổi tập dượt kiểm lại từng mục và ghi kết quả vào
`Docs/capture_devices.md`.

- ☐ Cài đặt → Camera → Quay video: chọn **1080p HD ở 30 fps**; tắt **Auto FPS** (nếu có); tắt **HDR video** (nếu có); bật **Khóa camera**
  (nếu có) để máy không tự đổi ống kính. Chỉ dùng ống kính chính 1×, không zoom, không dùng chế độ Hành động (Action) hay Điện ảnh (Cinematic).
- ☐ Cài đặt → Camera → Định dạng: **Hiệu quả cao** là HEVC, **Tương thích nhất** là H.264. Chọn "Tương thích nhất" nếu muốn file H.264;
  HEVC cũng được chấp nhận nếu chương trình đọc được (protocol mục 4); ghi lại đã chọn gì.
- ☐ Khóa phơi sáng và lấy nét: chạm giữ vào khung hình cho đến khi hiện "Khóa AE/AF".
- ☐ Vị trí: Cài đặt → Quyền riêng tư và bảo mật → Dịch vụ định vị → Camera → **Không bao giờ**.
- ☐ Sao lưu: Cài đặt → Ảnh → **Ảnh iCloud tắt**.
- ☐ Chép sang Windows bằng cáp: Cài đặt → Ảnh → "Chuyển sang Mac hoặc PC" → chọn **Giữ bản gốc**. Nếu để "Tự động", iPhone có thể đổi
  HEVC sang định dạng khác lúc chép, tức là nén lại file, trái mục 8 của protocol.
- ☐ Chế độ Tập trung (Không làm phiền) bật; tắt Chế độ nguồn điện thấp.
- Lưu ý: camera gốc của iPhone không có nút "khóa tốc độ khung hình" như ứng dụng chuyên dụng, và file iPhone thường ghi thời điểm
  khung hình hơi lệch đều. Đó chính là điều buổi tập dượt đo (kiểm C-2). Nếu file bị đánh dấu VFR, thử ứng dụng quay có khóa fps
  (ví dụ Blackmagic Camera, đã nêu ở W0 của TECH_WORKFLOW) và so sánh.

## 3. Phiếu của buổi (điền một lần)

| Trường | Giá trị | Ghi chú |
| --- | --- | --- |
| `session_id` | | `S99` hoặc `S00` |
| Ngày | | `YYYY-MM-DD` |
| Nơi quay | | Mô tả bằng tên phòng hoặc vật mốc, không ghi địa chỉ |
| Vùng tập (dài × rộng, m) | | Đánh dấu bằng băng keo |
| Hướng bài | | Vật mốc trong phòng mà người tập quay mặt tới ở thức đầu tiên |
| Máy A (`camA`): vai | `main_axis` | Trên trục chính, ngay trước người tập |
| Máy A: độ cao (m), khoảng cách tới tâm vùng tập (m) | | Đo bằng thước dây |
| Máy B (`camB`): vai | `side_left` hoặc `side_right` | Lệch 90°, giữ nguyên cả buổi |
| Máy B: độ cao (m), khoảng cách tới tâm vùng tập (m) | | Đo bằng thước dây |
| Ứng dụng quay, tốc độ khung hình đặt (Hz), codec | | Mỗi máy một dòng |
| Đường thẳng đứng thật trong khung (khung cửa, cột, dây dọi) | máy A: có / không; máy B: có / không | Dùng để hiệu chỉnh độ nghiêng máy |
| Đèn: loại, kích thước phần sáng (cm), khoảng cách tới máy A và máy B (m) | | Thử cả đèn thứ hai, to hơn, nếu có (chỉ ở P1.09a) |
| Bảng checkerboard: số góc trong, cạnh một ô đo bằng thước (mm) | | Đo 10 ô liền nhau rồi chia 10: máy in có thể co giãn tờ in |
| Ánh sáng phòng | | Có cửa sổ phía sau người tập không; đèn có nhấp nháy không |
| Thẻ vị trí và sao lưu đám mây đã tắt (cả hai máy) | có / không | Mục 2 |

## 4. Phiếu của từng take (một dòng mỗi file)

| Trường | Giá trị | Ghi chú |
| --- | --- | --- |
| `take_id` | | Giống nhau cho cả hai máy |
| `camera_id` | | `camA` hoặc `camB` |
| Tên file gốc | | Tên do điện thoại đặt, để đối chiếu |
| Tên file sau khi đổi | | `<take_id>-<camera_id>.<đuôi>`, chỉ đổi tên bản sao |
| Tín hiệu đầu: thấy đủ hai lần đèn, nghe đủ hai tiếng vỗ | có / không | Xem lại vài giây ngay sau take, trên cả hai file |
| Tín hiệu cuối: như trên | có / không | |
| Người hỗ trợ đã ra khỏi khung hình trước khi người tập đứng tham chiếu | có / không | Chỉ ở P1.09b |
| Người tập đứng yên trước khi bắt đầu bài (giây) | | Chỉ ở P1.09b; protocol 1.1 sẽ ghi số cần thiết |
| Ghi chú bất thường | | Không xóa take lỗi, chỉ ghi chú |

## 5. P1.09a: các bước của buổi tập dượt (khoảng 1 giờ)

1. Đặt máy theo mục 3 của protocol, đo độ cao và khoảng cách; quay thử 10 giây ở mỗi máy.
2. Bấm quay cả hai máy, chờ 5 giây. Take `S99-P99-T01`:
   - tín hiệu đầu ở giữa vùng tập: vỗ tay hai lần kèm bật đèn (cầm đèn ở tầm ngực); lặp lại với đèn thứ hai, to hơn, nếu có;
   - cầm cây sào thẳng đứng khoảng 5 giây ở từng góc vùng tập và ở giữa (để kiểm vùng tập có nằm trọn trong khung, cách mép khoảng 10 %);
   - vỗ tay mạnh rồi vỗ tay nhẹ, mỗi kiểu hai lần;
   - tín hiệu cuối giống tín hiệu đầu; chờ 5 giây rồi dừng cả hai máy.
3. Quét checkerboard `S99-CB-T01` theo mục 6 của protocol. Người cầm bảng đứng sau bảng, không để mặt vào khung.
4. Ghi thời gian từng phần (đặt máy, quét bảng, take, chép file) vào mục 7.
5. Chép file bằng cáp hoặc đầu đọc thẻ sang hai nơi (máy phân tích và ổ ngoài do O giữ); đổi tên bản sao theo mục 7 của protocol;
   chỉ xóa file trên điện thoại (và trong "đã xóa gần đây") khi cả hai bản đã kiểm tra.

## 6. P1.09b: take thử (khoảng 1,5 giờ)

Chỉ làm khi đủ điều kiện: O đã ghi ngày duyệt pháp lý của mẫu đồng ý, người tập đã ký, `P00` đã được đăng ký, hàng D08 của
`Docs/DATASET_REGISTRY_TAIJI.md` đã cập nhật, và P1.09a đã xong.

1. Đặt máy đúng các giá trị đã chốt ở P1.09a; quét checkerboard `S00-CB-T01`.
2. Take `S00-P00-T01` theo mục 5 của protocol: tín hiệu đầu, **người hỗ trợ ra khỏi khung hình**, người tập đứng yên rồi đứng
   tham chiếu 3 đến 5 giây, tập trọn bài, đứng lại, tín hiệu cuối, chờ 5 giây, dừng.
3. Kiểm nhanh trong 1 phút (mục 9 của protocol). Quay `S00-P00-T02` ngay sau đó nếu take thứ nhất lỗi, hoặc nếu người tập đồng ý và còn thời gian.
4. Nếu người tập thấy tay bị mờ khi xem lại ở 30 fps, quay thêm một đoạn ngắn ở 60 fps và ghi lại.
5. Người xem hình (maintainer hoặc O) mở từng file và điền: người tập có nằm trọn trong khung suốt bài ở cả hai máy không, có ai khác
   trong khung không, đường thẳng đứng có trong khung không; ghi giây của từng chỗ có vấn đề (không ghi tên ai).
6. Chép file như bước 5 của mục 5.

## 7. Thời gian từng phần (ghi để cập nhật protocol 1.1)

| Phần | Dự kiến trong protocol (thử) | Thực tế (phút) |
| --- | --- | --- |
| Đặt máy, cài đặt, quay thử 10 giây | khoảng 25 phút | |
| Quét checkerboard | tối đa 5 phút | |
| Một take (tín hiệu, tham chiếu, bài, nghỉ) | khoảng 25 phút cho 3 take | |
| Thu dọn và chép file | khoảng 10 phút | |

## 8. Danh sách mang theo cho P1.09a

- ☐ Hai điện thoại (cùng đời máy nếu có), hai chân máy có kẹp, cáp hoặc đầu đọc thẻ, ổ ngoài.
- ☐ Một đèn cầm tay (đèn LED hoặc đèn pin) và, nếu có, một đèn thứ hai to hơn.
- ☐ Bảng checkerboard in mờ trên bảng cứng: 9 × 6 góc trong, 10 × 7 ô; ô 80 mm thì bảng khoảng 800 × 560 mm (vừa khổ A1).
- ☐ Một cây sào khoảng 2 m, có băng keo đánh dấu mỗi 0,5 m.
- ☐ Băng keo hoặc phấn, thước dây, bản in protocol và phiếu này, bút.
- ☐ Một người hỗ trợ là thành viên dự án, biết rằng file không được gửi qua ứng dụng nhắn tin hay đưa lên đám mây.
