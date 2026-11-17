# Dataset registry — Thái Cực Quyền

Cập nhật 13/11/2026; thêm D02, D15, D16, D17 ngày 2026-11-15 (X.14, chưa tải gì). Đã tải: D12 UMONS-TAICHI (Kinect, Segmented_Kinect, Labels) và D09 TaiForm (annotation + tiêu chí, chưa tải video). ~~Các bộ kiểm soát truy cập (D06, D10, D11) chưa gửi yêu cầu.~~ *(2026-11-15, DEC-0018: không gửi yêu cầu cho D06, D10, D11, D14; dự án dùng dữ liệu đã có và tìm bộ tải tự do, task X.14.)* Trạng thái dựa trên trang nguồn, metadata API, bài báo và file License đi kèm dữ liệu.

Quy tắc sử dụng: `AGENTS.md` §9.4. Giá trị "Mục đích được phép": `dev-test`, `benchmark`, `train`, `reference-only`, `not-usable`. Muốn dùng ngoài mục đích đã ghi thì phải cập nhật registry và được maintainer duyệt.

## Tổng hợp

| ID | Dataset | Bài | Nhãn chất lượng | Truy cập | License | Mục đích được phép | Vai trò trong dự án | Trạng thái |
|---|---|---|---|---|---|---|---|---|
| D20 | Video hướng dẫn Thái Cực Quyền 24 thức (4 file trong `video/`, maintainer tải về) | 24 thức (hướng dẫn, không phải tập luyện của người tham gia) | Không | Tải công khai trên web; URL gốc không được ghi lại | Không có điều khoản được xác minh. **Maintainer quyết định 2026-11-16: không áp ràng buộc license cho việc dùng nội bộ này** (agent không kiểm tra nguồn hay điều khoản) | `dev-test` nội bộ: kiểm tra kỹ thuật (ingest, probe, proxy, hiệu năng) **và phát triển pose P3.01 đến P3.06**, **đo hiệu năng pose P3.07** (tốc độ, VRAM, độ nhất quán của N so với N = 1, không dùng nhãn; DEC-0038) và **rà lỗi pose P3.08** (ảnh cắt khung hình có khung xương chỉ ở máy, không vào git; báo cáo chỉ có số và ID; DEC-0039); và **so sánh detector P3.09** (YOLOX đang chạy với YOLO11, chỉ đo recall, độ ổn định hộp, tốc độ; ảnh các frame bất đồng chỉ ở máy; báo cáo chỉ có số và nhãn; DEC-0043); và **lớp mask, lớp nối gap, bộ lọc Hampel, lưới đều, bộ lọc Butterworth và cờ tráo trái/phải P4.01 đến P4.06** (đếm các cú nhảy chéo của cặp trái/phải và số hàng bị cờ, đối chiếu với các frame tráo đã gán nhãn của P3.08, đếm các gap mà cờ sẽ chặn; đếm các ô bị loại, đo sai số của một đoạn nối, đếm các ô bị Hampel gắn cờ cùng độ nhạy trên các khớp mà người đã gọi tên sai (nhãn P3.08), đo độ đều của timeline cùng sai số vòng đi-về của lưới đều, và đo độ dịch, jitter và tốc độ trước sau của bộ lọc Butterworth trên chuyển động thật, và đếm coverage của cả chuỗi quality (ô đã quan sát, đã nối và thiếu theo video, khớp, lý do và kết cục gap) cùng sàn Hampel theo thân và kích thước của `quality.json` (P4.07), trên các file pose đã có của P3.08; chỉ ghi số và nhãn, không đưa ảnh hay file pose vào git; DEC-0040, DEC-0045, DEC-0046, DEC-0047, DEC-0048, DEC-0049, DEC-0050); không chia sẻ, không đưa vào git, không tính độ chính xác sản phẩm. `train`, `benchmark`, dùng ngoài máy này: chưa được quyết, cần cập nhật registry và maintainer duyệt | Kiểm khói ingest/proxy với file dài 1080p (X.26); không phải file điện thoại, không có tiếng vỗ tay hay đèn nên không dùng cho đồng bộ | Có trên máy từ 2026-11-16; chưa tính vào bộ dữ liệu của dự án |
| D08 | Taiji24-Local (tự quay) | 24 thức (variant HLV xác nhận) | Nhãn HLV theo rubric dự án | Nội bộ | Theo consent từng người | `dev-test`, `benchmark`; `train` chỉ với `consent_train = 1` | Nguồn chính cho mọi phase | Chưa quay (P9) |
| D14 | S3GCN Tai Chi (Hengonda / BUAA, ICIP 2024) | Thái cực quyền (bài cụ thể chưa rõ) | Điểm liên tục do chuyên gia chấm | Gửi đơn PDF có chữ ký qua email nhóm tác giả (theo README repo SSSGCN) | Chỉ nghiên cứu khoa học, cấm thương mại (theo README) | `not-usable` cho tới khi được cấp; sau đó `benchmark` (nghiên cứu) | Ứng viên cho chấm chất lượng (E03) | Không gửi yêu cầu (2026-11-15, DEC-0018); quy mô và bài chưa rõ |
| D06 | TaiChi-AQA | 24 thức | Có theo bài báo, chưa kiểm tra file nhãn | Gửi form qua email | Chưa rõ, xem thỏa thuận khi được cấp | `not-usable` cho tới khi được cấp; sau đó theo thỏa thuận | Nhận diện thức, đánh giá chất lượng | Không gửi yêu cầu (2026-11-15, DEC-0018) |
| D10 | TaiChi-24 (BSU) | 24 thức | Có score theo survey AQA, thang điểm chưa rõ | Ký thỏa thuận và email | Chưa rõ | `not-usable` cho tới khi được cấp; sau đó theo thỏa thuận | Nhận diện và đánh giá dựa trên skeleton | Không gửi yêu cầu (2026-11-15, DEC-0018) |
| D11 | PSU-TMM100 | 24 thức giản hóa | Không, đây là dữ liệu đo chuyển động | Dataset Request Form | Theo điều kiện cấp (IRB STUDY8085) | `not-usable` cho tới khi được cấp; dự kiến `benchmark` | Kiểm chứng số đo 2D bằng mocap và áp lực bàn chân | Không gửi yêu cầu (2026-11-15, DEC-0018); P10.07 không chạy trừ khi quyết định đổi |
| D12 | UMONS-TAICHI | 13 kỹ thuật, không phải 24 thức | Trình độ 0–10 theo người, không theo đoạn | Tải công khai (Zenodo) | **CC BY-NC-SA 4.0** (theo `License.txt` trong dữ liệu) | `dev-test`, `benchmark` (nghiên cứu, phi thương mại). **Không** `train` model dùng trong sản phẩm | Code đọc skeleton, phân đoạn | **Đã tải** Kinect, Segmented_Kinect, Labels → `datasets/taiji/umons/`; tải thêm `Segmented_C3D.zip` (Qualisys, 2,67 GB) ngày 2026-11-15 (X.16) Dùng cho P4.08 (2026-11-17, `dev-test`): chạy chuỗi quality (W6) trên 111 file Kinect, chỉ ghi số và mã chuỗi (`Docs/reports/p4_umons_quality.md`), không chép dữ liệu vào git, kết quả ngoài miền, không tính độ chính xác sản phẩm; DEC-0051 |
| D09 | TaiForm (mẫu) | Bát pháp Ngũ bộ | Nhãn key event theo frame, file tiêu chí trừ điểm | Mẫu 5 người tải được; bộ đủ 41 người kiểm soát truy cập | Zenodo ghi CC BY 4.0, nhưng tác giả nói đây là mẫu cho phản biện | `reference-only` (cấu trúc nhãn và tiêu chí). Không train, không trộn nhãn với 24 thức | Tham khảo nhãn đa góc và keyframe | **Đã tải** annotation + tiêu chí (chưa tải video) → `datasets/taiji/taiform/` |
| D13 | Motion Embedding 24-form | 24 thức | Không | Google Drive | **Không có license**, chưa có quyền tái sử dụng | `not-usable` (chỉ học ý tưởng từ code/bài báo) | So sánh với mẫu, embedding | Chờ làm rõ quyền; kiểm lại ngày 2026-11-15 (X.16): vẫn không có `LICENSE` và không có câu nào về quyền sử dụng; **không tải** |
| D18 | Raw data of typical balance movements of Tai Chi (Figshare, PeerJ 2023) | Hai động tác thăng bằng (knee lift balance, leg stirrup balance); 16 nam, 8 vận động viên chuyên nghiệp và 8 nghiệp dư; không phải bài 24 thức | Không | Tải công khai trên Figshare, không cần đăng ký (DOI 10.6084/m9.figshare.22574185) | **CC BY 4.0** (đọc ở API Figshare ngày 2026-11-15) | `dev-test`, `benchmark`. License cho phép cả `train`; chưa có việc cần nên chưa mở (cập nhật registry khi cần) | Tham khảo sinh cơ học chi dưới; có thể dùng cho nghiên cứu động tác đứng một chân. Không phục vụ ba số đo của MVP | **Đã tải** ngày 2026-11-15 → `datasets/taiji/balance_figshare/` (16 workbook xlsx; md5 khớp công bố; X.16) |
| D19 | Tai Chi, Physiological Complexity, and Healthy Aging: Gait and EMG data (PhysioNet) | Không có động tác Thái cực quyền: 87 người 50–79 tuổi (60 chưa tập, 27 chuyên gia) **đi bộ** | Không | Tải công khai, truy cập mở (ZIP 1,5 GB) | Open Data Commons Attribution License v1.0 (đọc ở trang v1.0.1 ngày 2026-11-15; v1.0.2 mới hơn) | `reference-only` | Không dùng cho MVP: dữ liệu đi bộ (bấm bước chân và EMG 1500 Hz), không video | Không tải (X.16): không có việc nào dùng |
| D02 | KungfuAthlete (phần Thái cực quyền) | Thái cực quyền: quyền 21 mẫu, kiếm 9 mẫu theo thẻ dataset; bài và phong cách không nêu | Không | Tải trực tiếp trên Hugging Face, không cần đăng ký; bản có video qua Google Drive (chưa kiểm) | **Xung đột:** thẻ Hugging Face ghi Apache-2.0; trang dự án ghi dữ liệu chỉ cho nghiên cứu và học thuật, video dùng với phép của vận động viên | `reference-only` (áp dụng mức chặt hơn). Không train, không dùng cho sản phẩm | Chuyển động 3D ước lượng từ video (SMPL-H, không phải mocap) để tham khảo; không dùng để kiểm chứng số đo | Chưa tải; mã D02 theo master plan |
| D15 | MADS (Martial Arts, Dancing and Sports, CityU) | Thái cực quyền: 2 sư phụ, 6 bài (theo trang bên thứ ba; kiểu quyền không nêu) | Không | **Chưa xác minh:** trang chính thức lỗi TLS khi kiểm (2026-11-15) | Chưa tìm thấy license; footer cổng CityU ghi bảo lưu mọi quyền, kể cả khai thác dữ liệu và huấn luyện AI | `not-usable` cho tới khi maintainer đọc điều khoản trên trình duyệt; dự kiến `dev-test`, `benchmark` nếu điều khoản cho phép | Ứng viên thay PSU-TMM100: video nhiều góc và mocap đồng bộ, đã hiệu chuẩn (theo bên thứ ba) để kiểm chứng số đo 2D | Chưa tải; điều khoản chưa xác minh; **bỏ khỏi kế hoạch** (2026-11-15, DEC-0019) |
| D16 | Kinetics (lớp tai chi), bản host CVDF | Nhiều kiểu Thái cực quyền trộn, không phải 24 thức; clip YouTube khoảng 10 giây | Không (nhãn cấp clip) | Tải qua script và S3 của CVDF, không cần tài khoản; chưa kiểm có lấy riêng một lớp được không | Annotation CC BY 4.0 **chỉ theo nguồn thứ cấp** (trang Hyak của UW, mirror Hugging Face); repo CVDF và trang DeepMind không ghi license; quyền video thuộc người đăng YouTube | `dev-test` (nội bộ, không phân phối lại, không train model dùng trong sản phẩm); chỉ sau khi maintainer duyệt việc tải | Thử pipeline pose trên video Thái cực quyền thật và đa dạng | Chưa tải; chưa duyệt tải. Tập val Kinetics-400: 20 phần, 28,3 GB (đo bằng yêu cầu HEAD ngày 2026-11-15); tập val có 50 clip mỗi lớp nên có 50 clip tai chi (theo bài báo) |
| D17 | CMU Graphics Lab Motion Capture (take Tai Chi) | Tai Chi chung chung; một take (theo agent đọc metadata của mirror, chưa tự kiểm) | Không | Tải trực tiếp; trang gốc lỗi chứng chỉ khi kiểm, điều khoản đọc qua mirror Hugging Face | Điều khoản CMU theo mirror (thẻ `cmu-mocap`): được sao chép, sửa, phân phối lại không cần xin phép; được đưa vào sản phẩm bán thương mại nhưng không được bán lại dữ liệu, kể cả bản chuyển đổi | `dev-test` (kiểm tra thử mocap, không kết luận kiểm chứng); sau khi maintainer đọc điều khoản trên trang gốc | Kiểm tra thử quy trình mocap nhỏ; không thay được PSU-TMM100 | Chưa tải; metadata của mirror liệt kê take 12_04 là "tai chi" (FBX); đường dẫn, dung lượng và tần số chưa xác định |

Chưa có bằng chứng TaiChi-AQA và TaiChi-24 là cùng nguồn. Khi nhận được dữ liệu, kiểm tra người tập, video nguồn và cách chia tập trước khi ghép hoặc đánh giá chéo.

## Chi tiết và bằng chứng

### D20 — Video hướng dẫn Thái Cực Quyền 24 thức (web)

- Nguồn: bốn file `.mp4` do maintainer tải về, để trong thư mục `video/` ở gốc workspace (không phải `datasets/`, nên không theo đúng bố cục của AGENTS.md §9.4 mục 2; `.gitignore` chặn `*.mp4` nên không vào git). URL gốc, tác giả và điều khoản **không được ghi lại**. Ban đầu (2026-11-16) agent coi là mức hạn chế nhất (AGENTS.md §9.1, chỉ `dev-test` kỹ thuật); cùng ngày maintainer quyết định không áp ràng buộc license cho việc dùng nội bộ, nên mục đích được phép mở rộng sang phát triển pose P3.01 đến P3.06 (DEC-0036). Agent không xác minh nguồn.
- Agent chỉ đọc siêu dữ liệu bằng ffprobe và probe/quét PTS của dự án (2026-11-16), chưa xem nội dung hình.

| # | File | Dung lượng (byte) | Codec | Thời lượng | SHA-256 |
|---|---|---|---|---|---|
| 1 | `Hướng Dẫn Chi Tiết Thái Cực Quyền 24 Thức (Phần 1).mp4` | 215719545 | AV1 1080p 24 fps | 1029,6 s | `f80bd1594d0311e2493e33ee4ed55e51904267f0151a2323933252f7f501c0cf` |
| 2 | `Hướng Dẫn Chi Tiết Thái Cực Quyền 24 Thức (Phần 2).mp4` | 257287499 | H.264 1080p 24 fps | 977,3 s | `50a6cd2f383ccd8fc3da77b94d300bd80cd5d3f5cf208a13aa12e6004e35bec8` |
| 3 | `Hướng dẫn chi tiết Thái Cực Quyền 24 Thức (Phần 3).mp4` | 350787594 | H.264 1080p 24 fps | 1328,9 s | `1eb59b6f01c32dcff463f6c37e53d04ca536a3a5be55ffb3055c71fe393f1d7d` |
| 4 | `Thái Cực Quyền 24 Thức - Tai Chi 24 Forms - Hướng Dẫn Chi Tiết Kèm Hơi Thở - martial arts - Kung Fu.mp4` | 486260064 | AV1 1080p 30 fps | 2576,6 s | `65d2913540fcff7afb3af1052b5be09e4ec686cb181f28d789b8669e3e57e15a` |

Tất cả: 1920x1080, không tag xoay, bắt đầu ở 0, âm thanh AAC 44,1 kHz stereo, không phải VFR theo quy tắc của dự án. Ba file đầu là ba phần nối tiếp; file thứ tư là một video khác. Không phải hai camera của một take.

Huấn luyện, `benchmark`, chia sẻ hoặc dùng ngoài máy này chưa được quyết: cần cập nhật registry và maintainer duyệt. Kết quả pose trên các video này không tính là độ chính xác sản phẩm.

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
- Xin dữ liệu: [Dataset Request Form](https://forms.office.com/r/ceCgdJGkE7). Liên hệ Keaton Kraiger (<kbk5531@psu.edu>), Yanxi Liu (<yanxi@cse.psu.edu>).
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
| Ground truth mocap (khi cần) | `Segmented_TSV.zip` / `TSV.zip` / `C3D.zip` | 2,7–5,2 GB mỗi file. **`Segmented_C3D.zip` (2,67 GB) đã tải 2026-11-15 (X.16)**: md5 khớp, 2.149 file `.c3d` của 12 người và 13 lớp, license trong dữ liệu CC BY-NC-SA 4.0; chưa mở nội dung |

### D09 — TaiForm

- [Zenodo 19656906](https://zenodo.org/records/19656906): mẫu 5 người (102, 108, 116, 118, 141), 6 góc RGB đồng bộ, 6 file annotation Excel, file *Deduction Criteria for Taijiquan (Bafa Wubu)*. Tổng 17,4 GB.
- Bộ đầy đủ nằm ở ba record Zenodo kiểm soát truy cập.

### D13 — Motion Embedding 24-form

- [Repo](https://github.com/Charl0tte19/Motion_Embedding_Model_For_24-Form_Tai-chi). File `.npz` đặt tên theo form, view, person, file, fps. Gồm 2D COCO-WholeBody và 3D MotionBERT (ước lượng, không phải mocap).
- `videos.txt` liệt kê 104 link Bilibili mà DATASET.md gọi là *some of the videos*, nên đây chưa phải danh sách nguồn đầy đủ.
- Repo không có license. Repo công khai không có nghĩa là được phép tái sử dụng, kể cả cho nghiên cứu. Cần hỏi tác giả trước khi dùng.

### D02 — KungfuAthlete

Khảo sát trong X.14 (2026-11-15). **Tôi đã đọc:** [trang dự án](https://kungfuathletebot.github.io/), [thẻ Hugging Face](https://huggingface.co/datasets/LuluCao/KungfuAthleteBot), [README GitHub](https://github.com/NPCLEI/KungFuAthleteBot).

- Nội dung (thẻ Hugging Face): 197 video luyện tập của một vận động viên; dữ liệu chuyển động gồm SMPL-H (GVHMR), qpos robot và BeyondMimic; tổng 7,29 GB. Thái cực quyền: quyền 21 mẫu, kiếm 9 mẫu (30 mẫu). Tần số 50 Hz (BeyondMimic) và 30 Hz (qpos GMR) theo thẻ.
- License xung đột: thẻ ghi `apache-2.0`; trang dự án ghi "released for research and academic use" và video dùng "for research and academic purposes only" với phép của vận động viên; README GitHub ghi dữ liệu chỉ cho mục đích khoa học và học thuật; code ghi MIT (chưa thấy nội dung license). Áp dụng mức chặt hơn (AGENTS.md §9.1): nghiên cứu, không thương mại.
- Video: trang dự án mô tả bản Google Drive là "Full release + videos" và bản Hugging Face là "QA + robot qpos"; chưa kiểm Drive. Agent khảo sát báo bài báo (arXiv 2602.13656) nói video gốc không phân phối lại: **chưa tự đọc, mâu thuẫn chưa xác minh**.
- Theo master plan: phân loại riêng dữ liệu robot, pseudo-3D và video; không lấy tổng mẫu võ thuật làm số mẫu Thái cực quyền. Họ SMPL có license riêng (AGENTS.md §9.1: nghiên cứu, chưa rõ).

### D18 — Raw data of typical balance movements of Tai Chi

Khảo sát trong X.16 (2026-11-15). **Tôi đã đọc:** [bài báo trên PubMed Central](https://pmc.ncbi.nlm.nih.gov/articles/PMC10404393/) (câu về nơi lưu dữ liệu) và [API Figshare](https://api.figshare.com/v2/articles/22574185).

- Bản ghi: DOI 10.6084/m9.figshare.22574185.v1, công khai, CC BY 4.0, một file `Raw data (Tai Chi).rar`, 211.846.155 byte, md5 `d6f770b7f0904d937f64672a1f6ceee4`, mô tả "Lower limb joints and muscles".
- Theo bài báo: 16 nam; hai động tác; góc khớp, mô-men khớp, lực cơ (mô hình AnyBody) và EMG bốn cơ; bắt chuyển động 250 Hz, bàn lực và EMG 1000 Hz. Nội dung thật của file (đọc tên sheet và vùng dữ liệu ngày 2026-11-15): 16 workbook (8 nghiệp dư, 8 chuyên nghiệp), mỗi workbook 10 sheet gồm lực cơ, hoạt động cơ, lực khớp, mô-men khớp và góc khớp cho bên phải và bên trái, 300 đến 1.840 dòng mỗi sheet. Đó là kết quả mô hình sinh cơ học chi dưới; **không có tọa độ marker, thân hay vai, và không có video**, nên không phục vụ ba số đo của MVP và không dùng được cho nghiên cứu camera ảo.
- Trích dẫn: Li, Haojie (2023), *Raw data of typical balance movements of Tai Chi*, figshare, và bài báo PeerJ 2023 (Li và cộng sự).

### D19 — Tai Chi gait (PhysioNet)

Khảo sát trong X.16. **Tôi đã đọc:** [trang PhysioNet v1.0.1](https://physionet.org/content/taichidb/1.0.1/).

- DOI 10.13026/51h0-rs07 (v1.0.1). Dữ liệu là bấm bước chân (công tắc ở ngón và gót) và EMG của cơ chày trước và cơ bụng chân ngoài, mẫu 1500 Hz, trong khi **đi bộ** (10 phút một nhiệm vụ, 90 giây hai nhiệm vụ). Không có video hay động tác bài.
- Nội dung dán vào ghi "Gait v1.0.2": đó là phiên bản mới hơn của cùng bộ này; tôi chỉ đọc trang v1.0.1.

### D15 — MADS

Khảo sát trong X.14. Trang chính thức [CityU VISAL](https://visal.cs.cityu.edu.hk/research/mads/) **không đọc được** (lỗi TLS ở máy kiểm); không vượt lỗi chứng chỉ.

- Theo agent khảo sát (chưa tự đọc): video nhiều góc, một bộ stereo/depth và mocap đồng bộ đã hiệu chuẩn; phần Thái cực quyền có 2 sư phụ, 6 bài; khoảng 53 nghìn frame; mocap 60 Hz theo một bài báo bên thứ ba. Bản ghi [CityU Scholars](https://scholars.cityu.edu.hk/en/datasets/martial-arts-dance-sports-mads-dataset/) là nơi footer bảo lưu mọi quyền.
- Không dùng torrent hay mirror không rõ nguồn (AGENTS.md §9.1).
- ~~**Việc cần:** maintainer mở trang trong trình duyệt, đọc điều khoản tải và license, rồi cập nhật dòng D15.~~ *(2026-11-15, DEC-0019: bỏ khỏi kế hoạch, không cần đọc.)*

### D16 — Kinetics, lớp tai chi

Khảo sát trong X.14. **Tôi đã đọc:** [kho CVDF](https://github.com/cvdfoundation/kinetics-dataset), [trang DeepMind](https://deepmind.google/research/open-source/kinetics/) (không nhắc Kinetics, không có điều khoản).

- CVDF host video Kinetics-400 và Kinetics-700-2020; tải bằng script (ví dụ `k400_downloader.sh`) lấy các tarball; README không ghi license.
- CC BY 4.0 cho annotation chỉ có ở nguồn thứ cấp ([trang Hyak của UW](https://hyak.uw.edu/docs/data-commons/kinetics), mirror Hugging Face). Chưa có tài liệu chính thức của Google. Mỗi clip là video YouTube nên quyền video thuộc người đăng.
- **Đo ngày 2026-11-15 (chỉ yêu cầu HEAD và đọc file danh sách, không tải dữ liệu):** tập val Kinetics-400 gồm 20 phần `part_0` … `part_19`, tổng 28,3 GB; theo bài báo (arXiv 1705.06950) tập val có 50 clip mỗi lớp, tức 50 clip tai chi (khoảng 8 phút). README CVDF chỉ mô tả tải theo cả tập, không có cách lấy riêng một lớp; các phần là mảnh chia, nên phải tải đủ 20 phần mới lọc được 50 clip (suy luận, chưa kiểm).
- **Chưa kiểm:** dung lượng tập train; số clip tai chi ở train (agent báo lớp số 347 với 1.070 clip theo phụ lục bài báo; chưa tự đọc).

### D17 — CMU Graphics Lab Motion Capture

Khảo sát trong X.14. Trang gốc [mocap.cs.cmu.edu](https://mocap.cs.cmu.edu/) lỗi chứng chỉ khi kiểm; không vượt lỗi.

- **Tôi đã đọc** thẻ mirror [gbionics/cmu-fbx](https://huggingface.co/datasets/gbionics/cmu-fbx): license `cmu-mocap`; "The motion capture data may be copied, modified, or redistributed without permission"; "You may include this data in commercially-sold products, but you may not resell this data directly, even in converted form". Đây là trích lại điều khoản của CMU qua bên thứ ba, chưa đọc từ trang gốc.
- Take Tai Chi: file metadata của mirror (2549 dòng, đọc ngày 2026-11-15) có dòng `12_04.fbx,tai chi`; các take 12_01 đến 12_03 là "walk". Đường dẫn thật của file không tìm thấy ở URL tôi đoán (404), nên **dung lượng, tần số và định dạng dùng được (FBX hay BVH) chưa xác định**; chọn định dạng khi có task cần dữ liệu này.

## Khảo sát bộ tải tự do (X.14, 2026-11-15)

Kết quả khảo sát do agent thực hiện (chỉ đọc web, không tải, không đăng nhập); các mục không ghi "đã đọc" ở trên là **chưa tự kiểm lại**.

- **Không có bộ mở nào có nhãn từng thức của bài 24 thức.** Mọi nguồn có nhãn loại đó đều cần yêu cầu: PSU-TMM100, TaiChi-AQA, TaiChi-24 và bộ TaiChi nhiều góc (arXiv 2306.14490).
- **Đã khảo sát, không đăng ký:** TaiChi-HD (chỉ ID YouTube, ảnh cắt 256×256, repo MIT), UCF101 lớp TaiChi (không ghi license, độ phân giải thấp), Sports-1M (nhãn tự động, nhiều link chết), Kinetics-skeleton (OpenPose 2D, không phải HALPE_26, không ghi license dữ liệu), ActivityNet (video qua Google Form), MA-Pose trên figshare (chưa thấy nội dung Thái cực quyền).
- **Loại vì cần đăng ký hoặc yêu cầu:** AMASS, BABEL, HumanML3D (dựng lại từ AMASS), Motion-X, Humanoid-X (không ghi license), bộ TaiChi của ECNU (không thấy tải công khai).
- **Yêu cầu truy cập chưa có phản hồi (2026-11-15, DEC-0019):** maintainer đã điền form và gửi email cho tác giả một bộ dữ liệu, chưa nhận phản hồi; dự án không chờ. Chưa rõ bộ nào (câu hỏi mở trong X.15), nên không sửa trạng thái dòng cụ thể nào.
- **D12 không đổi:** metadata Zenodo ghi CC BY 4.0, còn file license trong dữ liệu ghi CC BY-NC-SA 4.0; vẫn áp dụng điều khoản chặt hơn.

## Thứ tự triển khai đã chốt

| Việc cần làm | Dataset ưu tiên |
|---|---|
| Code đọc, chuẩn hóa và hiển thị skeleton | UMONS — Segmented_Kinect |
| Code phân đoạn chuỗi chuyển động | UMONS — Kinect + Labels |
| Nhận diện và đánh giá bài 24 thức | ~~Xin TaiChi-AQA, TaiChi-24~~ Không xin (2026-11-15, DEC-0018); bộ tải tự do: xem X.14 |
| Kiểm chứng số đo bằng dữ liệu đo thật | ~~Xin PSU-TMM100~~ Không xin (2026-11-15, DEC-0018); ứng viên tải tự do: CMU (D17), chờ maintainer đọc điều khoản gốc (X.14); MADS (D15) bỏ khỏi kế hoạch (DEC-0019) |
| Thử pipeline pose trên video Thái cực quyền thật, trước khi có D08 | Kinetics lớp tai chi (D16), sau khi maintainer duyệt việc tải (X.14) |
| Thử so sánh động tác với mẫu | Motion Embedding, sau khi rõ quyền sử dụng |
| Tham khảo nhãn nhiều góc và keyframe | TaiForm, giữ riêng bài Bát pháp Ngũ bộ |
