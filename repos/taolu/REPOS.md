# Repo cho phân tích Wushu Taolu (quyền)

Clone ngày 13/11/2026, `--depth 1`, đã tắt git hooks. Chưa cài đặt hay chạy thử repo nào.

## Dùng được (có license mở)

| Repo | Commit | Ngày | License | Vai trò | Vị trí trong kế hoạch v3 |
|---|---|---|---|---|---|
| [Sports2D](https://github.com/davidpagnon/Sports2D) | `f10818034df11cc5d795ab967e00c59fef16ebbd` | 2026-11-13 | BSD-3-Clause | Pose 2D + góc khớp từ video. Baseline pose của MVP | P01 |
| [mmaction2](https://github.com/open-mmlab/mmaction2) | `a5a167dff2399e2d182a60332325f9c0d4663517` | 2026-03-18 | Apache-2.0 | Train nhận diện thức/động tác trên skeleton (STGCN++, PoseC3D) | E01 |
| [QAQA](https://github.com/waHAHJIAHAO/QAQA) | `013a25a1d3b899e53c7de1965f2fa6575b624737` | 2026-07-03 | Apache-2.0 | So sánh với bài mẫu bằng DTW, chấm chất lượng không cần nhãn | P03.06 |
| [OpenWushu](https://github.com/cloudsbird/OpenWushu) | `53d4e20616c209479246a3ec91d711498becfaf9` | 2026-10-28 | Code AGPL-3.0, **nội dung CC BY-SA 4.0** | Kho tri thức bài quyền: danh sách động tác, bước, điểm mấu chốt, lỗi hay gặp | Ontology, rubric |

### Ghi chú

**Sports2D**
- Chạy pose bằng RTMLib/RTMPose (ONNX, gốc Apache-2.0), không dùng Ultralytics. Vì vậy không vướng AGPL.
- Mặc định `pose_model = 'Body_with_feet'` (HALPE_26), có bàn chân. Đúng với lựa chọn skeleton trong v3.
- Cần Python ≥ 3.11.

**mmaction2**
- v1.2.0, cần `mmcv>=2.0.0rc4,<2.2.0`. Trên Windows nên dùng torch 2.1 + CUDA 12.1 để có wheel mmcv dựng sẵn.
- Graph hỗ trợ các layout `coco` (17 khớp), `nturgb+d` (25 khớp Kinect V2, khớp dữ liệu UMONS) và layout tùy biến dạng dict (HALPE_26).
- Chỉ phân loại clip. Bài quyền liên tục cần sliding window, hoặc HLV chia đoạn như MVP v3.

**QAQA**
- Gồm DTW nhiều mức phân giải và phát hiện bất thường bằng DBSCAN trên gia tốc.
- Dữ liệu gốc là khí công (Bát đoạn cẩm, Dịch cân kinh), xin qua form. Phải thay template bằng mẫu Thái cực quyền và kiểm chứng lại.

**OpenWushu**
- `db/seeds/routines/*.json` gồm 10 bài thi đấu: taiji-42, taiji-sword-42, changquan, southern-fist, broadsword, straight-sword, spear, staff, southern-broadsword, southern-staff.
- Mỗi động tác có tên Trung/pinyin/Anh, `section`, `start_sec`/`end_sec` trong video mẫu, toạ độ trên thảm, `steps`, `key_points`, `mistakes`.
- **Không có bài 24 thức.** Một số trường còn để trống (ví dụ `facing_en: "[to be filled in from the reference]"`).
- README ghi là "AI-assisted, certified-judge-verified", nhưng HLV vẫn phải duyệt trước khi dùng làm rubric.
- Nội dung CC BY-SA: sản phẩm phái sinh từ nội dung phải chia sẻ cùng điều khoản. Code app Rails là AGPL, không cần dùng.

## Chỉ đọc tham khảo (không có license, không được tái sử dụng code/dữ liệu) — `_no-license/`

| Repo | Commit | Nội dung | Ghi chú |
|---|---|---|---|
| [Intelligent-Scoring-the-Long-Fist-Routine-Movements](https://github.com/pyqpyqpyqpyq789/Intelligent-Scoring-the-Long-Fist-Routine-Movements) | `58d73eb2fca3d0b14cd208f61993be0cfbf19964` | Chấm điểm Trường quyền, kèm bài báo Scientific Reports 2025 | `XingShenQuan.npy` có shape (52, 32, 28), trong khi `QualityScore.npy` có (180,). Số mẫu không khớp, cần audit trước khi tin kết quả |
| [Action-Recognition-and-Temporal-Localization-for-Wushu-Routine-Competition](https://github.com/pyqpyqpyqpyq789/Action-Recognition-and-Temporal-Localization-for-Wushu-Routine-Competition) | `9348795a1a771394a86843fc8537b344ab5a19c2` | Nhận diện và định vị thời gian động tác, bài Trường quyền quốc tế v3 | Chỉ có 1 notebook và 1 script |
| [Motion_Embedding_Model_For_24-Form_Tai-chi](https://github.com/Charl0tte19/Motion_Embedding_Model_For_24-Form_Tai-chi) | `77e84bee3e242528560eafb698e2c366dd52b051` | Embedding chuyển động bài 24 thức (ST-GCN + triplet loss), giao diện so sánh với mẫu | Dữ liệu `.npz` trên Google Drive chưa tải. Cần xin phép tác giả |

Không có license nghĩa là mặc định giữ mọi quyền. Chỉ đọc để học phương pháp. Nếu muốn dùng thì viết lại hoặc xin phép tác giả.

## Đánh giá code (13/11/2026, đọc tĩnh, chưa chạy)

### Sports2D: không dùng nguyên khối, dùng lại rtmlib và một phần logic

Phần lõi nằm ở Pose2Sim (pin `c6db0ca`) và rtmlib (không pin). Gọi qua `Sports2D.process(config)`, chỉ ghi file, không trả mảng.

- **Pose:** `Body_with_feet` gồm YOLOX-m (HumanArt) và RTMPose-m (body7-halpe26).
  - Model tải về `~/.cache/rtmlib` lúc chạy lần đầu, **không kiểm hash**.
  - Chọn backend: có torch + CUDA thì dùng onnxruntime-gpu, không thì OpenVINO CPU.
  - Cột output đi theo thứ tự cây skeleton (Hip=19, RHip=12…), không theo chỉ số HALPE. Bỏ mắt và tai, còn 22 khớp.
  - License weights không ghi rõ. Body7 gồm cả bộ dữ liệu chỉ cho nghiên cứu.
- **Chọn người:** mặc định là click trên GUI (`on_click`).
  - Tracking ghép theo khoảng cách keypoint (Hungarian, tối đa 250 px).
  - Mất dấu quá 1 s thì tách thành ID mới, ID cũ không dùng lại.
  - Không xử lý tráo trái/phải: code xử lý nằm ở `process.py:2174` nhưng đã bị comment.
- **Khoảng trống và lọc:**
  - Score < 0,3 thì thành NaN. Nội suy tuyến tính tới 100 frame.
  - **Gap lớn mặc định điền `last_value`** (`Config_demo.toml:157`). Cách này tạo ra pause giả, làm sai metric nhịp. Phải đặt `nan`.
  - Hampel + Butterworth 6 Hz. **Chỉ lưu dữ liệu đã lọc**, không lưu raw.
- **Thời gian:** `fps = round(CAP_PROP_FPS)` (`Sports2D.py:438`), timestamp là `frame/fps`. Không dùng PTS, không xử lý được video VFR từ điện thoại.
- **Đổi px→m:**
  - Một hệ số chung lấy từ chiều cao người.
  - Góc sàn ước lượng từ mũi chân, rồi xoay toàn bộ tọa độ.
  - Độ sâu cố định 10 m, giả định chuyển động phẳng.
  - Với metric độ cao hông nên dùng TRC theo px. TRC theo m dễ bị chuyển động ngang lọt vào trục y.
- **Góc:**
  - Trunk là Neck(18)→Hip(19), 90° khi đứng thẳng. Không phải trục hông-giữa → vai-giữa như README mô tả.
  - X bị lật khi người quay trái. Khi đổi sang mét thì trừ đi góc sàn.
- **Rủi ro khi tích hợp:**
  - Import là **tắt kiểm chứng SSL cho toàn process** (`process.py:106`).
  - Ép dùng Qt backend trên Windows.
  - `DEFAULT_CONFIG.copy()` là shallow copy, nên config bị dùng chung và biến đổi giữa các lần gọi (`Sports2D.py:538`).
  - `except` trống biến lỗi thành frame NaN.
  - Mỗi lần chạy ghi đè vào cùng thư mục output.
  - Kéo theo opensim, PySide6, openvino. Nếu dùng phải chạy dưới dạng subprocess.
- **Kết luận:**
  - Pose: gọi **rtmlib trực tiếp** với ONNX đã pin SHA. Tự đọc frame bằng PyAV để có PTS.
  - Tracking: có thể dùng lại `sort_people_sports2d`, cộng thêm cơ chế khóa người mục tiêu.
  - Phần mask/raw/lọc, metric và DTW: tự viết. Không dùng phần px→m/floor/perspective.

### QAQA: viết lại, chỉ tham khảo thuật toán

- **Đầu vào:** code chỉ chạy được với JSON pose 3D Human3.6M-17 của mmpose, đổi thành 15 khớp và căn theo cổ. Mỗi frame có 27 đặc trưng thủ công (góc khớp, góc đoạn, hướng mặt nhị phân…).
- **Khác với bài báo:**
  - **Không có DBSCAN, không có phát hiện bất thường theo gia tốc, không có code đánh giá Spearman.**
  - "Multi-resolution O(n)" thực chất là FastDTW chuẩn.
  - Ngưỡng là hằng số `t = 0.1/0.2` theo số frame.
- **Không chạy được:**
  - Lỗi import: package `realize` khác tên thư mục `QAQA_realize`.
  - `run_test.py` unpack sai số giá trị trả về.
  - Đường dẫn cứng tới `E:/FJNU/...`. Không có file requirements.
- **Bỏ qua confidence:** khớp thiếu bị đặt `[0,0,0]`. Trái/phải bị cố định. Nhịp bị bỏ qua, giả định 30 fps.
- **Có thể tham khảo (ghi nguồn Apache-2.0):** cách chia cửa sổ của FastDTW, công thức phạt bước của ACDTW, danh sách góc đặc trưng.

### Motion Embedding 24 thức (không license, chỉ học ý tưởng)

- **Dữ liệu:** ViTPose whole-body 2D, rồi MotionBERT 3D (Human3.6M-17), 10 fps.
- **Model:** ST-GCN-18 tạo embedding 256-d, train bằng triplet cosine. Positive được căn yaw rồi DTW theo anchor. Các bài làm dở (lớp 24–30) dùng làm hard negative.
- **Giao diện:** cứ 1,5 s so 10 frame webcam (MediaPipe) với 10 frame mẫu, không căn chỉnh. GOOD > 0,85, OK > 0,65.
- **Đánh giá không đáng tin:**
  - Chia ngẫu nhiên 10% file, nên cùng người xuất hiện ở cả train và test.
  - Chọn checkpoint theo test loss.
  - Top-1 retrieval trên embedding có sẵn chỉ khoảng 50%.
  - Khoảng thời gian bị xóa khi frame không có người.
  - Train trên 3D MotionBERT nhưng inference trên tọa độ MediaPipe world.
- **Ý tưởng nên dùng:**
  - Chuẩn hóa theo độ dài thân.
  - Độ tương đồng từng khớp có mask theo confidence.
  - Phản hồi theo từng giây.
  - Dùng bài làm dở làm hard negative.

### Hai repo Trường quyền của nhóm Pang/Zhang (không license, không dùng được làm benchmark)

**Intelligent-Scoring (Sci. Rep. 2025)**
- **Dữ liệu:**
  - `XingShenQuan.npy` có 52 clip × 32 keyframe × 28 đặc trưng, đã căn DTW.
  - `DengJianGeCaiYang` là **等间隔采样** (lấy mẫu đều), cùng clip nhưng không căn. Không phải tên bài.
  - Pose MediaPipe 3D, 33 khớp.
- **Lỗi đã kiểm chứng:**
  - `get_angle` chia cho `sqrt(|v1|²+|v2|²)` thay vì `|v1|·|v2|`.
  - Chỉ số khớp theo Kinect-25 nhưng áp lên MediaPipe-33, nên "khuỷu" thực ra là điểm mắt.
- **Điểm số:**
  - `QualityScore.npy`: 52 điểm đầu là giá trị 1 chữ số thập phân, 128 điểm sau là **bản sao thêm nhiễu** (r ≈ 0,99, max 10,12 vượt thang 10).
  - Không ghép được với X.
- **Đánh giá:** leave-one-out theo mẫu, trọng số ensemble lấy từ chính dự đoán test, "MAE" thực ra là median.

**Temporal Localization (ICETC 2022)**
- **Phương pháp:** pose PP-YOLOv2 + HRNet, không có classifier học. DTW chuỗi cosine với một video mẫu đã gán nhãn, rồi chuyển ranh giới động tác qua warping path.
- **Lỗi đã kiểm chứng:**
  - **Notebook cộng tay `L2[7..9] += 14, 18, 14` (46 lần đếm) vào các bin IoU 0,7–1,0 của camera 2.**
  - Điều kiện không chồng lấn dùng `and` thay cho `or`.
  - Frame không có người được điền số ngẫu nhiên.
- **Ý tưởng nên dùng:**
  - Chuyển nhãn qua warping path với open-begin DTW có band.
  - Báo cáo temporal IoU kèm sai số ranh giới theo giây.
  - Dùng SHAP trên lưới keyframe × metric để phản hồi chỉ ra đúng thức.

### OpenWushu: kho tri thức, chưa đầy đủ

| Bài | Trạng thái | Số động tác | Mốc thời gian | Vị trí thảm | Hướng mặt | Bước | Điểm mấu chốt | Lỗi hay gặp |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| taiji-42 | published | 42 | 42 | 42 | 1 | 42 | 42 | **2** |
| taiji-sword-42 | in_progress | 43 | 43 | 0 | 0 | 43 | 43 | 0 |
| 8 bài khác (changquan, southern-fist, binh khí) | awaiting | 50–68 | đủ | 0 | 0 | đủ | gần đủ | 0 |

- Nguồn là sách *IWUF 1st Compulsory Routines (B Junior)*. Mô tả được viết lại bằng lời của nhóm và có dẫn trang, vì không chép văn bản gốc có bản quyền.
- Mốc thời gian tính theo video tham chiếu của họ. Quyền dùng video đó là chuyện riêng.
- **Giá trị cho dự án:**
  - Danh mục động tác Trung/pinyin/Anh và cách chia đoạn.
  - Bước + điểm mấu chốt làm gợi ý cho rubric. HLV phải duyệt.
  - Lược đồ dữ liệu (number, section, start/end, carpet x/y, facing, steps/key_points/mistakes) đáng tham khảo cho ontology.
  - Không có bài 24 thức. Hầu như không có lỗi hay gặp.

### mmaction2

Xem `../sanda/REPOS.md` (mục mmaction2). Với Taolu:
- Đơn người dùng `num_person=1`.
- Graph `nturgb+d` đọc trực tiếp UMONS Kinect 25 khớp. HALPE_26 cần khai báo layout dạng dict.
- Chỉ dùng khi bước sang nhận diện thức (E01).

## Tổng kết: dùng được gì

| Nhu cầu trong v3 | Dùng | Không dùng |
|---|---|---|
| Pose HALPE_26 | rtmlib (qua code Sports2D tham khảo) + ONNX pin SHA | Toàn bộ pipeline Sports2D làm thư viện |
| Đọc video, timestamp | Tự viết (PyAV, PTS) | `round(fps)` của Sports2D |
| Tracking người tập | `sort_people_sports2d` + khóa target | Chọn người bằng click GUI |
| Mask/nội suy/lọc | Tự viết; tham số Butterworth/Hampel tham khảo | `fill_large_gaps_with='last_value'` |
| 3 metric (hông, thân, nhịp) | Tự viết trên tọa độ px | px→m, floor angle, trunk Neck→Hip |
| So sánh mẫu | Tự viết constrained DTW; tham khảo FastDTW/ACDTW (QAQA), ý tưởng chuẩn hóa/mask (Motion Embedding) | Code QAQA, embedding Motion Embedding |
| Phân đoạn tự động (sau) | Chuyển nhãn qua warping path (ý tưởng Zhang 2022); mmaction2 STGCN++ | Notebook Zhang 2022 |
| Chấm chất lượng (sau) | Ý tưởng: căn DTW → keyframe × metric, SHAP, so với ICC giữa trọng tài | Dữ liệu và code Pang 2025 |
| Ontology, rubric | OpenWushu (lược đồ + danh mục, CC BY-SA); TaiForm deduction criteria | Coi nội dung OpenWushu là chuẩn đã duyệt |

## Chưa clone

| Repo | Lý do |
|---|---|
| MMPose | Sports2D đã dùng RTMPose qua RTMLib. Chỉ cài khi cần fine-tune pose |
| GVHMR | 3D, thuộc phase E05. License NOASSERTION, phụ thuộc SMPL (phi thương mại) |
| dntod/wushu-judge | Repo chỉ có LICENSE và README, không có code |
