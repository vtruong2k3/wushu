# Kế hoạch Thái Cực Quyền AI v3.0

Ngày cập nhật 13/11/2026. Bản sửa sau phản biện v2.0.

## 1. Quyết định triển khai

MVP là công cụ đo hỗ trợ HLV trên video Thái Cực Quyền. HLV chọn đoạn động tác, xem ba nhóm số đo, so sánh với mẫu cùng động tác và duyệt nhận xét có bằng chứng. Bài 24 thức là phạm vi đề xuất, HLV cần xác nhận phiên bản và cách chia thức trong Phase 00.

Ba nhóm số đo đầu tiên gồm biến thiên độ cao quan sát được, độ nghiêng thân trong mặt phẳng quan sát phù hợp và đặc trưng nhịp/chuyển động liên tục. Prototype dùng Streamlit, Sports2D, file artifact và SQLite trên một máy được kiểm soát truy cập. Một người vận hành tại một thời điểm. Các quyết định này là đề xuất của bản sửa, có thể điều chỉnh qua phỏng vấn và pilot.

### Các thay đổi so với v2

| Nội dung | Quyết định v3 |
|---|---|
| Giá trị người dùng | Phỏng vấn 3–5 HLV trước triển khai, đo workflow hiện tại |
| Phân đoạn | HLV chia đoạn và chọn mẫu ở MVP |
| Đo kỹ thuật | Ba nhóm metric có điều kiện quan sát cụ thể |
| Quay dữ liệu | Hai camera từ đợt đầu, kiểm tra đồng bộ đầu/cuối |
| Skeleton | HALPE_26 cho baseline, lưu joint mapping có phiên bản |
| Nghiệm thu | Audit nhãn người, error budget và coverage trước khi khóa threshold |
| Nền tảng | Streamlit, SQLite, file artifacts, một job tại một thời điểm |
| Dữ liệu | Ngân sách cụ thể theo người, buổi quay, giờ annotation và giờ HLV |
| Nguồn ngoài | TaiChi-AQA là ứng viên có điều kiện, dữ liệu tự quay là nguồn chủ động |
| Thương mại | Kiểm kê riêng code, weights, dataset và phụ thuộc body model |
| Mở rộng | Action recognition, SaaS, scoring, 3D có gate và ngân sách riêng |

Tài liệu là kế hoạch xây dựng. Repo/model chưa được chạy trên máy người dùng, dữ liệu chưa được thu thập, chi phí là kịch bản tính toán và nhân sự chưa được xác nhận bằng tên thật.

## 2. Kiểm chứng nhu cầu trước khi chọn tính năng

### 2.1. Người sử dụng và giả thuyết trả tiền

Người sử dụng chính là HLV dạy bài quyền và quản lý tiến bộ của học viên. Người trả tiền giả định là HLV hoặc CLB. Học viên nhận báo cáo thông qua HLV. Đây là giả thuyết cần kiểm chứng bằng các buổi làm việc thực tế.

Giả thuyết giá trị ban đầu là giảm thời gian chuẩn bị nhận xét, tăng khả năng chỉ ra thời điểm cần sửa và so sánh cùng động tác giữa hai buổi tập. Đo số phút phân tích một đoạn, số lần phải tua, độ tự tin của HLV và số nhận xét có thể giải thích cho học viên.

### 2.2. Kịch bản 3–5 buổi phỏng vấn

Mỗi buổi 45–60 phút, ưu tiên HLV ở ít nhất hai môi trường giảng dạy. Dùng một video thật do người tham gia được quyền chia sẻ.

- [ ] D00.1 Hỏi HLV đã phân tích video gần nhất như thế nào, dùng công cụ nào và mất bao lâu.
- [ ] D00.2 Quan sát họ chọn 3 đoạn cần sửa, ghi thao tác và thời gian.
- [ ] D00.3 Hỏi thông tin nào khiến họ thay đổi quyết định huấn luyện.
- [ ] D00.4 Cho xem ba bản phác số đo, yêu cầu xếp mức hữu ích và nêu trường hợp gây hiểu lầm.
- [ ] D00.5 Xác định người chi trả, ngân sách hiện có và điều kiện thử trả phí.
- [ ] D00.6 Mời hai HLV tham gia pilot, ghi thời gian có thể cam kết mỗi tuần.

Đầu ra là bảng nhu cầu, bằng chứng workflow, top 3 vấn đề, lịch pilot và giả thuyết thương mại. Trường hợp chưa có hai HLV đồng hành, giảm quy mô xuống POC đo hình học với một người phản biện và ghi giới hạn kiểm chứng.

### 2.3. Công cụ đối chiếu

Kinovea có slow motion, annotation, đo và so sánh hai video. Onform là nền tảng video coaching. Chọn workflow hiện tại của HLV và Kinovea làm đối chứng trong thử nghiệm thời gian. Khác biệt cần chứng minh của dự án là số đo tự động theo đoạn Thái Cực Quyền và báo cáo có bằng chứng. Nguồn [N8], [N9].

### 2.4. Pilot về giá trị

Cho HLV xử lý cùng loại nhiệm vụ bằng workflow cũ và prototype, đảo thứ tự giữa các clip để giảm hiệu ứng học. Mỗi người đánh giá ít nhất 6 đoạn, tổng khoảng 12–20 đoạn. Ghi thời gian, nhận xét hữu ích, lỗi phải sửa và mức tin cậy. Mục tiêu kinh doanh đề xuất là giảm khoảng 25% thời gian review mà chất lượng phản hồi được HLV chấp nhận. Khóa mục tiêu sau discovery, trước thử pilot. Giá trị âm dẫn tới sửa workflow hoặc metric trước khi đầu tư nền tảng.

## 3. Phạm vi sản phẩm và kiến trúc

### 3.1. Bàn giao MVP

1. Mở video từ máy hoặc upload nội bộ, đọc metadata và tạo proxy khi cần.
2. Chọn VĐV, chọn góc camera, cắt đoạn bằng start/end timestamp.
3. Chạy pose với quality mask, hiển thị keypoint và vùng thiếu bằng chứng.
4. Xem ba nhóm metric cùng điều kiện áp dụng.
5. Chọn reference cùng động tác/biến thể và so sánh cạnh nhau.
6. HLV thêm/sửa/xác nhận nhận xét, xuất JSON/CSV/HTML có clip bằng chứng.
7. Lưu phiên bản số đo, config và review để mở lại được.

### 3.2. Thiết kế tối thiểu

| Thành phần | Lựa chọn | Trách nhiệm |
|---|---|---|
| UI | Streamlit, ba tab Video / Số đo / Báo cáo | Nhập đoạn, xem kết quả, review |
| Video | FFmpeg và ffprobe | Metadata, proxy, timestamp map |
| Pose | Sports2D + HALPE_26 | Keypoint và confidence |
| Measurement | Python/NumPy/SciPy | Feature, mask, summary và evidence |
| So sánh | Mốc HLV, constrained DTW khi phù hợp | Đồng bộ đoạn cùng động tác |
| Metadata | SQLite | Video, đoạn, run, review và version |
| Artifacts | Thư mục theo UUID | Raw video, pose, metric, report |
| Execution | Một subprocess/job, file manifest | Tiến độ, kết quả, lỗi và chạy lại |

Dùng atomic write cho kết quả và trạng thái. Một run được xác định bằng video hash, segment revision, model checksum và config hash. Chạy lại cùng cấu hình có thể dùng cache hợp lệ. Review thủ công nằm ngoài artifact model để bảo toàn khi rerun. Worker hỏng báo failed và cho chạy lại từ stage hoàn tất. Đây là mức phục hồi dữ liệu cần cho prototype.

Upload resumable, đa tổ chức, dashboard Admin, distributed queue và registry server được đưa vào phase sản phẩm hóa. Model registry MVP là manifest có schema và checksum. Pilot từ xa dùng môi trường có kiểm soát truy cập, phân quyền và cơ chế bảo vệ phù hợp với mô hình triển khai trước khi nhận video người dùng.

### 3.3. Hợp đồng dữ liệu

| Entity | Trường tối thiểu |
|---|---|
| participant | ID giả danh, consent reference, trình độ tự khai/HLV xác nhận |
| recording | session ID, camera ID, take ID, hash, FPS/timebase, nguồn và quyền |
| sync | camera pair, offset, drift, residual, phương pháp xác nhận |
| segment | routine version, action, side, start/end, view, reviewer, revision |
| pose | model/checkpoint, skeleton version, coordinates, timestamps, visibility |
| metric | metric version, units, valid intervals, missing reason, result |
| finding | criterion version, evidence interval, metric IDs, HLV decision |
| report | run IDs, segment/review revision, snapshot time |

## 4. Repo, model và skeleton

### 4.1. Lựa chọn theo vai trò

| Thành phần | Vai trò | Điều kiện sử dụng |
|---|---|---|
| Sports2D | Baseline pose và góc 2D | Chạy video pilot và khóa phiên bản |
| MMPose/RTMPose | Đối chứng hoặc thay pose nếu benchmark tốt hơn | Khớp layout và checkpoint |
| QAQA | Tham khảo căn chỉnh chuỗi và DTW | Thay reference bằng mẫu Taiji, kiểm tra license |
| MMAction2 | Nhận diện động tác khi mở rộng | Có nhãn theo động tác và split đủ người |
| TaiChi-AQA | Nguồn dữ liệu chuyên Taiji có thủ tục xin truy cập | Xác minh dữ liệu và quyền được cấp |
| GVHMR | Thử nghiệm tái dựng 3D ở phase riêng | Audit cả code, weights, body model và dữ liệu |
| KungFuAthleteBot | Nguồn motion nghiên cứu tùy trường hợp | Lọc mẫu người phù hợp, kiểm tra từng asset |

Nguồn repo [R1]–[R7]. Tài liệu công khai chưa xác minh được một checkpoint chấm toàn bộ Thái Cực Quyền phù hợp dự án. Các repo ngoài miền chỉ có vai trò tham khảo phương pháp khi có nhu cầu cụ thể.

### 4.2. Skeleton được chọn

Cấu hình demo Sports2D công bố `Body_with_feet` dùng HALPE_26 mặc định, có lựa chọn whole-body. MVP chốt HALPE_26 làm schema native và lưu danh sách tên/thứ tự khớp từ phiên bản thực tế. Nguồn [N1].

- [ ] S01 Kiểm tra đủ gót, mũi chân và mắt cá trong output thực.
- [ ] S02 Tạo manifest skeleton, coordinate convention, mirror và joint mapping.
- [ ] S03 Test trái/phải khi người quay lưng, xoay người và chân che nhau.
- [ ] S04 Ghi confidence/missing mask của từng keypoint.
- [ ] S05 Nếu thử COCO-133, đánh giá riêng bàn tay và bàn chân trước khi đổi schema.

Phân tích chưởng/quyền/câu thủ cần annotation và chất lượng hình ảnh bàn tay riêng. Whole-body là nhánh thử nghiệm theo nhu cầu HLV. Bổ sung nhiều keypoint làm tăng yêu cầu kiểm chứng chất lượng.

## 5. Quy trình quay hai camera từ đợt đầu

### 5.1. Cấu hình quay đề xuất

Hai điện thoại/camera đặt cố định ở hai hướng khác nhau khoảng 60–90 độ, thấy toàn thân và khoảng di chuyển. HLV chọn vị trí sau khi thử trọn bài. Đặt máy cùng chiều cao tương đối, tránh camera nghiêng hoặc cắt bàn chân. Ưu tiên 1080p, 30 hoặc 60 fps ổn định, khóa zoom, kiểm tra ánh sáng và quần áo tương phản nền.

Ghi camera model, resolution, FPS thực, timebase, rotation, exposure nếu có. Đánh dấu vị trí máy và vùng tập để lặp lại. Quay đoạn đứng tham chiếu và dấu chuẩn kích thước trong mặt phẳng phù hợp. Hình chiếu thay đổi khi người di chuyển theo chiều sâu được ghi vào quality gate.

### 5.2. Đồng bộ

- [ ] C01 Ghi tiếng vỗ tay và tín hiệu nhìn thấy ở đầu mỗi take.
- [ ] C02 Lặp tín hiệu cuối take để đo clock drift.
- [ ] C03 Lưu offset/drift, kiểm tra bằng mốc chuyển động chung.
- [ ] C04 Đặt mục tiêu residual một frame cho so sánh slow motion, báo số đo đạt được.
- [ ] C05 Nếu residual lớn, hiển thị hai video với mốc HLV xác nhận và hạn chế ghép metric theo thời gian.
- [ ] C06 Lưu hai file gốc, PTS mapping và camera manifest.

Hai camera giúp chọn góc quan sát cho từng metric. Để tái dựng 3D cần thêm hiệu chuẩn intrinsics/extrinsics, kiểm tra đồng bộ chính xác và benchmark. Nếu có khả năng, quay bảng hiệu chuẩn ngay đợt đầu để giữ lựa chọn nghiên cứu sau. Đồng bộ thô chỉ hỗ trợ review và tạo dữ liệu ban đầu.

### 5.3. Lựa chọn đoạn quan sát

HLV chọn trước đoạn phù hợp để đo từng metric. Mỗi interval có camera_id, view_category, orientation_change, occlusion và perspective_shift. Khi đổi camera, tạo đoạn đo mới để tránh ghép trực tiếp hai hệ tọa độ ảnh khác nhau.

## 6. Ba nhóm metric MVP

Đây là thiết kế chỉ số đề xuất để kiểm chứng trên video, cần HLV định nghĩa phạm vi theo thức và phong cách. Hệ thống báo giá trị hình học, chất lượng quan sát và reference tương ứng.

### 6.1. Biến thiên độ cao quan sát được

Dùng midpoint hai hông làm đại diện vị trí vùng chậu trong ảnh. Sau sửa độ nghiêng camera hợp lệ, đo `P95(y_hip) - P5(y_hip)` chia cho scale tham chiếu cố định của take. Ghi thêm profile theo thời gian và biến thiên đầu nếu keypoint đủ tin cậy. Scale lấy từ đoạn tham chiếu kiểm tra được, giữ cố định khi phân tích để tránh triệt tiêu biến thiên cần đo.

Điều kiện gồm camera cố định, thay đổi chiều sâu nhỏ, pose đủ rõ và đoạn HLV xác nhận kỳ vọng độ cao tương đối ổn định. Tấn thấp, đổi tấn hoặc động tác có thay đổi độ cao chủ đích cần reference riêng. Di chuyển chiều sâu, camera tilt và keypoint drift có thể tạo biến thiên giả.

Output gồm normalized range, khoảng hợp lệ, coverage và thời điểm biến thiên. HLV xác nhận biến thiên nào cần phản hồi. Không tự áp ngưỡng chung cho toàn bài.

### 6.2. Độ nghiêng thân theo mặt phẳng quan sát

Trục thân từ midpoint hông tới midpoint vai. Đo góc với phương đứng đã hiệu chỉnh của ảnh trong camera có mặt phẳng quan sát phù hợp. Báo median, P95 và duration vượt ngưỡng do HLV đặt cho đúng đoạn, nếu ngưỡng đã được kiểm chứng.

Động tác xoay và nghiêng có chủ đích cần nhãn riêng. Output có `view`, `orientation_valid` và missing reason. Angle được hiểu là góc chiếu trong mặt phẳng camera. Hai góc quay cho phép lựa chọn bằng chứng phù hợp từng đoạn.

### 6.3. Nhịp và độ liên tục

Tính vận tốc keypoint đã lọc theo timestamp, chuẩn hóa bằng scale cố định, tổng hợp theo nhóm tay/hông/chân được chọn. Lưu duration gốc, profile tốc độ, số và độ dài các interval tốc độ thấp. Threshold và minimum pause duration được xác định từ nhãn HLV cho cùng loại động tác.

Chuyển động chậm liên tục, kết thúc thức và khoảng dừng có chủ đích được phân biệt qua nhãn đoạn. Lọc phải ghi tham số và kiểm tra tác động lên pause, giữ raw pose để đối soát. DTW giúp so hình dạng chuyển động, còn nhịp đánh giá trên trục thời gian gốc.

### 6.4. Metric tiếp theo theo nhu cầu

Độ rộng tấn và căn chỉnh gối/bàn chân chỉ đưa vào sau khi đo chất lượng feet và điều kiện view. Quy tắc gối so với mũi chân cần rubric theo động tác, hình thể và góc quay. Mỗi tiêu chí do HLV xác nhận về mục tiêu huấn luyện, tránh biến một câu hướng dẫn thành ngưỡng lỗi phổ quát. Hệ thống không suy luận lực, trọng tâm sinh cơ học hay nguy cơ chấn thương chỉ từ các proxy này.

## 7. Dữ liệu, số người và ngân sách giờ

### 7.1. Pilot có thể bắt đầu nhỏ

Kịch bản cơ sở gồm 6 người tập, 2 buổi/người, 3 lần thực hiện/buổi, 2 camera đồng thời. Tổng 36 performance, 72 file video. Giả định 6 phút/performance tạo 216 phút diễn tập và 432 phút video hai góc. Đây là ngân sách giả định, chưa phải thời lượng chuẩn của bài.

Chọn 120 đoạn từ các performance trên, khoảng 10–30 giây/đoạn, phân bố nhiều người và điều kiện quan sát. HLV chia đoạn thủ công. Chọn 200 frame phân tầng để rà keypoint, trong đó 50 frame được hai người đánh dấu độc lập. Nếu chỉ tuyển được 3–4 người, dùng kết quả như feasibility pilot và ghi rõ giới hạn khái quát.

### 7.2. Ngân sách giờ chuyên môn

| Công việc | Công thức dự trù | Person-hours |
|---|---|---:|
| Phỏng vấn HLV | 4 người × 1 giờ | 4 |
| Chốt rubric và mẫu | 2 HLV × 2 giờ | 4 |
| Hỗ trợ quay | 6 buổi nhóm × 1 giờ HLV | 6 |
| Chấm độc lập 120 đoạn | 120 × 3 phút × 2 HLV / 60 | 12 |
| Xử lý bất đồng | 30 đoạn × 4 phút × 2 HLV / 60 | 4 |
| Pilot workflow | 2 HLV × 2 giờ | 4 |
| Dự phòng chuyên môn | 20% × 34 giờ | 6,8 |
| **Tổng HLV** | | **40,8** |

Giả định 3 phút/đoạn phải đo lại sau 20 đoạn đầu. Chưa tính đồng thời các góc quay như hai mẫu độc lập. Người đứng trước máy cần khoảng 12 participant-hours theo giả định 1 giờ/buổi. Hai người hỗ trợ quay × 6 buổi × 2 giờ tạo 24 operator-hours, phân bổ vào công ML/full-stack nếu họ trực tiếp thực hiện.

Ngân sách annotation dự kiến thêm 16 giờ chuẩn bị/chia đoạn, 200 frame × 3 phút = 10 giờ và 4 giờ QA, tổng 30 giờ. Thời gian gán nhãn keypoint được hiệu chỉnh sau thử 20 frame.

### 7.3. Minh họa chi phí

| Khoản | Đơn giá giả định | Thành tiền |
|---|---:|---:|
| HLV | 40,8 giờ × 300.000 đồng | 12.240.000 đồng |
| Annotator | 30 giờ × 100.000 đồng | 3.000.000 đồng |
| Hỗ trợ người tập | 12 buổi-người × 150.000 đồng | 1.800.000 đồng |
| Giá đỡ, lưu trữ, hậu cần | Khoản dự trù | 3.000.000 đồng |
| Tổng trực tiếp pilot | | 20.040.000 đồng |
| Dự phòng tiền mặt 15% | | 3.006.000 đồng |
| **Ngân sách trực tiếp minh họa** | | **23.046.000 đồng** |

Đây là kịch bản tính toán, chưa có báo giá hoặc cam kết tuyển người. Chưa bao gồm lương kỹ sư, mua camera/GPU, tư vấn pháp lý hoặc giấy phép thương mại. Dự phòng tiền mặt và giờ chuyên môn phục vụ hai loại bất định khác nhau, điều chỉnh nếu đội chọn chỉ dùng một khoản dự phòng.

### 7.4. Quy mô khi mở recognition/scoring

Sau pilot, lập đợt riêng cho 300–800 clip nhận diện và 200–400 đoạn chấm chất lượng theo mục tiêu cần train. Ước lượng HLV theo `số đoạn × phút/đoạn × số người / 60`, cộng adjudication. Tuyển thêm người tập trước khi tăng hàng loạt clip từ cùng người. Tách tập theo người, session và performance, giữ cả hai camera cùng split.

## 8. Độ thống nhất nhãn và tiêu chí nghiệm thu

### 8.1. Audit người gán nhãn

Hai HLV gán độc lập 20 đoạn đầu để chỉnh hướng dẫn, rồi đánh giá 100 đoạn còn lại theo rubric đã chốt. Giữ nhãn gốc, nhãn sau adjudication và lý do thay đổi. Mẫu đánh giá độ lặp lại gồm một phần đoạn được HLV chấm lại sau khoảng nghỉ, ẩn kết quả trước.

| Đối tượng | Cách đánh giá |
|---|---|
| Mốc thời gian | Boundary difference, khoảng ranh giới HLV chấp nhận |
| Nhận xét loại | Agreement theo class, confusion và kappa/alpha phù hợp |
| Nhận xét thứ bậc | Weighted agreement, phân bố bất đồng |
| Số đo/score liên tục | MAE, bias, giới hạn đồng thuận, ICC với mô hình được nêu rõ |
| Keypoint | Sai lệch landmark giữa annotator, error theo khớp/view |

Mức đồng thuận người–người là mốc tham chiếu cho độ mơ hồ và error budget. Model có thể khớp nhãn tổng hợp tốt hơn một annotator đơn lẻ, nên mức đồng thuận không được xem như giới hạn tuyệt đối. Chất lượng hình học phải đối chiếu annotation hình học độc lập, còn tính hữu ích chuyên môn đối chiếu rubric HLV.

### 8.2. Khóa threshold sau audit

Mỗi metric có một record gồm intended use, supported views, gold annotations, human variability, smallest useful change, measurement error, minimum valid duration và threshold đã được ký duyệt. Khóa record trước holdout pilot. Nếu sai số tương đương hoặc lớn hơn thay đổi HLV muốn thấy, điều chỉnh phạm vi đo hoặc cách quay.

Các mức Macro-F1, Event F1 và Segment F1 của v2 trở thành mục tiêu nghiên cứu cho phase tự động nhận diện. MVP phân đoạn tay được đánh giá theo độ chính xác timestamp và chi phí thao tác.

### 8.3. Coverage có mẫu số rõ ràng

Báo ba tỷ lệ cho mỗi metric và mỗi camera.

1. Tỷ lệ thời gian của bài thuộc điều kiện chuyên môn/view đủ để đo.
2. Tỷ lệ frame có pose đạt chất lượng trong các đoạn đủ điều kiện.
3. Tỷ lệ thời gian toàn bài thực sự tạo được metric, cùng lý do loại.

Hai camera được báo riêng trước, tỷ lệ kết hợp tính trên hợp các interval hợp lệ. Ghi rõ có đủ coverage trên những đoạn HLV cần sửa hay không. Mục tiêu coverage được chốt từ dữ liệu pilot, tránh đặt 90% toàn bài khi chưa biết phân bố hướng người.

### 8.4. Nghiệm thu MVP

- [ ] Timestamp trên proxy và video nguồn được kiểm tra trong sai số một frame đã định nghĩa.
- [ ] Từng metric có benchmark hình học và kiểm tra độ lặp lại.
- [ ] HLV xác nhận tối thiểu các điều kiện sử dụng được và trường hợp cần abstain.
- [ ] Báo cáo nêu valid duration, view và reference cho mỗi kết luận.
- [ ] Chạy lại giữ revision HLV và snapshot báo cáo cũ.
- [ ] Pilot cho thấy giá trị workflow theo tiêu chí đã khóa ở Phase 00.

## 9. License và dữ liệu cá nhân

### 9.1. Ma trận kiểm tra sớm

| Asset | Bằng chứng hiện có | Hành động |
|---|---|---|
| Sports2D code | LICENSE hiện tại là BSD-3-Clause | Pin commit, giữ thông báo, audit weights/phụ thuộc riêng |
| HALPE/RTMPose weights | Cấu hình có đường dẫn weights | Ghi model card, file license và quyền phân phối của đúng bản tải |
| QAQA | Repo phương pháp tham khảo | Kiểm kê license và dataset trước reuse |
| TaiChi-AQA | Có quy trình yêu cầu dữ liệu | Xác nhận quyền nghiên cứu/thương mại bằng điều kiện được cấp |
| TaiForm | Mẫu và phạm vi truy cập cần kiểm tra | Ghi quyền asset cụ thể trước tích hợp |
| GVHMR/KungFuAthlete | Có phụ thuộc/assets nghiên cứu cần audit | Tách license code, checkpoint, body model, input và output |
| SMPL-Model/SMPL-X | Điều khoản nghiên cứu phi thương mại và kênh cấp phép thương mại | Xin quyền phù hợp hoặc chọn đường kỹ thuật khác |
| SMPL-Body | Có giấy phép riêng cho subset body | Đối chiếu chính xác asset và chuỗi nguồn gốc |
| Video tự quay | Quyền theo thỏa thuận với người tham gia | Ghi phạm vi phân tích, train, chia sẻ và thời hạn |

Sports2D code BSD-3-Clause được kiểm tra ở [N2]. SMPL-Model và SMPL-Body có điều khoản khác nhau, không suy ra quyền từ tên chung SMPL [N3], [N4]. License của phần code không tự cấp quyền mọi asset mà pipeline sử dụng. Trạng thái TaiChi-AQA cần được xác nhận qua điều kiện cấp dữ liệu, tránh kết luận chỉ cho nghiên cứu khi chưa đọc thỏa thuận.

### 9.2. Yêu cầu vận hành dữ liệu tại Việt Nam

Căn cứ rà soát hiện hành gồm Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP, cùng có hiệu lực từ 01/01/2026. Đội cần đối chiếu toàn văn và phạm vi hoạt động cụ thể khi triển khai. Nguồn [N5], [N6].

Chủ dự án phụ trách chốt data flow và người chịu trách nhiệm rà soát. Hồ sơ pilot ghi mục đích xử lý, dữ liệu thu thập, người được xem, thời hạn lưu, cách yêu cầu xóa/rút lại sự đồng ý, nơi lưu và dịch vụ bên ngoài. Quyền dùng video để huấn luyện được ghi tách khỏi quyền phân tích buổi tập.

Nếu tuyển người chưa thành niên, bổ sung bước xác định yêu cầu pháp lý theo độ tuổi, chủ thể đồng ý và người giám hộ trước quay. Chi tiết thủ tục này cần được người phụ trách rà soát theo văn bản hiện hành. MVP chạy local giúp thu hẹp luồng chia sẻ, nhưng vẫn cần quản lý quyền truy cập, bản sao và xóa dữ liệu.

## 10. Phase triển khai MVP thu gọn

Owner dùng vai trò để giao việc ngay, tên người cụ thể được điền trong Phase 00. Mỗi task 0,5–2 ngày công, mỗi phase có artifact nghiệm thu. Nhãn A là ML/CV, B là full-stack, H là HLV, O là chủ dự án. Ngày công chuyên môn H được tính riêng trong mục 7.

### Phase 00 — Discovery, rubric và nguồn lực · 3–4 ngày công A+B

- [ ] P00.01 O tổ chức 3–5 buổi phỏng vấn, ghi baseline workflow.
- [ ] P00.02 H chọn 3 loại đoạn và xác nhận bài/biến thể, mục tiêu đo.
- [ ] P00.03 A lập protocol hai camera và thử một take trọn bài.
- [ ] P00.04 O điền tên owner, danh sách người tập, lịch HLV và đơn giá thực.
- [ ] P00.05 A+B lập ma trận license/data flow, inventory phần cứng.
- [ ] P00.06 O khóa mục tiêu pilot về thời gian/chất lượng review.

Đầu ra gồm scope một trang, interview notes, protocol, budget và calendar. Gate G00 đạt khi có nhu cầu cụ thể, video thử và lịch chuyên gia khả thi. Nếu tuyển người chưa đủ, điều chỉnh quy mô ngay.

### Phase 01 — Pose, góc quay và kiểm chứng khả thi · 4–6 ngày công

- [ ] P01.01 A chạy Sports2D trên 5 clip, pin environment/checkpoint.
- [ ] P01.02 A kiểm tra HALPE_26, chân/tay che khuất và đổi hướng.
- [ ] P01.03 A đo offset/drift hai camera và tạo timestamp manifest.
- [ ] P01.04 A+H đánh dấu view hợp lệ cho ba metric trên các đoạn mẫu.
- [ ] P01.05 B dựng notebook/Streamlit thử video, pose overlay và chọn đoạn.
- [ ] P01.06 A+H đo 20 frame/20 đoạn thử để kiểm tra effort annotation.

Gate G01 đạt khi ít nhất một nhóm metric tạo giá trị quan sát được trên đoạn HLV chọn, có tỷ lệ coverage và lỗi đo ban đầu. Nếu chất lượng không đạt, chỉnh góc quay/pose hoặc thu hẹp mục tiêu trước train model mới.

### Phase 02 — Quay pilot và audit nhãn · 4–6 ngày công kỹ thuật

Giờ HLV/annotation bổ sung theo mục 7, cần khoảng 1–2 tuần lịch tùy tuyển người.

- [ ] P02.01 A+O tổ chức 6 buổi nhóm, lưu 36 performance/72 file theo kịch bản cơ sở.
- [ ] P02.02 A kiểm kê hashes, consent, camera, take và sync.
- [ ] P02.03 H chia đoạn, chọn reference và gán nhãn độc lập.
- [ ] P02.04 A điều phối keypoint audit với annotator, phân tầng view/occlusion.
- [ ] P02.05 A+H đo agreement, adjudicate và chốt error budget.
- [ ] P02.06 A khóa holdout theo người, giữ mọi góc/phiên của người đó cùng nhóm.

Gate G02 đạt khi nhãn, quyền dữ liệu, quality masks và tiêu chí nghiệm thu có thể truy vết. Dataset nhỏ dùng leave-one-person-out cho phát triển khi phù hợp, giữ holdout cuối riêng để hạn chế chọn model theo test.

### Phase 03 — Ba nhóm metric và so sánh mẫu · 6–8 ngày công

- [ ] P03.01 A viết normalization, camera tilt correction có điều kiện và valid masks.
- [ ] P03.02 A triển khai hip-height range, raw profile và quality reason.
- [ ] P03.03 A triển khai trunk angle theo view đã duyệt.
- [ ] P03.04 A triển khai speed/pause profile, giữ duration gốc.
- [ ] P03.05 A+H thiết lập reference cùng động tác và mốc tương ứng.
- [ ] P03.06 A thử constrained DTW nếu thêm giá trị, lưu warp và giới hạn.
- [ ] P03.07 A đối chiếu manual measurement và kiểm tra repeatability.
- [ ] P03.08 B nối output với UI, hiển thị units/coverage/evidence.

Gate G03 đạt khi từng metric được bật có sai số phù hợp intended use, nhãn đúng mặt phẳng quan sát và xử lý thiếu dữ liệu rõ ràng. Metric chưa đạt được giữ ở trạng thái thử nghiệm.

### Phase 04 — Review và báo cáo dùng được · 4–6 ngày công

- [ ] P04.01 B hoàn thiện ba tab và chọn cặp camera/reference.
- [ ] P04.02 B lưu segment/review revision trong SQLite.
- [ ] P04.03 B thêm run manifest, atomic artifacts và phục hồi stage.
- [ ] P04.04 B tạo nhận xét template từ metric đã đủ điều kiện.
- [ ] P04.05 B export JSON/CSV/HTML với timestamp bằng chứng.
- [ ] P04.06 A+B kiểm tra rerun, video hỏng, missing joints và backup/restore.

Gate G04 đạt khi một HLV xử lý trọn workflow và mở lại chính xác nhận xét đã duyệt. Báo cáo có snapshot để các lần sửa sau được truy vết.

### Phase 05 — Pilot giá trị và quyết định sản phẩm · 3–5 ngày công

- [ ] P05.01 O+H chạy thử đối chiếu workflow trên clip holdout, đảo thứ tự công cụ.
- [ ] P05.02 A đo error, coverage và sai nhận xét theo người/view.
- [ ] P05.03 B đo thời gian thao tác, lỗi UX và thời gian xử lý.
- [ ] P05.04 O kiểm tra ý định dùng lại, người trả tiền và điều kiện thử trả phí.
- [ ] P05.05 A+B sửa ba vấn đề gây mất giá trị lớn nhất.
- [ ] P05.06 O ghi quyết định tiếp tục, sửa phạm vi hoặc tạm dừng một metric.

Gate G05 gồm bằng chứng giá trị, chất lượng và chi phí vận hành. Đầu ra là prototype có thể dùng trong pilot cùng báo cáo quyết định mở rộng.

## 11. Các phase mở rộng có điều kiện

| Phase | Chủ trì | Công việc nhỏ cần làm | Điều kiện bắt đầu |
|---|---|---|---|
| E01 — Action/segmentation | A+H | Chốt ontology; tuyển thêm người; gán 300–800 clip; train STGCN++/PoseC3D; đo biên thời gian | HLV thấy chia đoạn tay là bottleneck và dữ liệu đủ |
| E02 — Platform | B | FastAPI/PostgreSQL; queue; resumable upload nếu cần; phân quyền; multi-user; monitoring | Có nhiều người dùng thực hoặc nhiều job đồng thời |
| E03 — Learned AQA | A+H | Rubric score; audit agreement; chấm 200–400 đoạn; regression baseline; calibration | Chất lượng nhãn đủ cho quyết định dự kiến |
| E04 — Rules/referee | A+B+H | Xác định giải/edition; criterion map; evidence; test rules; review ledger | Có yêu cầu thi đấu và chuyên gia xác nhận |
| E05 — 3D | A | Audit license; hiệu chuẩn; sync chính xác; reconstruction; ground-truth validation | Hai camera 2D còn thiếu giá trị cốt lõi cần đo |
| E06 — Longitudinal/coach | A+B | So sánh session cùng điều kiện; trend; evidence-bound explanations | Có dữ liệu nhiều buổi và nhu cầu được xác nhận |
| E07 — Nội dung khác | O+A+H | Ontology/rubric/reference/data mới; benchmark riêng | Thái Cực Quyền pilot đã ổn định |

Mỗi extension có đề xuất ngân sách riêng. Thu hai camera từ MVP giúp giữ dữ liệu cho nghiên cứu sau, nhưng chất lượng tái dựng vẫn phải kiểm chứng theo calibration và sync thực tế.

## 12. Lịch, nhân sự và quyết định mở rộng

### 12.1. Phân bổ trách nhiệm

| Vai trò | Nhiệm vụ | Người cụ thể |
|---|---|---|
| O — Chủ dự án | Scope, ngân sách, tuyển người, quyết định kinh doanh | Điền tại P00.04 |
| A — ML/CV | Pose, dữ liệu, metrics, benchmark | Điền tại P00.04 |
| B — Full-stack | Streamlit, storage/revision, report | Điền tại P00.04 |
| H1/H2 — HLV | Rubric, nhãn độc lập, adjudication, pilot | Điền tại P00.04 |
| Annotator | Landmark và metadata theo guide | Điền tại P00.04 |

### 12.2. Effort và lịch thực tế

Tổng Phase 00–05 là 24–35 ngày công A+B, cộng thời gian HLV và annotation. Dự trù thêm 25% engineering cho tích hợp/lỗi, thành khoảng 30–44 ngày công. Với hai kỹ sư và lịch dữ liệu thuận lợi, mục tiêu lịch là 5–7 tuần. Một người có thể cần 7–10 tuần hoặc hơn. Đội phải cập nhật lịch sau P01 và 20 đoạn annotation đầu.

| Tuần đề xuất | Việc chính | Phụ thuộc |
|---|---|---|
| 1 | Discovery, thử pose và test quay | HLV/video có sẵn |
| 2 | Quay dữ liệu, skeleton/sync, UI tối thiểu | G00, G01 |
| 3 | Annotation audit và triển khai metric | HLV độc lập có lịch |
| 4 | So sánh mẫu, report, sửa metric | Error budget đã chốt |
| 5 | Holdout pilot và đánh giá giá trị | G03, G04 |
| 6–7 | Dự phòng tuyển người, annotation và sửa lỗi | Theo kết quả đo |

### 12.3. Công thức chi phí toàn dự án

Chi phí = engineering person-days × đơn giá thực + HLV + annotation + hỗ trợ quay + thiết bị bổ sung + compute/storage + quyền sử dụng/pháp lý khi áp dụng. Ví dụ 30–44 ngày công × 2 triệu đồng/ngày tương đương 60–88 triệu đồng engineering. Cộng ngân sách trực tiếp minh họa 23,046 triệu đồng thành khoảng 83–111 triệu đồng, trước những khoản chưa có báo giá. Dùng effort thực tế để hiệu chỉnh thay vì coi đây là giá thị trường.

### 12.4. Rủi ro và nhánh xử lý

| Vấn đề | Dấu hiệu đo được | Hành động |
|---|---|---|
| Thiếu người tập | Số người thấp, nhiều clip cùng người | Giữ feasibility scope, bổ sung người trước training lớn |
| Thiếu giờ HLV | Backlog review tăng | Giảm số đoạn/metric, ưu tiên quyết định cần thiết |
| View quá hạn chế | Đoạn HLV cần sửa thường thiếu dữ liệu | Chỉnh camera/protocol hoặc mở E05 nếu có căn cứ |
| Metric vô ích | HLV vẫn cần cùng thời gian review | Sửa workflow/metric trước platform |
| Nhãn mơ hồ | Agreement thấp theo một criterion | Làm rõ rubric hoặc giữ nhận xét mô tả |
| Dependency/license | Asset chưa rõ quyền hoặc khó chạy | Chọn baseline thay thế, timebox audit |
| Sai timestamp/skeleton | So sánh lệch, khớp đổi bên | Test contract và quality flag trước phát hành |

## 13. Checklist thực thi và hợp đồng nghiệm thu

### Hai tuần đầu

- [ ] Có 3–5 interview notes và hai HLV dự kiến tham gia.
- [ ] Scope ghi rõ bài/biến thể và ba metric cần thử.
- [ ] Có ít nhất một take quay hai góc, sync đầu/cuối và metadata.
- [ ] Sports2D chạy được trên 5 clip, lưu commit/checkpoint/runtime.
- [ ] HALPE_26 được kiểm tra chân, trái/phải và visibility.
- [ ] Đo effort thực tế trên 20 đoạn và 20 frame.
- [ ] Ngân sách được thay bằng đơn giá/nhân sự thực tế khi có.
- [ ] Streamlit chọn đoạn và xem skeleton hoạt động.

### Definition of Done mỗi task

Artifact có đường dẫn, owner, input/output, version và kết quả kiểm tra. Task đo kỹ thuật có điều kiện áp dụng, units, coverage và failure examples. Task UX có thao tác đầu-cuối với video thực. Task dữ liệu có provenance, split và quyền sử dụng. Báo cáo chỉ chứa những metric đang đạt gate cùng bằng chứng tương ứng.

## 14. Ánh xạ khung 18 engine để truy vết

| Engine gốc | Vị trí trong v3 |
|---|---|
| Video acquisition | MVP import/proxy |
| Multi-camera synchronization | MVP sync review, E05 sync/calibration nâng cao |
| Object detection | MVP trong pose pipeline |
| Tracking | MVP chọn và giữ người mục tiêu |
| Pose estimation | MVP HALPE_26 |
| Action recognition | E01 |
| Equipment tracking | E07 khi nội dung cần |
| Stability | MVP metric có điều kiện |
| Tactical/routine analysis | HLV chọn đoạn, E01 mở rộng cấu trúc |
| Biomechanics | MVP đo hình học 2D, E05 nâng cao |
| Performance prediction | E06 sau khi có dữ liệu dọc |
| Injury risk | Nghiên cứu riêng khi có protocol và outcome labels |
| Event detection | HLV gán mốc MVP, tự động hóa trong E01 |
| Referee assistance | E04 |
| Highlights | Evidence clip trong report MVP |
| Digital Twin | Hồ sơ chuyển động sau E05/E06, phạm vi riêng |
| Knowledge/analytics | Criterion/reference/metric manifest MVP |
| AI Coach | Template HLV duyệt MVP, mở rộng E06 |

## 15. Nguồn và trạng thái kiểm chứng

Các nguồn mới được tra cứu ngày 13/11/2026. Bản kế hoạch không đại diện một lần benchmark. Ngân sách, công thức feature, ngưỡng giá trị và phân bổ phase là đề xuất kỹ thuật của dự án.

- [N1 — Sports2D cấu hình skeleton](https://github.com/davidpagnon/Sports2D/blob/main/Sports2D/Demo/Config_demo.toml)
- [N2 — Sports2D LICENSE](https://github.com/davidpagnon/Sports2D/blob/main/LICENSE)
- [N3 — SMPL-Model license](https://smpl.is.tue.mpg.de/modellicense.html)
- [N4 — SMPL-Body license](https://smpl.is.tue.mpg.de/license.html)
- [N5 — Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15](https://vanban.chinhphu.vn/?classid=1&docid=214590&pageid=27160)
- [N6 — Nghị định 356/2025/NĐ-CP](https://vanban.chinhphu.vn/?classid=1&docid=216387&pageid=27160&typegroupid=4)
- [N8 — Kinovea](https://www.kinovea.org/)
- [N9 — Onform](https://onform.com/)
- [R1 — Sports2D](https://github.com/davidpagnon/Sports2D)
- [R2 — MMPose](https://github.com/open-mmlab/mmpose)
- [R3 — QAQA](https://github.com/waHAHJIAHAO/QAQA)
- [R4 — MMAction2](https://github.com/open-mmlab/mmaction2)
- [R5 — TaiChi-AQA](https://github.com/mlxger/TaiChi-AQA)
- [R6 — GVHMR](https://github.com/zju3dv/GVHMR)
- [R7 — KungFuAthleteBot](https://github.com/NPCLEI/KungFuAthleteBot)
- [R8 — TaiForm record để kiểm tra quyền của mẫu](https://zenodo.org/records/19656906)

## 16. Những quyết định còn cần dữ liệu thực tế

Bài 24 thức và variant, tên HLV/người phụ trách, danh sách người tập, đơn giá, lịch quay, điều kiện camera, model checkpoint và quality thresholds được chốt trong P00–P02. Các phase mở rộng chỉ được lập lịch sau G05 và nhu cầu đã đo. Prototype tập trung kiểm chứng ba câu hỏi — đo có đáng tin, HLV có dùng và thời gian bỏ ra có tương xứng giá trị.
