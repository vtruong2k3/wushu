# Dữ liệu Thái Cực Quyền đã tải

Tải ngày 13/11/2026 từ Zenodo API. Toàn bộ file đã kiểm tra md5 khớp với metadata Zenodo. Chưa chạy code nào từ nguồn ngoài.

```text
datasets/taiji/
├── umons/
│   ├── raw/          # zip gốc, giữ để truy vết
│   └── extracted/
│       ├── Labels/            # 131 file .lab — nhãn phân đoạn trên chuỗi liên tục
│       ├── Kinect/            # 111 chuỗi skeleton chưa chia đoạn (512,7 MB)
│       ├── Segmented_Kinect/  # 1.815 đoạn đã cắt (362,7 MB)
│       └── Segmented_C3D/     # 2.149 đoạn mocap Qualisys .c3d (3,53 GiB), tải 2026-11-15
├── balance_figshare/          # Figshare, CC BY 4.0, tải 2026-11-15 (mục riêng bên dưới)
│   ├── raw/
│   └── extracted/
└── taiform/
    ├── raw/
    │   ├── Five_subject_sample_for_peer_review_Annotation_Results.rar
    │   └── Deduction_Criteria_Bafa_Wubu.xlsx
    └── extracted/Five_subject_sample_for_peer_review_Annotation_Results/  # 5 file xlsx
```

## Provenance

| File | Nguồn | md5 | Bytes |
|---|---|---|---:|
| umons/raw/Labels.zip | zenodo.org/records/2784581 | 35de96a035c9d3b41619ac1f9932f946 | 42.456 |
| umons/raw/Segmented_Kinect.zip | zenodo.org/records/2784581 | f783bbe1c8c19dbebb9ca3dbc2265f83 | 152.968.528 |
| umons/raw/Kinect.zip | zenodo.org/records/2784581 | d2802095beec3736ecfb35ab4eac70e8 | 216.919.024 |
| umons/raw/Segmented_C3D.zip (tải 2026-11-15) | zenodo.org/records/2784581 | 6b2746280984014fb18a59f38d0a95d2 | 2.668.864.662 |
| taiform/raw/…Annotation_Results.rar | zenodo.org/records/19656906 | 91b9d8e74524a4eb35a51ab06d3b1d3f | 126.286 |
| taiform/raw/Deduction_Criteria_Bafa_Wubu.xlsx | zenodo.org/records/19656906 | 406463c63f05493e27b401267ff5e539 | 18.762 |

File xlsx tiêu chí được đổi tên khi lưu. Tên gốc: `Deduction Criteria for Taijiquan (Bafa Wubu) Competition Routine .xlsx`.

## UMONS-TAICHI

**License:** `License.txt` trong cả 3 zip ghi **CC BY-NC-SA 4.0**. Điều khoản này là của chính bản dữ liệu, dù metadata Zenodo ghi `cc-by-4.0`. Chỉ dùng phi thương mại, ghi nguồn và chia sẻ cùng điều khoản. Trích dẫn: Tits et al., *UMONS-TAICHI*, Data in Brief, 2018, doi:10.1016/j.dib.2018.05.088.

**Định dạng Kinect `.txt`:** mỗi dòng là một frame, gồm 76 trường: timestamp (ms) + 25 khớp × (x, y, z). Kinect V2, 30 Hz, đơn vị mm. Chuỗi mẫu `P01T01C03` có 4.120 frame.

**Định dạng `.lab`:** mỗi dòng có thời điểm (giây) và nhãn. `_` là đoạn nghỉ/chuyển tiếp.

**Tên file đã cắt `PxxTxxCxxGxxDxxSxx`.** Ý nghĩa dưới đây tôi suy ra từ thống kê, cần đối chiếu với bài báo:

| Mã | Giá trị thấy | Suy luận |
|---|---|---|
| P | 01–12 | Người tập (khớp Metadata.txt) |
| T | 01–03 | Trial / buổi |
| C | 01–15 | Chuỗi ghi (capture) trong buổi |
| G | 01–13 | 13 lớp động tác. Nhãn `.lab` có ex1–ex5 và tech1–tech8 |
| D | 01–02 | Bên trái/phải. Nhãn có hậu tố `l`/`r` |
| S | 01–05 | Lần lặp |

**Thống kê:**

- 1.815 đoạn Kinect. Con số 2.200 trong mô tả gốc có thể tính theo Qualisys.
- Mỗi đoạn dài 18–1.147 frame, trung vị 225.
- G01/G02 chỉ có 32 đoạn mỗi lớp. Các lớp khác có 121–180 đoạn.

**Trình độ người tập:** Metadata.txt trên GitHub có 12 người, 3 chuyên gia chấm 0–10, chia thành Expert / Advanced / Intermediate / Novice. Điểm này là **theo người**, không theo từng đoạn.

**Giới hạn:**

- Đây là 13 kỹ thuật cơ bản, không phải bài 24 thức.
- Skeleton Kinect V2 có 25 khớp, khác HALPE_26 của pipeline video. Cần joint mapping riêng.
- Dữ liệu Qualisys: chỉ `Segmented_C3D.zip` đã tải (xem mục dưới); các file TSV và C3D chưa phân đoạn (2,7–5,2 GB mỗi file) chưa tải, chỉ tải khi cần.

**Segmented_C3D (tải ngày 2026-11-15, task X.16):** zip 2.668.864.662 byte, md5 khớp công bố của Zenodo; sha256 `a921f9c9f1914170ee472db7d3d9538b461c1c46b0acda8cdac3d44ef2d95b4f`. Trước khi giải nén đã kiểm từng thành viên bằng script: 2.151 thành viên (2.150 file, 1 thư mục), không có đường dẫn tuyệt đối, `..`, dấu `\`, liên kết, tên trùng hay thành viên mã hóa; tỉ lệ nén cao nhất 1,6; 3,53 GiB sau giải nén. Nội dung: 2.149 file `.c3d` và `License.txt`. **License:** `License.txt` ghi CC BY-NC-SA 4.0, khớp mục License ở trên. Tên file theo cùng mẫu `PxxTxxCxxGxxDxxSxx` với phần Kinect; cả 2.149 tên đều đúng mẫu, 12 người (P) và 13 lớp (G); kích thước từ 106 KB đến 7,9 MB (trung vị 1,4 MB). Con số này khác 1.815 đoạn Kinect và 2.200 mẫu ở mô tả gốc; chưa tìm lý do. **Chưa mở nội dung `.c3d`** (không có việc nào dùng ngay; marker 68, 179 Hz theo mô tả của Zenodo, chưa kiểm).

## TaiForm (Bát pháp Ngũ bộ), chỉ tham khảo

- **Annotation:** 5 người (102, 108, 116, 118, 141). Mỗi file có 6 sheet, có thể là 6 góc quay. Mỗi sheet có `Action Label`, `Start Frame`, `End Frame`, gồm cả tên thức và các *scoring frame* (mốc chấm). Một số mốc có giá trị `0, 0`, có thể là thiếu nhãn, cần kiểm tra.
- **Deduction Criteria:** gồm thức → scoring frame → mô tả tư thế chuẩn → các lỗi trừ 0,1 điểm, nhiều lỗi có ngưỡng đo được (ví dụ "lệch > 5 cm", "lệch > 15°", "< 1 s"). Đây là mẫu tốt để thiết kế rubric có thể đo được cho bài 24 thức.
- **Video:** khoảng 17,4 GB, chưa tải. Tác giả ghi đây là mẫu tạm cho phản biện, không phải bản phát hành chính thức.
- **Không trộn** nhãn hay tiêu chí của bài này với bài 24 thức.

## Raw data of typical balance movements of Tai Chi (Figshare), tải ngày 2026-11-15

Nguồn: DOI 10.6084/m9.figshare.22574185.v1 (task X.16). **License CC BY 4.0**, ghi nguồn: Li, Haojie (2023), *Raw data of typical balance movements of Tai Chi*, figshare, và bài báo PeerJ 2023 (Li và cộng sự). Chưa chạy code nào từ nguồn ngoài.

| File | Nguồn | md5 | Bytes |
|---|---|---|---:|
| balance_figshare/raw/Raw_data_Tai_Chi.rar | ndownloader.figshare.com/files/40062664 | d6f770b7f0904d937f64672a1f6ceee4 | 211.846.155 |

md5 và số byte khớp giá trị công bố trong API Figshare. sha256: `9d123bafc2051810573d51b771415e9c17df5d976282bd2592f4d8c68c6f4297`. File được đổi tên khi lưu; tên gốc `Raw data (Tai Chi).rar`.

**Kiểm tra trước khi giải nén:** liệt kê bằng bsdtar, không có đường dẫn tuyệt đối, không có `..`, không có liên kết; 16 file `.xlsx` và 3 thư mục, 233.851.850 byte sau giải nén. Giải nén vào `balance_figshare/extracted/Raw data (Tai Chi)/{Amateur,Professional}/Participant1..8.xlsx` (223 MiB).

**Nội dung (đọc tên sheet và vùng dữ liệu, chưa phân tích số liệu):** mỗi workbook có 10 sheet: lực cơ (Muscle strength), hoạt động cơ (Activity), lực khớp (Joint force), mô-men khớp (Joint torque) và góc khớp (Joint Angle), mỗi loại cho bên phải (R) và bên trái (L); khoảng 300 đến 1.840 dòng mỗi sheet. Không có macro. Đây là kết quả mô hình sinh cơ học chi dưới (AnyBody) cho hai động tác thăng bằng; **không có tọa độ marker, không có thân hay vai, không có video**.

**Giới hạn:** 16 nam, hai động tác, chi dưới. Không phục vụ ba số đo của MVP (độ cao hông trên ảnh, độ nghiêng thân, nhịp) và không dùng được cho nghiên cứu camera ảo vì không có vị trí khớp trong không gian. Tên sheet có vài chỗ lệch chữ (ví dụ `Joint torqueL`, `Joint AngleL`); đọc theo tên đã in khi cần.

## Chưa tải

| Dataset | Lý do |
|---|---|
| TaiChi-AQA, TaiChi-24, PSU-TMM100 | Phải gửi yêu cầu truy cập. Không gửi (DEC-0018, DEC-0019). Xem `Docs/DATASET_REGISTRY_TAIJI.md` |
| Motion Embedding 24-form | Repo không có license, chưa có quyền tái sử dụng; kiểm lại 2026-11-15, không tải |
| UMONS Qualisys TSV (2 file) và C3D chưa phân đoạn | Chưa cần, khoảng 12,7 GB. Segmented_C3D đã tải (xem trên) |
| TaiForm video | 17,4 GB, chưa rõ phạm vi sử dụng của bản mẫu phản biện |
| Tai Chi gait (PhysioNet, D19) | Dữ liệu đi bộ, không phải Thái cực quyền; không có việc nào dùng, ZIP 1,5 GB |
