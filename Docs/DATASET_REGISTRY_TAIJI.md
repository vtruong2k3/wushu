# Dataset registry — Thái Cực Quyền

Cập nhật 13/11/2026. Đã tải: D12 UMONS-TAICHI (Kinect, Segmented_Kinect, Labels) và D09 TaiForm (annotation + tiêu chí, chưa tải video). Các bộ kiểm soát truy cập (D06, D10, D11) chưa gửi yêu cầu. Trạng thái dựa trên trang nguồn, metadata API, bài báo và file License đi kèm dữ liệu.

Quy tắc sử dụng: `AGENTS.md` §9.4. Giá trị "Mục đích được phép": `dev-test`, `benchmark`, `train`, `reference-only`, `not-usable`. Muốn dùng ngoài mục đích đã ghi thì phải cập nhật registry và được maintainer duyệt.

## Tổng hợp

| ID | Dataset | Bài | Nhãn chất lượng | Truy cập | License | Mục đích được phép | Vai trò trong dự án | Trạng thái |
|---|---|---|---|---|---|---|---|---|
| D08 | Taiji24-Local (tự quay) | 24 thức (variant HLV xác nhận) | Nhãn HLV theo rubric dự án | Nội bộ | Theo consent từng người | `dev-test`, `benchmark`; `train` chỉ với `consent_train = 1` | Nguồn chính cho mọi phase | Chưa quay (P9) |
| D14 | S3GCN Tai Chi (Hengonda / BUAA, ICIP 2024) | Thái cực quyền (bài cụ thể chưa rõ) | Điểm liên tục do chuyên gia chấm | Gửi đơn PDF có chữ ký qua email nhóm tác giả (theo README repo SSSGCN) | Chỉ nghiên cứu khoa học, cấm thương mại (theo README) | `not-usable` cho tới khi được cấp; sau đó `benchmark` (nghiên cứu) | Ứng viên cho chấm chất lượng (E03) | Chưa gửi yêu cầu; quy mô và bài chưa rõ |
| D06 | TaiChi-AQA | 24 thức | Có theo bài báo, chưa kiểm tra file nhãn | Gửi form qua email | Chưa rõ, xem thỏa thuận khi được cấp | `not-usable` cho tới khi được cấp; sau đó theo thỏa thuận | Nhận diện thức, đánh giá chất lượng | Chưa gửi yêu cầu |
| D10 | TaiChi-24 (BSU) | 24 thức | Có score theo survey AQA, thang điểm chưa rõ | Ký thỏa thuận và email | Chưa rõ | `not-usable` cho tới khi được cấp; sau đó theo thỏa thuận | Nhận diện và đánh giá dựa trên skeleton | Chưa gửi yêu cầu |
| D11 | PSU-TMM100 | 24 thức giản hóa | Không, đây là dữ liệu đo chuyển động | Dataset Request Form | Theo điều kiện cấp (IRB STUDY8085) | `not-usable` cho tới khi được cấp; dự kiến `benchmark` | Kiểm chứng số đo 2D bằng mocap và áp lực bàn chân | Chưa gửi yêu cầu |
| D12 | UMONS-TAICHI | 13 kỹ thuật, không phải 24 thức | Trình độ 0–10 theo người, không theo đoạn | Tải công khai (Zenodo) | **CC BY-NC-SA 4.0** (theo `License.txt` trong dữ liệu) | `dev-test`, `benchmark` (nghiên cứu, phi thương mại). **Không** `train` model dùng trong sản phẩm | Code đọc skeleton, phân đoạn | **Đã tải** Kinect, Segmented_Kinect, Labels → `datasets/taiji/umons/` |
| D09 | TaiForm (mẫu) | Bát pháp Ngũ bộ | Nhãn key event theo frame, file tiêu chí trừ điểm | Mẫu 5 người tải được; bộ đủ 41 người kiểm soát truy cập | Zenodo ghi CC BY 4.0, nhưng tác giả nói đây là mẫu cho phản biện | `reference-only` (cấu trúc nhãn và tiêu chí). Không train, không trộn nhãn với 24 thức | Tham khảo nhãn đa góc và keyframe | **Đã tải** annotation + tiêu chí (chưa tải video) → `datasets/taiji/taiform/` |
| D13 | Motion Embedding 24-form | 24 thức | Không | Google Drive | **Không có license**, chưa có quyền tái sử dụng | `not-usable` (chỉ học ý tưởng từ code/bài báo) | So sánh với mẫu, embedding | Chờ làm rõ quyền |

Chưa có bằng chứng TaiChi-AQA và TaiChi-24 là cùng nguồn. Khi nhận được dữ liệu, kiểm tra người tập, video nguồn và cách chia tập trước khi ghép hoặc đánh giá chéo.

## Chi tiết và bằng chứng

### D06 — TaiChi-AQA
- Bài báo: *TaiChi-AQA: A Dataset and Framework for Action Quality Assessment and Visual Analysis*, Wang et al., IET Computer Vision 2026, DOI [10.1049/cvi2.70053](https://ietresearch.onlinelibrary.wiley.com/doi/10.1049/cvi2.70053).
- Đã xác nhận qua kết quả tìm kiếm: 1.313 video, 24 tư thế; nhãn action, description, frame-level; 5 chỉ số Action Quality là body shapes, step forms, hand shapes, balance, movement fluency.
- Chưa tự đọc được toàn văn (Wiley trả 403): 4 tiêu chí Practice Level, tổng điểm 0–40, số người tập, góc quay.
- Repo [mlxger/TaiChi-AQA](https://github.com/mlxger/TaiChi-AQA) chỉ có README và `TaiChi-AQA_Request_Form.docx`, không có code hay checkpoint.

### D10 — TaiChi-24
- [Trang dự án BSU](https://bsu3dvlab.github.io/TaiChi24/index.html): 1.408 mẫu, RGB-D và skeleton 3D. Bài báo: *Tai Chi Action Quality Assessment and Visual Analysis with a Consumer RGB-D Camera*, IEEE MMSP 2022.
- Chưa rõ số người, thang điểm và license.

### D14 — S3GCN Tai Chi (Hengonda / BUAA)
- Bài báo: *S³GCN: Sport Scoring Siamese Graph Convolution Network*, Y. Lu, Z. Zhang, S. Lin, D. Zhang, H. Ma, Z. Qin — ICIP 2024, DOI 10.1109/ICIP51287.2024.10647800.
- Theo README của [divided7/SSSGCN](https://github.com/divided7/SSSGCN): video Thái cực quyền thật, điểm **liên tục** do chuyên gia thể thao chấm; dữ liệu "chỉ cho mục đích khoa học, cấm thương mại"; xin bằng đơn PDF có chữ ký gửi nhóm tác giả (địa chỉ trong README).
- Chưa rõ: bài nào (24 thức?), số video/người, thang điểm, cách chia tập. Trang IEEE chặn truy cập tự động (418); chưa đọc được toàn văn.
- Code trong repo: không có license, dở dang → không dùng.

### D11 — PSU-TMM100
- Trang chính thức: [vision.cse.psu.edu/data/data.shtml](https://vision.cse.psu.edu/data/data.shtml). Mô tả nghiên cứu: [taijiDataset](https://vision.cse.psu.edu/research/taijiDataset/content.html).
- Xin dữ liệu: [Dataset Request Form](https://forms.office.com/r/ceCgdJGkE7). Liên hệ Keaton Kraiger (kbk5531@psu.edu), Yanxi Liu (yanxi@cse.psu.edu).
- Nội dung: 100 chuỗi bài 24 thức giản hóa, 10 người, mỗi người 8–12 trial.
  - Mocap Vicon Nexus 2.6.1.
  - Áp lực bàn chân Tekscan F-scan 7.0.
  - Video 1080p hai góc, đồng bộ và đã hiệu chuẩn.
  - Có sẵn 2D OpenPose và HRNet, cùng 3D triangulated.
- Trích dẫn bắt buộc: Scott et al., *From Image to Stability: Learning Dynamics from Human Pose*, ECCV 2020.
- Khi dùng để kiểm chứng metric:
  - Đồng bộ timestamp, ánh xạ khớp marker/joint sang HALPE_26 và thống nhất hệ tọa độ.
  - Chiếu 3D Vicon vào từng camera đã hiệu chuẩn, rồi mới so với góc và độ cao 2D. Không so trực tiếp góc 2D với góc 3D.
  - Insole cho tâm áp lực (CoP), không phải trọng tâm cơ thể (CoM). CoM chỉ là ước lượng từ mô hình mocap, ví dụ Plug-in-Gait. Báo hai đại lượng riêng.

### D12 — UMONS-TAICHI
- [Zenodo 2784581](https://zenodo.org/records/2784581) và [GitHub](https://github.com/numediart/UMONS-TAICHI). Bài báo trên Data in Brief 2018.
- 2.200 mẫu, 13 lớp, 12 người, Qualisys 179 Hz (68 marker) và Kinect V2 30 Hz (25 khớp). Có dữ liệu đã và chưa chia đoạn.
- License: metadata Zenodo API trả `cc-by-4.0`, trong khi README GitHub và bài báo ghi CC BY-NC-SA 4.0. `License.txt` nằm trong cả ba zip đã tải ghi **CC BY-NC-SA 4.0**, nên áp dụng điều khoản này. Chi tiết tải và thống kê xem `datasets/taiji/README.md`.
- File cần lấy:

| Việc | File | Dung lượng |
|---|---|---|
| Đọc, chuẩn hóa, hiển thị skeleton; phân loại đoạn đã cắt | `Segmented_Kinect.zip` | 153 MB |
| Phân đoạn tự động trên chuỗi liên tục | `Kinect.zip` + `Labels.zip` | 216,9 MB + nhỏ |
| Ground truth mocap (khi cần) | `Segmented_TSV.zip` / `TSV.zip` / `C3D.zip` | 2,7–5,2 GB mỗi file |

### D09 — TaiForm
- [Zenodo 19656906](https://zenodo.org/records/19656906): mẫu 5 người (102, 108, 116, 118, 141), 6 góc RGB đồng bộ, 6 file annotation Excel, file *Deduction Criteria for Taijiquan (Bafa Wubu)*. Tổng 17,4 GB.
- Bộ đầy đủ nằm ở ba record Zenodo kiểm soát truy cập.

### D13 — Motion Embedding 24-form
- [Repo](https://github.com/Charl0tte19/Motion_Embedding_Model_For_24-Form_Tai-chi). File `.npz` đặt tên theo form, view, person, file, fps. Gồm 2D COCO-WholeBody và 3D MotionBERT (ước lượng, không phải mocap).
- `videos.txt` liệt kê 104 link Bilibili mà DATASET.md gọi là *some of the videos*, nên đây chưa phải danh sách nguồn đầy đủ.
- Repo không có license. Repo công khai không có nghĩa là được phép tái sử dụng, kể cả cho nghiên cứu. Cần hỏi tác giả trước khi dùng.

## Thứ tự triển khai đã chốt

| Việc cần làm | Dataset ưu tiên |
|---|---|
| Code đọc, chuẩn hóa và hiển thị skeleton | UMONS — Segmented_Kinect |
| Code phân đoạn chuỗi chuyển động | UMONS — Kinect + Labels |
| Nhận diện và đánh giá bài 24 thức | Xin TaiChi-AQA, TaiChi-24 |
| Kiểm chứng số đo bằng dữ liệu đo thật | Xin PSU-TMM100 |
| Thử so sánh động tác với mẫu | Motion Embedding, sau khi rõ quyền sử dụng |
| Tham khảo nhãn nhiều góc và keyframe | TaiForm, giữ riêng bài Bát pháp Ngũ bộ |
