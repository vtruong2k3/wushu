# Dữ liệu Thái Cực Quyền đã tải

Tải ngày 13/11/2026 từ Zenodo API. Toàn bộ file đã kiểm tra md5 khớp với metadata Zenodo. Chưa chạy code nào từ nguồn ngoài.

```
datasets/taiji/
├── umons/
│   ├── raw/          # zip gốc, giữ để truy vết
│   └── extracted/
│       ├── Labels/            # 131 file .lab — nhãn phân đoạn trên chuỗi liên tục
│       ├── Kinect/            # 111 chuỗi skeleton chưa chia đoạn (512,7 MB)
│       └── Segmented_Kinect/  # 1.815 đoạn đã cắt (362,7 MB)
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
- Dữ liệu Qualisys (2,7–5,2 GB mỗi file) chưa tải. Chỉ tải khi cần ground truth mocap.

## TaiForm (Bát pháp Ngũ bộ), chỉ tham khảo

- **Annotation:** 5 người (102, 108, 116, 118, 141). Mỗi file có 6 sheet, có thể là 6 góc quay. Mỗi sheet có `Action Label`, `Start Frame`, `End Frame`, gồm cả tên thức và các *scoring frame* (mốc chấm). Một số mốc có giá trị `0, 0`, có thể là thiếu nhãn, cần kiểm tra.
- **Deduction Criteria:** gồm thức → scoring frame → mô tả tư thế chuẩn → các lỗi trừ 0,1 điểm, nhiều lỗi có ngưỡng đo được (ví dụ "lệch > 5 cm", "lệch > 15°", "< 1 s"). Đây là mẫu tốt để thiết kế rubric có thể đo được cho bài 24 thức.
- **Video:** khoảng 17,4 GB, chưa tải. Tác giả ghi đây là mẫu tạm cho phản biện, không phải bản phát hành chính thức.
- **Không trộn** nhãn hay tiêu chí của bài này với bài 24 thức.

## Chưa tải

| Dataset | Lý do |
|---|---|
| TaiChi-AQA, TaiChi-24, PSU-TMM100 | Phải gửi yêu cầu truy cập. Xem `Docs/DATASET_REGISTRY_TAIJI.md` |
| Motion Embedding 24-form | Repo không có license, chưa có quyền tái sử dụng |
| UMONS Qualisys (TSV/C3D) | Chưa cần, khoảng 15 GB |
| TaiForm video | 17,4 GB, chưa rõ phạm vi sử dụng của bản mẫu phản biện |
