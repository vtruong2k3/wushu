# Protocol quay 2 camera cho bài 24 thức

- Phiên bản: 1.0, bản nháp trước buổi quay thử (task P1.09), ngày 2026-11-15.
- Dành cho: người đi quay (người điều phối O hoặc huấn luyện viên H). Không cần kiến thức kỹ thuật.
- Căn cứ: `Docs/TECH_WORKFLOW_V1.md` (W0 và quyết định 7), `AGENTS.md` (§5.2 thời gian thật, §5.9 và §9.5 dữ liệu cá nhân).
- Giá trị ghi "(thử)" là giá trị khởi đầu. Buổi quay thử sẽ đo lại và thay bằng giá trị thật ở phiên bản 1.1.

## 1. Vì sao cần protocol này

Video quay sai thì không sửa được về sau: thiếu tín hiệu đồng bộ, tốc độ khung hình thay đổi, người tập ra khỏi khung hay
file bị nén lại đều làm mất dữ liệu. Làm đúng lúc quay là cách kiểm soát chất lượng rẻ nhất của cả dự án. Ba điều quan trọng nhất:

1. Tốc độ khung hình cố định, khóa bằng ứng dụng quay.
2. Hai lần vỗ tay kèm đèn, ở đầu và ở cuối mỗi take, cả hai máy cùng thấy và nghe.
3. File gốc không bao giờ bị nén lại, cắt hay chỉnh sửa; chỉ chép bằng cáp hoặc đầu đọc thẻ.

## 2. Vai trò và dụng cụ

Ba vai (một người có thể kiêm hai vai):

- Người điều phối: chuẩn bị, bấm máy, giữ phiếu ghi, kiểm tra từng take.
- Người tập: tập bài.
- Người hỗ trợ: vỗ tay cùng đèn, cầm bảng checkerboard.

| Dụng cụ | Ghi chú |
| ------- | ------- |
| 2 điện thoại, cùng đời máy nếu có | Pin đầy hoặc có sạc; dung lượng trống từ 32 GB mỗi máy (ước tính 0,5–1 GB mỗi take mỗi máy) |
| 2 chân máy có kẹp điện thoại | Vững, không đặt máy lên bàn lung lay |
| Ứng dụng quay khóa được tốc độ khung hình | Ví dụ trong W0: Blackmagic Camera, Open Camera; chọn theo máy |
| 1 đèn sáng cầm tay (đèn LED hoặc đèn pin) | Dùng cho tín hiệu đèn; phải nhìn thấy từ cả hai máy |
| Bảng checkerboard in sẵn | Quy cách ở mục 6 |
| Băng keo hoặc phấn | Đánh dấu vùng tập và vị trí xuất phát |
| Một đường thẳng đứng thật trong khung | Khung cửa, cột nhà hoặc dây dọi; dùng để đo độ nghiêng máy |
| Cáp hoặc đầu đọc thẻ, máy tính hoặc ổ cứng | Chép file gốc |
| Phiếu ghi (mục 7), bút, phiếu đồng ý đã ký | Mẫu phiếu đồng ý: task P1.06 |

## 3. Bố trí máy

Trục chính của bài là hướng người tập quay mặt lúc thức đầu tiên (Khởi thế). Hai máy đặt theo trục này, không đặt góc tùy ý:

- Máy A (`camA`): ngay trước người tập, trên trục chính, nhìn chính diện lúc bắt đầu.
- Máy B (`camB`): lệch 90°, ở bên cạnh người tập. Chọn bên trái hoặc bên phải, giữ nguyên cả buổi và ghi lên phiếu.
- Các thức đi chéo góc sẽ được tính là vùng coverage thấp; bản 1.0 chấp nhận điều đó, không thêm máy thứ ba.

| Mục | Giá trị khởi đầu | Quy tắc |
| --- | ---------------- | ------- |
| Độ cao máy | 1,0–1,2 m, ngang hông đến ngực (thử) | Máy thẳng đứng, không ngước hay cúi; dùng lưới hoặc thước thủy của điện thoại để cân sao cho đường chân trời trong ảnh nằm ngang |
| Khoảng cách từ máy đến tâm vùng tập | 4–5 m (thử) | Đo bằng thước dây và ghi lên phiếu |
| Vùng tập | Đánh dấu bằng băng keo, kích thước chốt ở buổi quay thử | Người tập không bước ra ngoài vùng |
| Khung hình | Toàn thân, từ đầu đến mũi chân, kể cả khi giơ tay hoặc đá | Luôn cách mép khung khoảng 10% (thử) |
| Đường thẳng đứng | Nằm trong khung ở cả hai máy nếu có thể | Dùng để hiệu chỉnh độ nghiêng máy khi đo độ nghiêng thân (phụ lục B2 của TECH_WORKFLOW) |
| Ánh sáng | Đều, không ngược sáng | Tránh cửa sổ phía sau người tập, tránh đèn nhấp nháy |
| Trang phục | Ôm vừa, không quá rộng, tương phản với nền | Giúp nhận khớp |

Sau khi đặt, không ai chạm vào máy, không zoom, không dịch chân máy cho đến hết buổi.

## 4. Cài đặt máy

Hai máy cài giống nhau, trước buổi quay, và không đổi giữa các take.

| Mục | Cài đặt | Lý do |
| --- | ------- | ----- |
| Độ phân giải | 1080p (1920 × 1080) | Đủ chi tiết cho nhận khớp, file vừa phải |
| Tốc độ khung hình | 30 fps cố định, khóa bằng ứng dụng quay, không để tự động | Tránh video có tốc độ khung hình thay đổi (VFR) làm sai mốc thời gian. Chỉ chuyển 60 fps nếu buổi thử cho thấy tay bị mờ |
| Codec | H.264 nếu máy cho chọn; nếu máy chỉ có HEVC thì vẫn quay | HEVC được chấp nhận nếu bước nhập file đọc được |
| Phơi sáng, lấy nét, cân bằng trắng, zoom | Khóa; zoom 1×, không dùng zoom số | Ảnh không đổi giữa chừng |
| Chống rung, HDR, làm đẹp, chế độ ban đêm | Tắt | Các chế độ này làm méo hoặc đổi hình |
| Hướng máy | Nằm ngang, khóa xoay màn hình, hai máy cùng hướng | Tránh sai thông tin xoay |
| Micro | Bật; tắt khử ồn tự động nếu có | Âm thanh là tín hiệu đồng bộ |
| Thông báo và tiết kiệm pin | Bật chế độ không làm phiền, tắt tiết kiệm pin | Tránh bị ngắt hoặc giảm hiệu năng |
| Giờ trên máy | Không dùng để ghép hai video | Giờ máy không đáng tin; việc đồng bộ dựa vào tiếng vỗ tay và đèn |

## 5. Tín hiệu đồng bộ và đoạn đứng tham chiếu

Mỗi take theo đúng thứ tự này:

1. Người điều phối bấm quay cả hai máy, để chạy ít nhất 5 giây trước khi làm tín hiệu.
2. Tín hiệu đầu: người hỗ trợ đứng trong vùng tập, vỗ tay hai lần cách nhau khoảng 1 giây; mỗi lần vỗ kèm bật đèn khoảng
   0,5 giây, giữ đèn ở tầm ngực để cả hai máy thấy. Sau đó rời vùng tập.
3. Đoạn đứng tham chiếu: người tập đứng thẳng, hai tay buông, quay mặt theo trục chính ở vị trí xuất phát, đứng yên 3–5 giây.
   Đoạn này cho tỷ lệ và góc đứng.
4. Người tập tập trọn bài (khoảng 4–6 phút).
5. Người tập về tư thế đứng; người hỗ trợ làm tín hiệu cuối giống hệt tín hiệu đầu.
6. Để máy chạy thêm ít nhất 5 giây rồi dừng cả hai máy.

Trong lúc làm tín hiệu và trong suốt take, không ai nói chuyện gần điện thoại. Không cắt, không bỏ đoạn nào.

## 6. Checkerboard (một lần mỗi buổi)

Mục đích: giữ khả năng hiệu chuẩn 3D về sau (quyết định 7 của TECH_WORKFLOW). Chỉ làm nếu thêm dưới 5 phút mỗi buổi; nếu
buổi quá chặt, bỏ qua và ghi vào phiếu.

- Quy cách: bảng cứng, in mờ (không bóng), 9 × 6 góc trong (10 × 7 ô), ô vuông 80–100 mm; với ô 100 mm bảng rộng khoảng 1 m × 0,7 m.
  Ô 25 mm là quá nhỏ: ở khoảng cách 4–5 m, một điểm ảnh ứng với khoảng 3–4 mm (ước tính, kiểm tra ở buổi thử), nên ô 25 mm chỉ
  rộng khoảng 7 điểm ảnh.
- Cách quét, khoảng 1 phút, đầu buổi sau khi đặt máy, cả hai máy quay cùng lúc: bắt đầu bằng tín hiệu đầu và kết thúc bằng
  tín hiệu cuối (mục 5); ở giữa, người hỗ trợ cầm bảng đưa qua vùng tập ở giữa, gần, xa, trái, phải và nghiêng nhẹ; mỗi vị
  trí giữ yên khoảng 2 giây; bảng luôn nằm trọn trong khung, không bị che, không bị chói.
- Đặt tên: `take_id` là `S01-CB-T01` (CB là bảng, không phải người). Cách nhập đoạn này vào hệ thống (không có người tập) do
  task P2.01 quyết; cứ giữ nguyên file.

## 7. Phiếu ghi và đặt tên file

Mỗi take có một dòng trên phiếu, ghi tay hoặc nhập bảng tính. Phiếu có tên thật đối chiếu với mã giả danh phải để ngoài kho
mã nguồn và ngoài git (do O giữ).

| Trường | Ví dụ | Ghi chú |
| ------ | ----- | ------- |
| `session_id` | `S01` | Cột `recording.session_id` |
| `participant_id` | `P03` | Mã giả danh, không phải tên; cột `participant.participant_id` |
| `take_id` | `S01-P03-T02` | **Giống nhau cho cả hai máy của một take**; cột `recording.take_id` |
| `camera_id` | `camA` hoặc `camB` | Cột `recording.camera_id` |
| Tên file gốc | `IMG_1234.MOV` | Tên do điện thoại đặt, để đối chiếu; chưa có cột |
| Vị trí máy | `A: trục chính; B: bên phải người tập` | Chưa có cột trong CSDL, giữ trên phiếu cho P2.01 |
| Độ cao máy, khoảng cách máy | `1,1 m; 4,5 m` | Như trên |
| Hướng bài | `quay mặt về phía cửa sổ` | Mô tả bằng vật mốc trong phòng; như trên |
| Ứng dụng, fps, codec | `Open Camera; 30; H.264` | Để đối chiếu với kết quả khi nhập file |
| `consent_ref` | Mã ghi trên phiếu đồng ý đã ký | Cột `participant.consent_ref` |
| Ghi chú bất thường | `take bị gián đoạn lúc 3:10` | Không xóa take lỗi, chỉ ghi chú |

Quy tắc đặt tên: `<take_id>-<camera_id>.<đuôi>`, ví dụ `S01-P03-T02-camA.mp4`.

- Chỉ dùng chữ cái không dấu, số và dấu gạch ngang; không khoảng trắng; không tên người.
- Buổi: `S` và 2 chữ số. Người tập: `P` và 2 chữ số, do người điều phối cấp theo thứ tự. Take: `T` và 2 chữ số, tăng dần cho
  từng người trong buổi.
- Chỉ đổi tên bản sao sau khi chép; không sửa nội dung file.

## 8. Xử lý file

- Chép file gốc bằng cáp hoặc đầu đọc thẻ. Không gửi qua ứng dụng nhắn tin, email hay lưu trữ đám mây: các nơi đó nén lại,
  làm mất âm thanh hoặc thông tin xoay.
- Không cắt, không chỉnh sửa, không đổi định dạng bản gốc.
- Chép xong: kiểm tra số file và dung lượng khớp với điện thoại; mở phát thử vài giây đầu của từng file, phải có hình và có tiếng.
- Chỉ xóa file trên điện thoại khi đã có hai bản chép đã kiểm tra.
- Khuôn mặt là dữ liệu cá nhân: không đăng mạng xã hội, không gửi dịch vụ bên ngoài, không cho người khác xem khi người tập
  không đồng ý chia sẻ.
- Một video chỉ vào hệ thống khi có mã giả danh và mã đồng ý (`consent_ref`). Thiếu một trong hai thì chưa nhập.

## 9. Quy trình buổi quay

Thời gian dự kiến một buổi nhóm: 1,5–2 giờ (W0). Các mốc dưới đây là ước tính, sẽ đo ở buổi quay thử.

| Phần | Thời gian dự kiến (thử) |
| ---- | ------------------------ |
| Đặt máy, cài đặt, quay thử 10 giây kiểm tra | khoảng 25 phút |
| Quét checkerboard | tối đa 5 phút |
| Mỗi người tập: 3 take, gồm tín hiệu, đoạn tham chiếu, nghỉ | khoảng 25 phút |
| Thu dọn và chép file | khoảng 10 phút |

Sau mỗi take, kiểm nhanh trong 1 phút. Quay lại ngay nếu có một trong các lỗi sau (không xóa take lỗi, chỉ ghi chú):

- Một trong hai máy không quay hoặc dừng giữa chừng.
- Tín hiệu đầu hoặc cuối không thấy đèn hay không nghe tiếng vỗ ở một trong hai file (phát lại vài giây).
- Người tập ra khỏi khung hoặc bị che.
- Có người chạm máy, zoom hoặc dịch chân máy.

## 10. Trang kiểm nhanh

Trước buổi quay:

- ☐ Pin đầy, dung lượng trống từ 32 GB mỗi máy.
- ☐ Đã cài ứng dụng quay có khóa tốc độ khung hình trên cả hai máy.
- ☐ Đã in bảng checkerboard; đã chuẩn bị đèn, băng keo, thước dây, phiếu ghi.
- ☐ Mọi người tập đã ký phiếu đồng ý; đã có mã giả danh và `consent_ref`.

Tại chỗ:

- ☐ Đánh dấu vùng tập và vị trí xuất phát; máy A trên trục chính, máy B lệch 90°.
- ☐ Cao 1,0–1,2 m, máy cân thẳng, đo và ghi khoảng cách; có đường thẳng đứng trong khung.
- ☐ 1080p, 30 fps cố định, khóa phơi sáng, lấy nét, zoom; tắt chống rung, HDR, làm đẹp; khóa hướng ngang; bật micro.
- ☐ Quét checkerboard (nếu còn thời gian).

Mỗi take:

- ☐ Bấm quay cả hai máy, chờ 5 giây.
- ☐ Tín hiệu đầu: vỗ tay hai lần kèm đèn.
- ☐ Người tập đứng tham chiếu 3–5 giây, tập bài, đứng lại.
- ☐ Tín hiệu cuối, chờ 5 giây, dừng cả hai máy.
- ☐ Kiểm nhanh; ghi phiếu (kể cả take lỗi).

Sau buổi:

- ☐ Chép file bằng cáp hoặc đầu đọc thẻ; đổi tên bản sao theo quy tắc.
- ☐ Kiểm số file, dung lượng, phát thử từng file.
- ☐ Hoàn tất phiếu; cất phiếu có tên thật ngoài kho mã nguồn.

## 11. Việc cần làm ở buổi quay thử (task P1.09)

Buổi quay thử dùng protocol này và ghi lại mọi chỗ khác đi. Cần đo và ghi:

- Độ cao máy, khoảng cách và kích thước vùng tập phù hợp với diện tích thật của bài.
- Tay có bị mờ ở 30 fps không (nếu có, thử 60 fps).
- Codec và định dạng thật của điện thoại.
- Thời gian thực tế của từng phần ở mục 9.
- Kiểm tra file thật bằng `probe_video` và `scan_pts`: tốc độ khung hình cố định, không phải VFR, thông tin xoay đúng, có âm thanh.
- Độ lệch giữa mốc âm thanh và mốc hình của tín hiệu đồng bộ.

Sau buổi thử: sửa các giá trị "(thử)" thành giá trị đo được, nâng protocol lên phiên bản 1.1, và ghi model điện thoại, hệ điều
hành, phiên bản ứng dụng vào `Docs/hardware_inventory.md` (không ghi thông tin cá nhân).

## 12. Lịch sử phiên bản

| Phiên bản | Ngày | Nội dung |
| --------- | ---- | -------- |
| 1.0 | 2026-11-15 | Bản nháp theo W0, quyết định 7 và task P1.05; chưa có buổi quay thử; khoảng cách và độ cao là giá trị khởi đầu |
