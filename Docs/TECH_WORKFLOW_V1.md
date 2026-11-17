# Workflow và công nghệ — Thái Cực Quyền AI (MVP v3)

**Phiên bản:** 1.1 · **Ngày:** 13/11/2026 · **Cập nhật:** 14/11/2026 (UI chuyển sang React + Vite + FastAPI, DEC-0008, task X.04)
**Đối tượng đọc:** kỹ sư ML/CV (A), kỹ sư full-stack (B), chủ dự án (O)
**Quan hệ với kế hoạch:** triển khai kỹ thuật cho `WUSHU_TAIJIQUAN_MASTER_PLAN_V3.md`, Phase 00–05.

Tài liệu này **thay hai quyết định của v3**:

1. Không dùng Sports2D làm thư viện. Thay vào đó gọi trực tiếp rtmlib và tự viết phần đọc video, mask, lọc và metric (DEC-0001).
2. **UI không dùng Streamlit** mà dùng React + Vite + TypeScript, với backend FastAPI (DEC-0008, 14/11/2026).

Lý do nằm ở mục 1.2, `repos/taolu/REPOS.md` và `Docs/tracking/DECISIONS.md`.

> Đây là thiết kế, chưa phải hệ thống đã chạy. Mọi phiên bản thư viện, ngưỡng và tham số đều phải chốt sau P00.05 (kiểm kê phần cứng) và P01 (chạy trên video thật).

---

## Mục lục

1. Quyết định công nghệ
2. Workflow tổng thể
3. Chi tiết từng bước (W0–W9)
4. Hợp đồng dữ liệu và lưu trữ
5. Kiến trúc code
6. Môi trường, model và tái lập
7. Workflow dữ liệu và gán nhãn
8. Workflow đánh giá và nghiệm thu
9. Quy trình phát triển
10. Bảo mật, quyền dữ liệu và license
11. Công nghệ cho các phase mở rộng
12. Quyết định còn mở

Phụ lục A: skeleton HALPE_26 · Phụ lục B: công thức metric · Phụ lục C: thuật toán so sánh mẫu

---

## 1. Quyết định công nghệ

### 1.1 Stack MVP

| Lớp | Công nghệ | License | Vai trò | Ghi chú |
|---|---|---|---|---|
| Ngôn ngữ | Python 3.12 | PSF | Toàn bộ pipeline và API | Đã chốt (DEC-0002): PyAV 19 yêu cầu ≥ 3.12 |
| Quản lý môi trường | `uv` + `uv.lock` | MIT/Apache | Cài và khóa dependency | Mỗi stack nặng một môi trường riêng (mục 6) |
| Video I/O | FFmpeg / ffprobe | LGPL/GPL tùy build | Metadata, proxy, cắt clip, tách audio | Gọi dạng CLI, không link thư viện |
| Đọc frame + PTS | PyAV | BSD-3 | Đọc frame kèm presentation timestamp | Không dùng `round(CAP_PROP_FPS)` |
| Pose | rtmlib + RTMPose-m HALPE_26 (ONNX) | rtmlib: Apache-2.0; weights: xem 10.3 | Keypoint 2D 26 điểm, có bàn chân | Weights lưu local, pin SHA-256 |
| Inference runtime | onnxruntime-gpu (fallback: onnxruntime CPU) | MIT | Chạy ONNX | Chọn bản khớp CUDA/cuDNN của máy |
| Tính toán | NumPy, SciPy | BSD | Mask, lọc, metric, DTW | Numba tùy chọn để tăng tốc DTW |
| Schema | Pydantic v2 | MIT | Manifest, config, dữ liệu trao đổi | Có version trong mọi file |
| Metadata | SQLite (stdlib `sqlite3`) | Public domain | Video, đoạn, run, review | Một file DB, có backup |
| Artifact | Thư mục theo UUID + Parquet/NPZ/JSON | — | Pose, metric, report | Ghi atomic (mục 4.4) |
| API | FastAPI + uvicorn | MIT / BSD-3 | REST `/api/*`, phục vụ video proxy (HTTP Range) và file build của web | Chỉ lắng nghe `127.0.0.1`; không chạy việc nặng trong process API |
| UI | React + Vite + TypeScript (SPA) | MIT | Các màn Video / Số đo / So sánh / Báo cáo | `<video>` + `requestVideoFrameCallback` cho đánh dấu chính xác từng frame (mục 3, W3) |
| UI: dữ liệu | TanStack Query, React Router | MIT | Gọi API, cache, điều hướng | Client API có kiểu (TypeScript) |
| UI: biểu đồ | Thư viện time-series nhẹ (ứng viên uPlot, MIT), chốt ở P8.08 | MIT | Đường cong metric đồng bộ với video | Plotly chỉ dùng cho report HTML tĩnh |
| Kiểm thử UI | Vitest (unit), Playwright (E2E) | MIT / Apache-2.0 | Component, luồng G04 | Vitest chạy trong `tools/check.ps1`; Playwright thêm ở P8.15 |
| Node toolchain | Node.js ≥ 24, pnpm | MIT | Build/dev frontend | Chỉ cần lúc phát triển và build |
| Biểu đồ report | Plotly | MIT | Biểu đồ trong report HTML tĩnh | Không dùng cho UI tương tác (xem "UI: biểu đồ") |
| Report | Jinja2 → HTML; JSON/CSV | BSD | Báo cáo có bằng chứng | Snapshot bất biến |
| Kiểm thử | pytest, hypothesis (tùy chọn) | MIT/MPL | Unit, contract, golden test | Fixture video sinh bằng FFmpeg |
| Gán nhãn keypoint | CVAT (self-host) hoặc tool nội bộ tối giản | MIT | Audit 200 frame | Chỉ cần export COCO keypoints |

### 1.2 Những gì không dùng, và lý do

| Thành phần | Lý do không dùng ở MVP | Dùng thay |
|---|---|---|
| Sports2D làm thư viện | Mặc định điền gap bằng `last_value` (tạo pause giả); chỉ lưu dữ liệu đã lọc; thời gian tính bằng `frame/round(fps)`; import là tắt SSL toàn process; kéo theo OpenSim/Qt | rtmlib trực tiếp + code tự viết. Tham khảo thuật toán tracking của Sports2D/Pose2Sim |
| Ultralytics YOLO | AGPL-3.0 | YOLOX/RTMDet trong rtmlib |
| Code QAQA, Motion Embedding, Pang/Zhang | Có lỗi hoặc không có license | Tự viết constrained DTW (Phụ lục C) |
| Streamlit | `st.video` không trả thời điểm đang phát; so sánh 2 video đồng bộ và biểu đồ chạy theo video đều phải viết custom component JS (DEC-0008) | React + Vite + FastAPI |
| Next.js | Cần thêm server Node; SSR/SEO/routing phía server không cần cho app nội bộ một máy; API routes dễ trùng với FastAPI (DEC-0008) | React SPA build tĩnh, FastAPI phục vụ |
| PostgreSQL/hàng đợi phân tán | Chưa cần ở MVP một người dùng | Để dành cho E02 (FastAPI đã có từ MVP) |
| LLM coach | Không cần cho 3 metric; rủi ro bịa nhận xét | Nhận xét theo template, HLV duyệt |

---

## 2. Workflow tổng thể

```mermaid
flowchart LR
  subgraph Thu["Thu thập"]
    W0["W0 Quay 2 camera\n+ tín hiệu đồng bộ"]
  end
  subgraph Nap["Nạp dữ liệu"]
    W1["W1 Ingest\nhash, ffprobe, PTS map, proxy"]
    W2["W2 Đồng bộ camera\noffset, drift, residual"]
  end
  subgraph Doan["Chọn đoạn"]
    W3["W3 HLV chọn đoạn\naction, side, view, reference"]
  end
  subgraph Xuly["Xử lý"]
    W4["W4 Pose\nrtmlib HALPE_26"]
    W5["W5 Khóa người tập\ntracking + cờ mất dấu"]
    W6["W6 Quality mask\nraw / mask / filtered"]
    W7["W7 Metric\nhông, thân, nhịp"]
    W8["W8 So sánh mẫu\nconstrained DTW"]
  end
  subgraph Ra["Kết quả"]
    W9["W9 Review + Report\nHLV xác nhận, snapshot"]
  end
  W0 --> W1 --> W2 --> W3 --> W4 --> W5 --> W6 --> W7 --> W8 --> W9
  W6 -. "coverage thấp" .-> W3
  W9 -. "sửa đoạn" .-> W3
```

| Bước | Đầu vào | Đầu ra | Công cụ | Người làm | Điểm dừng |
|---|---|---|---|---|---|
| W0 | Protocol quay | 2 file video gốc / take | Điện thoại, giá đỡ | A + O | Thiếu tín hiệu đồng bộ → quay lại take |
| W1 | Video gốc | `recording.json`, `pts.parquet`, proxy | ffprobe, PyAV, FFmpeg | Tự động | Video hỏng, quay xoay chưa xử lý |
| W2 | 2 recording cùng take | `sync.json` | FFmpeg (audio), SciPy | Tự động + A duyệt | Residual vượt ngưỡng → chỉ cho review song song |
| W3 | Proxy video | `segment` (revision) | React video player + FastAPI | HLV | Đoạn không ghi view/action |
| W4 | Video gốc + segment | `pose_raw.npz` | rtmlib, onnxruntime | Tự động | Model checksum sai |
| W5 | Pose raw (nhiều người) | `track.parquet` (1 người) | Code nội bộ | Tự động + người dùng chọn | Mất dấu > ngưỡng → cờ |
| W6 | Track | `pose_masked.npz`, `pose_filtered.npz`, `quality.json` | NumPy/SciPy | Tự động | Coverage dưới ngưỡng metric |
| W7 | Pose filtered + mask | `metrics.parquet`, `metric_summary.json` | NumPy | Tự động | Metric không đủ điều kiện → `insufficient_evidence` |
| W8 | 2 đoạn cùng động tác | `alignment.npz`, `comparison.json` | Code DTW nội bộ | Tự động | Khác action/view → từ chối |
| W9 | Metric + so sánh + nhận xét | `report/` snapshot | Jinja2, Plotly, FFmpeg | HLV | Nhận xét chưa duyệt không vào bản cuối |

---

## 3. Chi tiết từng bước

### W0 — Quay hai camera

**Cấu hình:**
- Đặt 2 camera theo **trục hướng chính của bài**: một chính diện, một ngang (lệch 90°). Không đặt góc tùy ý.
- Các thức đi chéo góc được ghi trước là vùng có coverage thấp.
- 1080p, khóa ở 30 fps hoặc 60 fps. Khóa zoom, phơi sáng và lấy nét.
- Dùng ứng dụng quay cho phép **cố định frame rate** (ví dụ Blackmagic Camera, Open Camera) để hạn chế video VFR.

**Đồng bộ:** vỗ tay hai lần kèm đèn/flash nhìn thấy được ở **đầu và cuối** mỗi take.

**Tham chiếu:**
- Quay 3–5 s người tập đứng thẳng ở vị trí xuất phát. Đoạn này cho scale và góc đứng.
- Nếu có thể, quay bảng checkerboard để giữ khả năng hiệu chuẩn 3D về sau.

**Metadata ghi tay** (form trong app hoặc CSV): `session_id`, `participant_id` (giả danh), `take_id`, `camera_id`, vị trí máy, chiều cao máy, hướng bài, consent reference.

**Thời gian một buổi:** mỗi buổi nhóm cần khoảng 1,5–2 giờ (setup, đồng bộ, 3 lần × 6 phút/người, nghỉ).

### W1 — Ingest

1. Copy file gốc vào `data/recordings/<recording_uuid>/source.<ext>`, chỉ đọc. Tính SHA-256.
2. Chạy `ffprobe -show_streams -show_format -of json` để lấy codec, kích thước, rotation metadata, `r_frame_rate`, `avg_frame_rate`, `time_base`, duration và audio stream.
3. Đọc toàn bộ PTS bằng PyAV để tạo `pts.parquet` (`frame_index`, `pts`, `t_sec = pts × time_base`).
   - Tính `dt` và đánh dấu VFR nếu `std(dt)/median(dt)` vượt ngưỡng (đề xuất 1%).
   - Chỉ đếm frame mà decoder thật sự xuất ra: packet gắn cờ *discard* không phải frame. Clip cắt trên điện thoại (stream copy
     bắt đầu giữa hai keyframe) có edit list; các packet trước điểm bắt đầu vẫn nằm trong file với pts âm và bị decoder bỏ.
     Đếm chúng làm dòng *i* của `pts.parquet` không còn là frame *i* đã decode (BUG-0052, DEC-0030).
4. Xử lý rotation: lưu `display_rotation`. Hoặc áp xoay một lần khi tạo proxy, hoặc xoay frame trước khi chạy pose. Ghi transform vào manifest.
5. Tạo proxy H.264 cho playback trên trình duyệt:
   `ffmpeg -i source -map 0:v:0 -vf "scale=-2:'min(720,ih)'" -c:v libx264 -preset veryfast -crf 23 -g 30 -pix_fmt yuv420p -fps_mode passthrough -an -movflags +faststart -map_metadata -1 proxy.mp4`
   - Map thời gian proxy ↔ nguồn bằng PTS (proxy giữ timestamp nguồn, không phóng to nguồn nhỏ).
   - Xóa metadata vị trí/thiết bị (`-map_metadata -1`).
   - Kiểm tra sai lệch ≤ 1 frame trên các điểm mẫu (tối đa 10 điểm), ghi `proxy.json` (`proxy/1`).
   - Proxy không đạt kiểm tra vẫn được giữ và đánh dấu `passed = false` (UI không dùng nó cho thao tác chính xác từng frame);
     lệnh `taiji proxy` và `taiji ingest --proxy` thoát với mã 1 và vẫn in recording ID (DEC-0030). Điều không đo được thì
     báo lỗi, không ghi số bịa.
6. Ghi `recording.json` (mục 4.2).

**Kiểm thử cần có:** fixture VFR, fixture có rotate 90°, file hỏng, file 0 byte, video không có audio.

### W2 — Đồng bộ camera

1. Tách audio mono 16 kHz cho từng camera: `ffmpeg -i source -vn -ac 1 -ar 16000 audio.wav`
2. Lấy envelope (trị tuyệt đối → lọc thông thấp). Dùng `scipy.signal.correlate` trong cửa sổ đầu take để có `offset_start`, cửa sổ cuối take để có `offset_end`.
   - Cửa sổ cuối là `window_s` giây cuối của đoạn **cả hai camera cùng ghi** (không phải của riêng A), và ở camera B được tìm
     đúng chỗ `offset_start` dự đoán, trong một lát B rộng hơn cửa sổ của A một biên ở hai phía (cắt trong vùng B đã ghi, không
     đệm số 0), biên = `end_margin_s` 3,5 s cộng phần drift cho phép (`max_drift` 500 ppm); như vậy kết
     quả không phụ thuộc máy nào dừng trước (BUG-0058). Biên 3,5 s phải rộng hơn khoảng cách giữa hai tiếng vỗ (khoảng 1 s,
     tối đa 2 s) để khớp thật của một drift vô lý vẫn là đỉnh tốt nhất rồi bị giới hạn drift loại, thay vì một tiếng vỗ lẻ
     khớp nhầm trong dải hợp lý. Không tìm được đầu thì không tìm cuối.
   - Một cửa sổ được tìm rộng hơn mức được chấp nhận (cửa sổ đầu: `max_lag_s` 15 s + vùng đệm 3,5 s; cửa sổ cuối: biên trên), để
     khớp thật nằm sát mép vẫn là đỉnh tốt nhất rồi bị loại, thay vì một tiếng vỗ lẻ khớp nhầm ngay trong dải. Đỉnh thứ hai được tìm
     ngoài 0,2 s quanh đỉnh tốt nhất (nhỏ hơn khoảng cách hai tiếng vỗ của một cặp, ≥ 0,3 s).
   - Drift vượt `max_drift` (500 ppm) không phải là đồng hồ: cửa sổ cuối bị loại, trạng thái `start_only`. `max_drift` cũng là phép
     kiểm chứng chéo giữa hai phép đo (lỗi E ở một cửa sổ hiện ra thành drift E/dt): một tiếng vỗ khớp nhầm ở một đầu bị loại, với
     lỗi 1 s thì đến take 2000 s. Lỗi giống hệt ở cả hai đầu (cặp bị hỏng như nhau) âm thanh không phát hiện được: flash ở cả hai đầu
     (bước 4) mới quyết định dùng được (BUG-0063).
   - Track audio bị mất mẫu (PTS nhảy quá 2 ms) bị từ chối khi tách audio, không tự vá (BUG-0058..0062, DEC-0033).
3. `drift = (offset_end − offset_start) / (t_ref_end − t_ref_start)`, với `t_ref` là thời điểm của tiếng vỗ tay đã khớp trên trục video
   của camera A, không phải tâm cửa sổ tìm kiếm (BUG-0059). Mapping: `t_cam2 = t_cam1 + offset_start + drift × (t_cam1 − t_ref)`.
4. Kiểm chứng bằng mốc nhìn thấy (frame flash). `residual` = sai lệch giữa mốc audio và mốc hình, tính theo ms và theo frame.
   Flash đi theo cặp (cách nhau khoảng 1 s) như tiếng vỗ tay, nên mỗi cửa sổ được ghép **một-một theo thứ tự thời gian**: hai
   camera phải thấy **cùng số flash, ít nhất hai**; flash thứ i của A so với flash thứ i của B; `residual` của cửa sổ là khoảng
   cách **lớn nhất**, không phải trung bình. Số flash khác nhau hoặc ít hơn hai thì cửa sổ không kết luận được (không có
   residual, take không dùng được cho metric). Ghép theo flash gần nhất, bỏ flash không có cặp và lấy trung bình từng để lọt
   một mapping lệch đúng một khoảng cách cặp (1 s) khi một camera không thấy một flash của cặp (BUG-0064, DEC-0034).
5. Ghi `sync.json`: `method`, `offset`, `drift`, `residual_ms`, `validated_by`.
6. Quy tắc dùng:
   - Residual ≤ 1 frame: cho ghép metric theo thời gian.
   - Lớn hơn: chỉ hiển thị song song, mốc do HLV xác nhận (C05 trong v3).

### W3 — HLV chọn đoạn

Giao diện tab **Video**:
- Phát proxy, tua từng frame, đánh dấu start/end.
- Chọn `action` (theo ontology v0), `side`, `occurrence`, `camera_id`, `view_category` (front/side/oblique/back), cờ `orientation_change`, `occlusion`, `perspective_shift`.
- Chọn reference cùng action/variant/view.

Mỗi lần sửa tạo `segment_revision` mới. Không ghi đè revision cũ.

**Video player (React):**
- FastAPI phục vụ `proxy.mp4` có hỗ trợ HTTP Range (để tua) và bảng PTS dạng JSON.
- Component dùng `requestVideoFrameCallback()` để lấy `mediaTime` của frame đang hiển thị; có nút ±1 frame.
- Timestamp nhận được là thời gian **proxy**. Đổi sang PTS nguồn qua bảng PTS, chọn frame nguồn gần nhất; gửi về API khi lưu segment.
- Trình duyệt mục tiêu: Chromium (Chrome/Edge) bản hiện hành, vì `requestVideoFrameCallback` cần được hỗ trợ đầy đủ.

Phương án dự phòng (P8.05b): HLV đánh dấu trong Kinovea hoặc ELAN rồi import CSV.

### W4 — Pose

- **Model:** `BodyWithFeet` của rtmlib, chế độ `balanced` (YOLOX-m HumanArt + RTMPose-m body7-halpe26).
  - Trước P01 phải tải ONNX thủ công một lần, tính SHA-256 và ghi vào `models/registry.json`.
  - Khi chạy, truyền **đường dẫn local** cho model detector và pose (kiểm tra tham số API tại commit rtmlib đã pin).
  - Pipeline **không được** tự tải model lúc chạy.
- **Đọc frame:** dùng PyAV theo PTS trong khoảng `[start, end]` của segment, thêm lề 1 s hai đầu để bộ lọc ổn định.
- **Output thô:** cho mọi người phát hiện được trong từng frame, lưu bbox, 26 keypoint (x, y theo pixel ảnh đã xoay đúng chiều), score và `t_sec`.
  - Lưu `pose_raw.npz`. Mảng có độ dài biến đổi thì lưu dạng ragged hoặc padded kèm `n_persons`.
- **Backend:** `onnxruntime` với `CUDAExecutionProvider`, fallback CPU. Ghi provider thực dùng vào run manifest.
- **Hiệu năng:** đo `processing_seconds / video_seconds` và peak VRAM ở P01. Batch không bắt buộc ở MVP.
  Đã đo ở P3.07 (`Docs/reports/p3_pose_benchmark.md`; clip D20, không phải clip điện thoại của P1.09; RTX 3060 12 GB dùng chung với màn hình; 5 clip 30 s, 3 lượt đo): RTF 1,23 (N = 1), 0,335 (N = 5), 0,259 (N = 10) trên video 24 và 30 fps; ở 30 fps là 1,47 / 0,40 / 0,31.
  Detector chiếm 73 % thời gian ở N = 1 (khoảng 36 ms mỗi lần gọi), pose khoảng 8 ms mỗi frame một người, decode 5 đến 21 %. VRAM đỉnh 1,8 đến 2,0 GB tổng (0,6 đến 0,8 GB trên mức các chương trình khác đang giữ), còn trống khoảng 10 GB.
  Một đoạn 30 s qua cả tầng pose (đến khi lưu `track.parquet`): 37 đến 46 s (N = 1), 10 đến 13 s (N = 5). Luật chọn N viết trước khi đo khuyến nghị **N = 1** (N = 5 lệch khỏi N = 1 trên keypoint người tập: trung vị 2,0 px, p95 9,7 px, p99 21,7 px); P3.08 so hai cadence trên các frame đã gán nhãn và không thấy bằng chứng N = 1 ít lỗi hơn (61 lỗi: 36 ở cả hai, 10 chỉ ở N = 1, 5 chỉ ở N = 5, 10 chưa rõ), nên **maintainer giữ N = 5** (DEC-0042, 2026-11-16); xem lại khi có clip của mình (X.27, X.28).

**Định dạng `pose_raw.npz` (schema `pose_raw/1`, P3.03, `pose/raw_io.py`, `schemas/pose.py`).** Chín mảng tên và kiểu cố định: `frame_index` (F,) int32 (dòng của frame trong `pts.parquet`, tăng ngặt);
`t_sec` (F,) float64 (PTS thật, tăng ngặt); `person_offsets` (F + 1,) int64 (người của frame `i` là dòng `[i]:[i + 1]`; bắt đầu từ 0, không giảm, kết thúc ở D); `bboxes` (D, 4) float32 xyxy [px];
`keypoints` (D, 26, 2) float32 (pixel ảnh đã xoay đúng chiều, y xuống, đúng như mô hình trả về); `scores` (D, 26) float32; `from_detector` (D,) bool; `schema_version` (chuỗi 0-d, `"pose_raw/1"`);
`meta_json` (chuỗi 0-d: `PoseRawMeta` gồm `skeleton`, `recording_id`, `image_size`, `display_rotation`, `segment_s`, `params`, `model_fingerprint`, `providers` và các số đếm xác định). Frame không có người có 0 dòng.
Keypoint và score không bị kiểm khoảng giá trị, cắt hay điền; NaN giữ nguyên. Thời gian chạy thật (wall clock) không nằm trong file mà nằm trong `run_manifest.json` (`runtime`). Đọc nghiêm ngặt: thiếu hay thừa mảng, sai kiểu hay shape,
số đếm lệch, khác phiên bản hay skeleton đều là `PoseRawError` nêu tên trường; mỗi phiên bản có một bộ đọc (`_READERS`), file cũ không bao giờ bị nâng cấp ngầm. Byte của `.npz` không xác định (timestamp trong zip):
so sánh theo nội dung (`PoseRaw.equals`), còn run manifest ghi SHA-256 của file đã ghi (`save_pose_raw` trả về).

Không lật gương ảnh. Người quay lưng vẫn giữ nhãn trái/phải do model trả về và được kiểm tra ở W6.

### W5 — Khóa người tập

1. Ở frame đầu segment (hoặc frame do người dùng chọn), hiển thị bbox các người phát hiện được. Người dùng chọn người tập. Mặc định chọn bbox lớn nhất gần tâm.
   Quy tắc cụ thể (P3.04, `track/target.py`, giá trị tạm): chỉ xét người đủ điều kiện (đủ `min_valid_keypoints` keypoint hợp lệ, bbox có diện tích); điểm = `diện tích bbox / diện tích ảnh × độ gần tâm` với
   `độ gần tâm = 1 − min(1, d / nửa đường chéo ảnh)`, `d` là khoảng cách từ tâm bbox đến tâm ảnh; điểm bằng nhau lấy dòng thấp hơn. Frame đầu segment không có ai đủ điều kiện thì tìm tiếp về phía sau tối đa 2 s
   (không bao giờ về trước điểm bắt đầu), không có thì báo lỗi, không đoán. Hai người có điểm gần nhau (điểm thứ hai / điểm tốt nhất ≥ 0,6) thì kết quả mang cờ `ambiguous` để UI hỏi lại. Khi người dùng chỉ định bbox:
   chọn người có IoU lớn nhất (≥ 0,3, kể cả người yếu, có cờ `weak`); bbox không khớp ai, hoặc bao hai người (IoU tốt nhất chưa gấp 1,5 lần IoU thứ hai) thì báo lỗi, không chọn người gần nhất. Lựa chọn (`bbox`, `at_t_sec`)
   nằm trong yêu cầu chạy và khóa cache của P7; `pose_raw.npz` không phụ thuộc người được chọn.
2. Ghép frame-to-frame bằng Hungarian trên chi phí kết hợp `1 − IoU(bbox)` và khoảng cách keypoint trung bình (chuẩn hóa theo chiều cao bbox).
   - Tham khảo `sort_people_sports2d` (Pose2Sim, BSD-3; giữ thông báo bản quyền nếu chép).
   - Cài đặt (P3.05, `track/associate.py`, giá trị tạm đã đo): chi phí = `(w_iou × (1 − IoU) + w_kp × min(1, khoảng cách keypoint trung bình / chiều cao hull)) / (w_iou + w_kp)` thuộc [0, 1], `w_iou = w_kp = 1`; hull là bao hộp của các keypoint hợp lệ
     (khi hai bên có ≥ 4 keypoint chung thì hull tính trên các keypoint chung), không dùng bbox detector đã lưu vì nó đổi theo nhịp detector; ít hơn 4 keypoint chung thì chỉ dùng số hạng IoU. Gán Hungarian toàn cục từng frame, cặp có chi phí > `max_cost = 0,3`
     không bao giờ được ghép. Track không được ghép sống thêm `max_gap_s = 0,1` s theo `t_sec` thật rồi đóng. Mọi người đủ điều kiện (đủ `min_valid_keypoints`) đều có track; người yếu có `track_id = −1`. `match_margin` đo độ tranh chấp của phép ghép: gần 0 chỗ hai người
     trùng nhau (không có đặc trưng hình dạng bề ngoài, hai thân hình giống hệt ở cùng chỗ không phân biệt được: giới hạn của phương pháp), ≥ 0,6 ở chỗ khác trên clip thật. Dự đoán chuyển động đã được đo và không được dùng (không giảm tráo ID, làm chi phí thật lớn hơn).
3. Mất dấu quá `max_lost` (đề xuất 0,5 s): đánh dấu `target_lost`, không tự nhảy sang người khác. Khi thấy lại, chỉ nối nếu chi phí dưới ngưỡng; nếu không thì báo người dùng chọn lại.
   Cài đặt (P3.06, `track/state.py`, giá trị tạm đã đo): mỗi frame của `pose_raw` có đúng một dòng với trạng thái `tracked` (có keypoint của người tập), `lost` (vắng ≤ `max_lost_s = 0,5` s theo `t_sec` thật, dự kiến quay lại),
   `target_lost` (vắng lâu hơn) hoặc `before_target` (trước frame đầu của track người tập). Keypoint và score của dòng không phải `tracked` là NaN: không điền, không nội suy (P4 nội suy gap ≤ 150 ms theo thời gian).
   Track của P3.05 đóng sau 0,1 s nên người quay lại sau một lúc vắng là một track **mới**; chỉ track **bắt đầu sau frame cuối của người tập, trong lúc người tập vắng** mới là ứng viên (người luôn có mặt, như người đi ngang qua người tập, không bao giờ là ứng viên).
   Chi phí của P3.05 (`person_cost`) giữa pose đầu của ứng viên và **pose cuối** của người tập: ≤ `reattach_cost = 0,5` thì nối (`reattached`); hai ứng viên cùng dưới ngưỡng và chi phí gần nhau (tốt nhất / thứ hai ≥ 0,6, hoặc cả hai bằng 0) thì `ambiguous`;
   trên ngưỡng hoặc vắng quá `max_reattach_s = 5` s thì `refused`. Không nối thì không đoán: giữ NaN và đặt `needs_reselect` kèm `reselect_reason` (`reattach_ambiguous`, `reattach_refused`, `target_lost_at_end`, `default_choice_ambiguous`, lý do đầu tiên trong
   danh sách này mà thỏa) để UI (P8) hỏi người dùng chọn lại. Người được chọn là người yếu (`track_id = −1`) thì báo lỗi `TargetStateError`.
   Số đo (Docs/tasks/P3.06.md mục 4): quay lại cùng chỗ trên SYN-12 (lệch ≤ 100 px) chi phí ≤ 0,44; trên clip thật D20 (bỏ các dòng của người dẫn 0,3 đến 7 s) ≤ 0,5 ở 83 đến 100 % vị trí; người lạ trong clip ≥ 0,65 (clip 660 s: 0,737 và 0,738, so với
   0,035 của chính người dẫn khi quay lại). Chưa có clip thật mà người tập thật sự rời khung (P1.09): ngưỡng là tạm, đo lại ở các take thật đầu tiên. Giới hạn: người lạ đứng đúng chỗ người tập vừa đứng có chi phí như người quay lại (không có đặc trưng bề ngoài,
   cùng giới hạn như P3.05); chỉ bắt được khi hai người cùng xuất hiện một lúc (`ambiguous`).
4. Ghi `track.parquet` (P3.06, `track/track_io.py`, schema `track/1`): mỗi frame của `pose_raw` một dòng: `frame_index`, `t_sec`, `in_segment` (frame nằm trong segment, không phải phần đệm 1 s), `status` (chuỗi), `track_id`, `person_row` (−1 khi không `tracked`),
   `keypoints` (list cố định 52 float32 x0, y0, x1, y1, …, px ảnh đã xoay thẳng, y xuống), `scores` (26 float32), `match_cost`, `match_margin`, `reattach_cost` (chi phí đã cho phép nối, chỉ ở frame nối). Metadata JSON `taiji_track_meta` trong schema Parquet:
   phiên bản, `recording_id`, lựa chọn người tập, tham số (cả của P3.05), số đếm từng trạng thái, `needs_reselect` và `reselect_reason`, các sự kiện (`lost`, `target_lost`, `recovered`, `reattached`, `refused`, `ambiguous` kèm frame, thời gian, chi phí). Không có đường dẫn hay tên file.
   Ghi nguyên tử, thư mục phải có sẵn; `save_track` trả SHA-256 cho manifest của run (P7); đọc nghiêm ngặt (cột, kiểu, null, tên trạng thái, số đếm và sự kiện phải khớp các dòng; phiên bản qua bảng reader).

### W6 — Quality mask, nội suy, lọc

Lưu **ba lớp riêng**: `raw` (từ W5), `mask` và `filtered`.

| Quy tắc | Giá trị đề xuất | Ghi chú |
|---|---|---|
| Keypoint score < τ_kp | τ_kp = 0,3 (chốt ở P01) | Đặt NaN, ghi lý do `low_conf` |
| Frame có < 50% khớp thiết yếu hợp lệ | Khớp thiết yếu: vai, hông, gối, mắt cá, gót | Cả frame `frame_invalid` |
| Nội suy gap ngắn | ≤ 150 ms, tuyến tính | Cờ `interpolated`. Không nội suy qua điểm đổi hướng nghi ngờ |
| Gap dài | > 150 ms | Giữ NaN. **Không** ffill, không điền 0 |
| Outlier | Hampel, cửa sổ 7, 3σ (MAD) | Cờ `outlier`, đặt NaN trước khi lọc. Mặc định thêm sàn σ ≥ 2 px (P4.03, DEC-0046) |
| Lọc | Butterworth bậc 4, 6 Hz, `filtfilt`, chạy riêng từng đoạn liên tục hợp lệ | Ablation 4/6/8 Hz cho metric nhịp |
| Tráo trái/phải | Phát hiện bước nhảy đồng thời của cặp L/R | Cờ `lr_swap_suspect`. MVP không tự sửa, chỉ cảnh báo |

**Cài đặt mask (P4.01, `quality/mask.py`; giá trị là của bảng trên, chưa kiểm bằng clip của ta):** `apply_mask(keypoints, scores, tracked, params)` trả lớp mask **mới** (không sửa lớp raw): mỗi ô khớp là giá trị đầu vào hoặc NaN, và mỗi NaN có một lý do (`reason`, uint8): `low_conf` (score hữu hạn dưới τ_kp; score **bằng** τ_kp được giữ, so sánh theo độ chính xác của score), `non_finite` (toạ độ hay score không hữu hạn), `not_tracked` (frame không phải frame của người tập: `lost`, `target_lost` hay `before_target`, cái nào thì ở `status`), `frame_invalid` (khớp còn dùng được nhưng frame thiếu khớp thiết yếu). Một khớp lấy lý do **đầu tiên** theo thứ tự `not_tracked`, `non_finite`, `low_conf`, `frame_invalid`, nên khớp đã bị loại ở frame không hợp lệ giữ lý do riêng của nó. "Dùng được" là đúng `valid_keypoint_mask` của tầng pose (tracker và P3.08 dùng cùng luật). Frame **tracked** có **ít hơn một nửa** khớp thiết yếu dùng được (5 trên 10 vẫn hợp lệ, 4 trên 10 thì không) là `frame_invalid`: cả 26 khớp là NaN. `mask_track(track)` giữ nguyên các frame đệm 1 s (`in_segment`) cho P4.03 và P4.05. Tham số (`MaskParams`) nằm trong kết quả để manifest và `quality.json` ghi lại. Chưa có định dạng file `pose_masked.npz`: một quyết định chung cho ba lớp sau P4.07 (DEC-0040).

**Số đo trên clip thật (M-QLT-01; 4 video D20, track của người tập theo luật của P3.08, τ_kp = 0,3):** trong 157 366 frame của các đoạn, 86 303 là `tracked` (54,8 %); phần còn lại là `before_target` (20 đến 37 % tuỳ video) và `target_lost` (17 đến 19 %) vì video web có cắt cảnh và người tập rời khung: đó là việc của tracker, không phải của mask. Trong các frame `tracked` mask chỉ loại 0,00 đến 0,18 % ô khớp (nhiều nhất là ngón chân và cổ tay) và **không frame nào là `frame_invalid`** (ít nhất 5 trên 10 khớp thiết yếu dùng được, chỉ 4 frame ở đúng 5). Trên video web này score của người tập gần như luôn từ 0,3 trở lên, nên mask theo score ở 0,3 gần như không loại gì; việc score có cảnh báo được các lỗi thật hay không là câu hỏi của P3.08, không phải của task này.

**Kết quả P3.08 (`Docs/reports/p3_failure_cases.md`; 250 frame, nhãn do agent gán và người xác nhận):** trong 34 lỗi pose ở frame bình thường có nêu khớp, **không lỗi nào** bị mask ở τ_kp = 0,3 loại: ở mọi lỗi có ít nhất một khớp sai có score từ 0,3 trở lên (điểm cao nhất của khớp sai có trung vị 0,67). Mask là cần (loại những gì không quan sát được) nhưng không phải bộ lọc chất lượng; cờ tráo trái/phải (P4.06) và kiểm tra theo nhãn phải làm việc đó. Giá trị τ_kp và danh sách khớp thiết yếu giữ nguyên; đổi là quyết định của maintainer.

**Cài đặt nội suy gap (P4.02, `quality/gaps.py`; giá trị là của bảng trên, đã đo trên clip D20, chưa kiểm bằng clip của ta):** `interpolate_gaps(keypoints, reason, t_sec, params, blocked)` đọc lớp mask (không sửa) và trả lớp mới. Một *gap* là đoạn frame liên tiếp mà một khớp không quan sát được (`reason != ok`). Độ dài gap là **khoảng giữa hai điểm neo** `t[sau] − t[trước]` (từ frame cuối còn quan sát được trước gap đến frame đầu quan sát được sau gap), tính bằng giây thật và nối nếu ≤ 0,150 s (+1e-9 s): ở 30 fps tối đa 3 frame thiếu, ở 24 và 25 fps tối đa 2, ở 60 fps tối đa 8; đúng 150 ms vẫn nối. Nối tuyến tính theo thời gian thật, x và y riêng, mỗi ô nối có cờ `interpolated`; không giữ giá trị cũ, không điền 0, không ngoại suy. Không nối (theo thứ tự này, kết cục ghi ở bảng gap) khi: thiếu điểm neo ở một hay cả hai đầu (`open_start`, `open_end`, `open_both`), gap có ô thuộc `never_fill` (mặc định `not_tracked`: frame không phải của người tập), gap hay một điểm neo nằm trong mặt nạ `blocked` tùy chọn, hoặc gap quá dài (`too_long`). `low_conf`, `non_finite` và `frame_invalid` được nối nếu ngắn. Câu "không nội suy qua điểm đổi hướng nghi ngờ" ở bảng trên được thực hiện bằng đầu vào `blocked`: bộ phát hiện là của P4.06, P4.07 nối hai bên, vì phát hiện ở đây cần một ngưỡng tốc độ chưa ai đo (DEC-0045). `reason` của mask giữ nguyên ở mọi ô, kể cả ô đã nối (P4.07 cần nó để báo coverage theo lý do); ô nối không có score. Một đoạn nối chỉ đúng khi hai điểm neo đúng: cờ `interpolated` nói "không quan sát được", không nói "đúng".

**Số đo trên clip thật (M-QLT-02; 4 video D20, N = 1, τ_kp = 0,3, 86 303 frame tracked, 24 fps ở ba video và 30 fps ở một video):** trong các frame tracked, mask để 1 787 trên 2 243 878 ô không quan sát được (0,080 %). Lớp gap nối 219 gap (phần lớn 1 hoặc 2 frame: 304 ô, 17 % số ô thiếu) và từ chối 82 gap quá dài (đa số trên 8 frame; 12 gap 3 frame ở 24 fps có khoảng 167 ms; 5 gap 4 frame ở 30 fps), nên còn 0,066 % ô là NaN; mọi lần mất người tập bị từ chối (`never_fill`). "Ẩn rồi nối lại" (ô đã quan sát bị ẩn ở đoạn theo dõi tốt, nối bằng hàm thật, so với giá trị đã quan sát): với g = 1 / 2 / 3 / 4 / 8 frame thiếu, sai số p95 là 5,9 / 6,4 / 6,8 / 7,1 / 9,4 px (2,6 / 2,9 / 3,1 / 3,3 / 4,4 % độ dài thân; thân ≈ 197 px), trung vị 1,4 đến 2,0 px; giữ giá trị cuối thay cho nối cho p95 từ 4,4 đến 15,6 %. Tay là nhóm khó nhất (p95 4,2 đến 4,8 % khi g ≤ 3), đầu, thân và chân 2,0 đến 2,6 %, bàn chân 2,9 đến 3,7 %. Giới hạn 150 ms giữ nguyên. Giới hạn của phép đo: ô bị ẩn nằm ở đoạn theo dõi tốt còn gap thật xảy ra khi model gặp khó (che khuất, chuyển động nhanh), nên sai số thật có thể lớn hơn; giá trị tham chiếu là giá trị quan sát, có nhiễu và có lỗi riêng; chỉ có clip bài giảng 24 đến 30 fps và động tác chậm.

**Cài đặt Hampel (P4.03, `quality/filters.py`; cửa sổ 7 và 3σ là của bảng trên, sàn 2 px chọn bằng số đo M-QLT-03, DEC-0046):** `hampel_outliers(keypoints, reason, t_sec, params)` đọc lớp mask (không sửa) và trả lớp mới. Với mỗi ô đã quan sát, cửa sổ là **7 frame** quanh nó; một frame trong cửa sổ chỉ được tính nếu ô của nó quan sát được và cách frame giữa không quá 0,25 s (+1e-9 s) theo thời gian thật, nên chỗ đứng hình hay mất người tập cắt cửa sổ và không giả định fps. Ô được *xét* nếu có ít nhất 5 ô được tính (kể cả chính nó); ô không được xét không bao giờ bị cờ (frame đầu và cuối có cửa sổ ngắn). σ = max(1,4826 × MAD, `scale_floor_px`); ô là outlier nếu |giá trị − trung vị| > 3σ (chặt: bằng thì giữ) ở x **hoặc** y, hai toạ độ xét riêng, một lượt trên giá trị gốc của cửa sổ. Outlier thành NaN với lý do mới `outlier` (mã 5 trong `mask.py`; `apply_mask` không bao giờ tạo mã này) và không có gì khác bị đổi: không làm mượt, không cắt, không bịa giá trị. Một spike dài đến 3 frame trong cửa sổ 7 vẫn tìm được nếu đủ lớn so với độ lệch của các frame tốt; lỗi kéo dài (khớp sai nhiều frame, tráo trái/phải) **không** là outlier vì mọi mẫu trong cửa sổ đều thấy nó (đó là việc của P4.06). Thứ tự các bước: mask → Hampel → gap → resample → lọc: lỗ do outlier để lại được P4.02 nối nếu ngắn (`outlier` không thuộc `never_fill`), có cờ `interpolated` và giữ lý do `outlier`, và Hampel không bao giờ thấy giá trị đã nối (P4.07 nối các bước). `hampel_track(masked)` chạy trên `MaskedTrack` và giữ nguyên các frame đệm. `torso_length_px(keypoints, reason)` đo độ dài thân (trung vị khoảng cách giữa trung điểm hai vai và trung điểm hai hông trên các frame đủ 4 khớp, NaN nếu không frame nào đủ) để quy sàn px cho camera hay độ phân giải khác; cách P4.07 truyền sàn theo đơn vị thân do P4.07 quyết định.

**Số đo trên clip thật (M-QLT-03; 4 video D20, N = 1, τ_kp = 0,3, 22 đoạn; 170 frame người đã xác nhận đúng với 4 394 ô quan sát, 118 ô được gọi tên là sai trong 34 lỗi pose ở frame bình thường của P3.08; thân ≈ 197 px):** luật đúng như bảng (3σ, không sàn) gắn cờ **7,06 %** số ô được xét (158 083 ô) và 6,87 % số ô của 170 frame đúng, vì MAD của 7 số là một ước lượng nhiễu (mô phỏng nhiễu Gauss thuần: 4,8 % số toạ độ; bỏ hệ số 1,4826 thì 10,8 %) và một khớp đứng yên vài frame có MAD gần 0 nên mọi dao động đều bị tính; nó thay 7 % ô tốt bằng ô nối. Với **sàn 2 px** (≈ 1 % thân): **0,49 %** (11 074 ô), 1,14 % trong frame đúng, độ nhạy trên khớp bị gọi tên sai 34,8 % (luật gốc 39,8 %; trong ±2 frame 44,9 % và 52,5 %), số ô NaN thêm sau Hampel và nối gap +313 (luật gốc +5 780; không Hampel: 1 483). Các mức khác: 3,5σ 5,67 %; 4σ 4,68 %; sàn 1 px 1,61 %; sàn 3 px 0,25 %. Theo loại lỗi (sàn 2 px): `lr_swap` 26 trên 58 ô, `joint_off` 13 trên 37, `foot_error` 1 trên 13, `flicker` 1 trên 10 — Hampel là lưới an toàn rẻ, **không** là bộ phát hiện các lỗi mà P3.08 tìm thấy. Giới hạn: độ nhạy dựa trên 118 ô ở frame được chọn vì luật xếp là đáng ngờ; frame "đúng" do người nhìn cả khung xương nên một số trong 50 ô bị cờ có thể là bước nhảy thật; chỉ có clip bài giảng 24 đến 30 fps. Sàn là tham số về tính hợp lệ của dữ liệu (cái gì tính là nhiễu của model), không phải ngưỡng cho một động tác (AGENTS.md mục 5.5).

**Tính timestamp không đều:** lọc Butterworth cần lấy mẫu đều. Nếu là video VFR, resample tuyến tính về lưới đều (ví dụ 30 Hz) để lọc, rồi giữ cả lưới gốc. Ghi `resampled = true` vào manifest.

**Output `quality.json`:** coverage theo khớp, theo segment và theo lý do loại. Đây là mẫu số 2 trong mục 8.3 của v3.

### W7 — Metric

Ba metric MVP, công thức chi tiết ở Phụ lục B. Nguyên tắc chung:
- Tính trên tọa độ **pixel ảnh**, đã sửa roll camera nếu có. Không dùng mét, không dùng góc sàn tự ước lượng.
- Mỗi metric có `metric_version`, `units`, `valid_intervals`, `coverage`, `missing_reason`.
- Chỉ tính trên interval mà `view_category` phù hợp với metric đó:
  - Độ nghiêng thân trước/sau: góc ngang.
  - Nghiêng trái/phải: góc chính diện.
- Không có ngưỡng chung. Ngưỡng hoặc mức thay đổi có ý nghĩa đọc từ `metric_record` do HLV ký duyệt (v3 mục 8.2). Chưa có record thì chỉ hiển thị giá trị, không kết luận.

### W8 — So sánh với mẫu

- Chỉ chạy khi hai đoạn cùng `action`, `side`, `variant`, cùng `view_category`, và coverage của cả hai ≥ ngưỡng.
- Chuẩn hóa: căn theo mid-hip, chia cho scale = **median** độ dài thân của từng đoạn. Không chuẩn hóa từng frame.
- Đặc trưng: tọa độ chuẩn hóa của các khớp được chọn, cộng `sin/cos` của góc đoạn chi.
- DTW có ràng buộc (Sakoe-Chiba band, step pattern có giới hạn độ dốc), chi phí có mask (Phụ lục C).
- Output:
  - Đường căn (warping path).
  - Khoảng cách hình dạng đã chuẩn hóa.
  - Đường cong lệch từng khớp theo timeline của mẫu.
  - **Tỷ lệ tốc độ cục bộ** lấy từ độ dốc đường căn so với thời gian thật.
- Nhịp **luôn** báo trên trục thời gian gốc. DTW chỉ dùng để so hình dạng.
- So sánh với độ biến thiên giữa các lần quay mẫu của chính HLV: dùng từ 2 take reference trở lên để có "dải bình thường".

### W9 — Review và report

- Tab **Số đo**:
  - Biểu đồ profile theo thời gian, đồng bộ với video.
  - Overlay skeleton render sẵn bằng FFmpeg (filter vẽ) hoặc Plotly.
  - Đánh dấu vùng NaN và vùng không đủ điều kiện.
- Tab **Báo cáo**: danh sách nhận xét.
  - Mỗi nhận xét có `criterion_version`, `evidence_interval`, `metric_ids` và trạng thái `ai_suggested` / `coach_confirmed` / `coach_rejected` / `insufficient_evidence`.
  - Nhận xét tạo từ template (không LLM). HLV sửa, thêm hoặc xác nhận.
- Export:
  - `report.json` (đầy đủ ID và version).
  - `metrics.csv`.
  - `report.html` (Jinja2 + Plotly offline).
  - Clip bằng chứng cắt bằng `ffmpeg -ss <t0−1s> -to <t1+1s> -c:v libx264` (re-encode để cắt chính xác).
- Report là **snapshot bất biến**. Review mới thì tạo revision report mới.

---

## 4. Hợp đồng dữ liệu và lưu trữ

### 4.1 Cấu trúc thư mục

```
data/
├── app.sqlite3
├── recordings/<recording_uuid>/
│   ├── source.mp4            # bản gốc, read-only
│   ├── recording.json
│   ├── pts.parquet
│   ├── proxy.mp4
│   ├── proxy.json            # kết quả kiểm tra timestamp của proxy (proxy/1, P2.01)
│   └── audio.wav
├── takes/<take_id>/sync.json
├── runs/<run_id>/            # run_id = hash(cache key, mục 4.3)
│   ├── run_manifest.json
│   ├── run.log               # log chạy của riêng run này (P0.06), ghi nối nếu chạy lại
│   ├── pose_raw.npz
│   ├── track.parquet
│   ├── pose_masked.npz
│   ├── pose_filtered.npz
│   ├── quality.json
│   ├── metrics.parquet
│   └── metric_summary.json
├── comparisons/<comparison_id>/{alignment.npz, comparison.json}
├── reports/<report_id>/{report.json, metrics.csv, report.html, clips/}
└── models/
    ├── registry.json
    └── *.onnx
```

### 4.2 Manifest mẫu

`recording.json` (schema `recording/1`, `schemas/recording.py`, chốt ở P2.01). Giá trị chưa biết là `null`, không bao giờ là 0
(một frame thì không có khoảng thời gian giữa các frame); không có tên file gốc và không có đường dẫn: file nguồn luôn là
`recordings/<recording_id>/source<source_ext>` tính từ thư mục dữ liệu. Số thực không được là NaN hay vô cực.

```json
{
  "schema_version": "recording/1",
  "recording_id": "3f2b8c1e-5d4a-4e7b-9c1a-0b2d3e4f5a6b",
  "sha256": "…",
  "participant_id": "P03", "session_id": "S01", "take_id": "S01-P03-T02", "camera_id": "camA",
  "consent_ref": "CONSENT-2026-011",
  "source_ext": ".mp4", "size_bytes": 812345678, "container": "mov,mp4,m4a,3gp,3g2,mj2", "codec": "h264",
  "width": 1920, "height": 1080, "display_rotation": 0,
  "time_base": "1/90000", "start_pts": 0, "n_frames": 11172,
  "pts_span_s": 372.4, "duration_s": 372.43,
  "nominal_fps": 30.0, "r_frame_rate": 30.0, "measured_fps": 30.0, "median_dt_s": 0.0333333, "dt_rel_std": 0.0,
  "n_duplicate_pts": 0, "vfr": false,
  "vfr_rule": {"name": "tick_median", "version": 1, "rel_tol": 0.01, "tick_tol": 1, "max_share": 0.01},
  "audio": {"codec": "aac", "sample_rate": 48000, "channels": 2, "start_offset_s": 0.0},
  "capture": {"camera_role": "main_axis", "height_m": 1.1, "distance_m": 4.5, "fps_setting": 30.0},
  "ingested_at": "2026-11-20T09:12:00+07:00",
  "tools": {"ffprobe": "9.0.1", "pyav": "19.0.2", "taiji_ai": "0.1.0"}
}
```

`proxy.json` (schema `proxy/1`): `recording_id`, `source_sha256`, `proxy_sha256`, `height`, `rotation_applied`, `ffmpeg`,
`args` (có placeholder, không có đường dẫn thật), `n_frames_source`, `n_frames_proxy` và `check` (`points`, `max_abs_dt_s`,
`max_abs_dt_frames`, `passed`). `passed = true` chỉ khi số frame bằng nhau và sai lệch lớn nhất ≤ 1 frame (P2.03).

`sync.json` (schema `sync/1`, `schemas/sync.py`), một file cho mỗi take và cặp camera. **Quy ước thời gian** (chốt ở P2.01,
DEC-0026; bản W2 trước đó không nói `t0` là gì): mọi thời gian là giây trên trục thời gian **video** của từng camera (giây
kể từ PTS đầu tiên, như `io/frames.py`). Camera A (`cam_a`, xếp trước theo tên) là mốc. Với một khoảnh khắc camera A thấy ở `t_a`:

```text
t_b = t_a + offset_s + drift × (t_a − t_ref_s)
t_a = (t_b − offset_s + drift × t_ref_s) / (1 + drift)
```

`t_ref_s` là thời điểm, trên trục video của camera A, của tiếng vỗ tay đã khớp ở đầu take (BUG-0059; trước đó là tâm cửa sổ); `drift` không có đơn vị (1e-4 = 100 ppm); `offset_s > 0` nghĩa là B
thấy cùng khoảnh khắc đó muộn hơn trên trục của B. Giá trị chưa biết là `null`: `status = ok` chỉ khi khớp tiếng vỗ tay ở cả đầu và
cuối; `start_only` thì chưa biết `drift`; `not_found` (kèm `not_found_reason` là `no_audio` hoặc `clap_not_found`) thì chưa biết
cả `offset_s`. Chỉ `ok` mới có phép ánh xạ (`a_to_b`, `b_to_a`; còn lại báo `SyncUnavailable`), để không ngầm coi drift là 0.
`usable_for_metrics = true` chỉ khi `status = ok`, có kiểm chứng bằng flash ở **cả hai đầu** và sai lệch lớn nhất ≤ 1 frame (P2.06).

```json
{
  "schema_version": "sync/1", "take_id": "S01-P03-T02", "cam_a": "camA", "cam_b": "camB",
  "recording_id_a": "…", "recording_id_b": "…", "method": "audio_xcorr/1",
  "params": {"sample_rate_hz": 16000, "window_s": 30.0, "max_lag_s": 15.0},
  "start": {"window_a_s": [0.0, 30.0], "lag_s": 0.737, "peak": 0.93, "peak_ratio": 3.1, "found": true},
  "end": {"window_a_s": [340.0, 370.0], "lag_s": 0.7371, "peak": 0.91, "peak_ratio": 2.8, "found": true},
  "status": "ok", "not_found_reason": null, "offset_s": 0.737, "drift": 3.0e-6, "t_ref_s": 15.0,
  "validation": {"method": "flash", "flash_a_s": [3.2, 4.2], "flash_b_s": [3.9373, 4.9373],
                 "residual_start_ms": 12.0, "residual_end_ms": 9.0, "residual_ms": 12.0,
                 "residual_frames": 0.36, "frame_dt_s": 0.0333333},
  "usable_for_metrics": true, "usable_reason": "usable",
  "created_at": "2026-11-20T09:20:00+07:00",
  "tools": {"ffprobe": "9.0.1", "pyav": "19.0.2", "taiji_ai": "0.1.0"}
}
```

`run_manifest.json`:
```json
{
  "schema_version": "run/1",
  "run_id": "…",
  "recording_id": "…",
  "segment_id": "…", "segment_revision": 3,
  "code_version": "git:abc1234",
  "models": {
    "det": {"name": "yolox_m_humanart", "sha256": "…"},
    "pose": {"name": "rtmpose_m_body7_halpe26", "sha256": "…"}
  },
  "provider": "CUDAExecutionProvider",
  "skeleton": "halpe26/1",
  "config_hash": "…",
  "stages": {"pose": "done", "track": "done", "quality": "done", "metrics": "failed"},
  "warnings": ["lr_swap_suspect@12.40-12.73"],
  "runtime": {"pose_rtf": 0.8, "peak_vram_mb": 2100}
}
```

### 4.3 Cache key và chạy lại

`run_id = sha256(video_sha256 ‖ segment_revision ‖ det_sha ‖ pose_sha ‖ config_hash ‖ skeleton_version ‖ code_version_major)`

- Thay bất kỳ thành phần nào thì tạo run mới. Run cũ giữ nguyên để report cũ còn truy vết được.
- Chạy lại theo stage: nếu `pose_raw.npz` hợp lệ (checksum trong manifest) thì bỏ qua W4.
- Review của HLV lưu trong SQLite, **không** nằm trong thư mục run. Vì vậy chạy lại không làm mất review.

### 4.4 Ghi atomic

Mọi file ghi vào `<name>.tmp` cùng thư mục → `fsync` → `os.replace()`. Manifest ghi cuối cùng. Thiếu manifest nghĩa là stage chưa hoàn tất.

### 4.5 Bảng SQLite chính

| Bảng | Khóa | Trường chính |
|---|---|---|
| `participant` | `participant_id` | pseudonym, level_self, level_coach, consent_ref, consent_scope (analysis/train/share), retention_until |
| `recording` | `recording_id` | take_id, camera_id, sha256, path, fps, vfr, rotation |
| `sync` | `take_id, cam_a, cam_b` | offset, drift, residual_ms, method, validated_by |
| `segment` | `segment_id, revision` | recording_id, start_pts, end_pts, action, side, occurrence, view_category, flags, reference_of, created_by, created_at |
| `run` | `run_id` | segment_id, revision, manifest_path, status |
| `metric_record` | `metric_name, version` | intended_use, supported_views, human_variability, smallest_useful_change, measurement_error, min_valid_duration, threshold, signed_by, signed_at |
| `finding` | `finding_id, revision` | run_id, criterion_version, t0, t1, metric_ids, status, coach_note, decided_by |
| `report` | `report_id` | run_ids, finding_revisions, snapshot_path, created_at |
| `audit_log` | autoincrement | actor, action, entity, before, after, at |

Migration viết bằng file SQL đánh số (`migrations/0001_init.sql` …), áp khi khởi động.

---

## 5. Kiến trúc code

### 5.1 Cấu trúc package

```
taiji_ai/
├── pyproject.toml / uv.lock
├── src/taiji_ai/
│   ├── config.py            # Pydantic settings, đọc TOML
│   ├── logs.py              # logging thống nhất, per-run file log, lọc đường dẫn tuyệt đối (P0.06)
│   ├── schemas/             # recording, segment, run, metric, finding (Pydantic)
│   ├── io/
│   │   ├── probe.py         # ffprobe → RecordingMeta
│   │   ├── frames.py        # PyAV: iter_frames(path, t0, t1) → (t_sec, frame)
│   │   ├── proxy.py         # FFmpeg proxy + kiểm tra PTS
│   │   └── audio_sync.py    # offset/drift/residual
│   ├── pose/
│   │   ├── registry.py      # đọc models/registry.json, kiểm SHA
│   │   ├── rtm.py           # wrapper rtmlib BodyWithFeet, model local
│   │   └── skeleton.py      # HALPE_26: tên, chỉ số, cặp L/R, cây chi
│   ├── track/target.py      # chọn người tập ở frame đầu (P3.04)
│   ├── track/associate.py   # gán id track bằng Hungarian giữa các frame (P3.05)
│   ├── track/geometry.py    # hull keypoint, IoU, bbox dùng được (dùng chung)
│   ├── track/state.py       # người mục tiêu theo thời gian: tracked/lost/target_lost, nối lại có ngưỡng (P3.06)
│   ├── track/track_io.py    # ghi/đọc `track.parquet` (track/1), nguyên tử và nghiêm ngặt (P3.06)
│   │                        # schemas/track.py: `TrackMeta` (metadata của `track.parquet`)
│   ├── quality/
│   │   ├── mask.py          # NaN theo score, frame_invalid, lý do
│   │   ├── gaps.py          # nội suy gap ngắn có cờ
│   │   ├── filters.py       # Hampel, Butterworth theo đoạn liên tục
│   │   └── coverage.py
│   ├── metrics/
│   │   ├── hip_height.py
│   │   ├── trunk_lean.py
│   │   └── tempo.py
│   ├── compare/
│   │   ├── features.py
│   │   └── dtw.py           # constrained, masked DTW (+ Numba tùy chọn)
│   ├── pipeline/
│   │   ├── stages.py        # mỗi stage: input manifest → output manifest
│   │   └── worker.py        # chạy job từ CLI: python -m taiji_ai.pipeline.worker <job.json>
│   ├── store/
│   │   ├── db.py            # sqlite3 + migrations
│   │   └── artifacts.py     # đường dẫn, ghi atomic, checksum
│   ├── report/
│   │   ├── findings.py      # template nhận xét
│   │   ├── render.py        # Jinja2 + Plotly
│   │   └── clips.py         # FFmpeg cắt clip bằng chứng
│   └── api/
│       ├── app.py           # FastAPI app factory, phục vụ /api và web/dist
│       ├── __main__.py      # python -m taiji_ai.api (uvicorn, 127.0.0.1)
│       └── routers/         # health, recordings, media, segments, runs, findings, reports
├── web/                     # React + Vite + TypeScript (pnpm)
│   ├── src/{pages,components,api,lib}/
│   ├── src/components/VideoPlayer/   # requestVideoFrameCallback, ±1 frame
│   ├── tests/               # Vitest; e2e/ cho Playwright
│   └── dist/                # build, FastAPI phục vụ (không commit)
├── migrations/
├── tests/{unit, contract, golden, fixtures}
└── tools/                   # script dataset UMONS/PSU, audit keypoint, agreement
```

### 5.2 Mô hình tiến trình

- **Web UI (React)** chạy trong trình duyệt, chỉ nói chuyện với **FastAPI** qua `/api/*`.
- **FastAPI** đọc/ghi SQLite, đọc artifact, phục vụ video proxy và tạo `job.json`. Không chạy pose/metric trong process API.
- Việc nặng (pose, metric) chạy bằng **subprocess worker** riêng (`python -m taiji_ai.pipeline.worker job.json`). Tiến độ ghi vào `run_manifest.json`; API trả tiến độ qua polling (1–2 s) hoặc SSE.
- Mỗi lần chỉ một job GPU (khóa bằng file lock), để tránh treo API và rò VRAM.
- Khi dùng: một lệnh chạy FastAPI (phục vụ cả `web/dist`). Khi phát triển: `pnpm dev` (Vite) proxy `/api` sang FastAPI.

### 5.3 Giao diện hàm chính

```python
# io/frames.py
def iter_frames(path: Path, t0: float, t1: float) -> Iterator[tuple[float, np.ndarray]]: ...

# pose/rtm.py
class PoseEstimator:
    def __init__(self, det_onnx: Path, pose_onnx: Path, device: str = "cuda"): ...
    def __call__(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """→ bboxes (N,4), keypoints (N,26,2) px, scores (N,26)"""

# quality
def apply_mask(kp: np.ndarray, sc: np.ndarray, tau: float) -> tuple[np.ndarray, np.ndarray]: ...
def filter_runs(x: np.ndarray, t: np.ndarray, cutoff_hz: float, order: int = 4) -> np.ndarray: ...

# metrics
def hip_height_profile(kp: np.ndarray, t: np.ndarray, variant: Literal["A","B"]) -> MetricSeries: ...
def trunk_lean(kp: np.ndarray, t: np.ndarray, roll_deg: float) -> MetricSeries: ...
def speed_pause(kp: np.ndarray, t: np.ndarray, group: JointGroup, tau: float, d_min: float) -> MetricSeries: ...

# compare/dtw.py
def masked_dtw(fa, ma, fb, mb, band: float, min_visible: int) -> Alignment: ...
```

Mọi mảng keypoint có shape `(T, 26, 2)`, kèm `t_sec (T,)` và `mask (T, 26)`. NaN nghĩa là không quan sát được.

---

## 6. Môi trường, model và tái lập

### 6.1 Môi trường

| Môi trường | Nội dung | Khi nào |
|---|---|---|
| `env-app` | Python, PyAV, NumPy/SciPy, Pydantic, FastAPI, uvicorn, Plotly, Jinja2, rtmlib, onnxruntime-gpu | MVP |
| `web` | Node.js ≥ 24, pnpm, React, Vite, TypeScript, Vitest, Playwright (`taiji_ai/web/pnpm-lock.yaml`) | MVP |
| `env-annot` | CVAT (Docker) | Audit keypoint ở P02 |
| `env-mmaction` | torch 2.1 + CUDA 12.1, mmcv 2.1.0, mmengine < 1.0, mmaction2 1.2.0 | Chỉ khi vào E01 |

- Khóa bằng `uv.lock`. Ghi `nvidia-smi`, phiên bản driver, CUDA và cuDNN vào `hardware_inventory.md` (P00.05).
- Chọn `onnxruntime-gpu` theo bảng tương thích CUDA/cuDNN của bản đó. Chạy `ort.get_available_providers()` trong smoke test.
- FFmpeg: ghi `ffmpeg -version` vào inventory, dùng cùng một bản cho cả nhóm.

### 6.2 Model registry

```json
{
  "schema_version": "model-registry/1",
  "models": [
    {
      "name": "rtmpose_m_body7_halpe26",
      "file": "rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.onnx",
      "sha256": "…",
      "source_url": "…",
      "downloaded_at": "…",
      "license_note": "weights: training data body7, xem mục 10.3",
      "input_size": [192, 256],
      "skeleton": "halpe26/1"
    }
  ]
}
```

Khi khởi động, `pose/registry.py` kiểm SHA-256 và **từ chối chạy** nếu không khớp. Không tắt kiểm tra SSL ở bất kỳ đâu.

### 6.3 Tái lập

- Mỗi report chứa `run_id`. Từ `run_id` lần ngược được video hash, segment revision, model SHA, config và commit code.
- Seed cố định cho mọi phần có ngẫu nhiên (bootstrap CI, chia tập).
- Test golden: một video fixture ngắn và giá trị metric kỳ vọng với tolerance. Đổi model hay code mà metric lệch thì CI báo.

---

## 7. Workflow dữ liệu và gán nhãn

### 7.1 Nguồn dữ liệu và vai trò

| Nguồn | Trạng thái | Dùng cho |
|---|---|---|
| D08 tự quay (Taiji24-Local) | Nguồn chính | Mọi thứ: metric, reference, pilot |
| UMONS-TAICHI (Kinect, đã tải) | `datasets/taiji/umons/` | Phát triển parser, mask, lọc, DTW, phân đoạn trên skeleton 25 khớp; test thuật toán trước khi có D08 |
| TaiForm deduction criteria (đã tải) | `datasets/taiji/taiform/` | Mẫu cấu trúc rubric có ngưỡng đo được |
| OpenWushu | `repos/taolu/OpenWushu/` | Lược đồ ontology, gợi ý điểm mấu chốt (HLV duyệt) |
| PSU-TMM100 | Chờ xin | Kiểm chứng metric 2D với mocap: chiếu 3D Vicon lên camera đã hiệu chuẩn |
| TaiChi-AQA, TaiChi-24 | Chờ xin | Giai đoạn E01/E03 |

### 7.2 Quy trình gán nhãn

1. **Ontology v0:** file `ontology_v0.yaml` gồm action, side, occurrence, view_category và cờ. HLV duyệt ở P00.
2. **Chia đoạn:** HLV làm trong app (W3). 20 đoạn đầu do 2 HLV chia độc lập để đo chênh lệch ranh giới.
3. **Chấm theo rubric:** form trong tab Báo cáo hoặc bảng tính có schema cố định. Mỗi HLV chấm độc lập, ẩn kết quả của người kia và của hệ thống.
4. **Audit keypoint:**
   - Chọn 200 frame phân tầng theo view × occlusion × động tác. Trong đó 50 frame do 2 người gán.
   - Dùng CVAT với skeleton template HALPE_26 (hoặc tập con khớp thiết yếu), export COCO keypoints.
5. **Adjudication:** lưu nhãn gốc, nhãn sau thống nhất và lý do. Không ghi đè.
6. **Chia tập:**
   - Holdout theo `participant_id`. Mọi camera và session của một người nằm cùng nhóm.
   - Phát triển dùng leave-one-person-out. Khóa `split_manifest.csv` kèm hash.

### 7.3 Công cụ phân tích độ thống nhất

| Loại nhãn | Chỉ số | Công cụ |
|---|---|---|
| Ranh giới thời gian | Chênh lệch tuyệt đối (s), trung vị và P90 | NumPy |
| Nhãn loại | Cohen's kappa (2 người) | `sklearn.metrics.cohen_kappa_score` |
| Nhãn thứ bậc | Weighted kappa | `cohen_kappa_score(weights="quadratic")` |
| Điểm liên tục | ICC(2,1) / ICC(3,1), Bland–Altman | Tự viết theo công thức, hoặc `pingouin` cho phân tích offline (GPL-3.0, không đưa vào sản phẩm) |
| Keypoint | Sai lệch giữa người gán theo khớp (px, chuẩn hóa theo thân) | NumPy |

---

## 8. Workflow đánh giá và nghiệm thu

### 8.1 Benchmark từng tầng

| Tầng | Cách đo | Dữ liệu |
|---|---|---|
| Timestamp | Sai lệch proxy ↔ nguồn ≤ 1 frame trên các mốc mẫu | Fixture + video thật |
| Đồng bộ | Residual audio ↔ flash (ms, frame) | Mỗi take |
| Pose | PCK@0,1 (chuẩn hóa theo thân) so với audit; lỗi theo khớp × view | 200 frame audit |
| Metric hình học | So với đo tay trên frame (Kinovea hoặc tool nội bộ); nếu có PSU thì so với mocap chiếu 2D | 20–30 đoạn |
| Độ lặp lại | Cùng người, cùng động tác, nhiều take: biến thiên trong người so với giữa người | D08 |
| So sánh mẫu | Spearman giữa khoảng cách DTW và xếp hạng HLV; leave-one-person-out | D08 |
| Workflow | Thời gian review, số nhận xét hữu ích, lỗi phải sửa (pilot P05) | 12–20 đoạn holdout |

### 8.2 Metric record (bắt buộc trước khi bật một metric)

Mỗi metric cần một record được HLV và A ký, gồm:
- Mục đích dùng và view được hỗ trợ.
- Sai số đo so với gold.
- Biến thiên giữa người với người (human variability).
- **Smallest useful change** do HLV đặt.
- Thời lượng hợp lệ tối thiểu và ngưỡng (nếu có).

Nếu sai số đo ≥ smallest useful change thì metric giữ ở trạng thái `experimental`.

### 8.3 Coverage

Báo ba tỷ lệ cho từng metric × camera (theo v3 mục 8.3): tỷ lệ thời gian đủ điều kiện view, tỷ lệ frame pose đạt trong đoạn đủ điều kiện, và tỷ lệ thời gian thực sự có metric, kèm lý do loại.

---

## 9. Quy trình phát triển

- **Git:**
  - `main` luôn chạy được. Mỗi việc một nhánh `feat/…` / `fix/…`, PR có mô tả và bằng chứng chạy.
  - Không commit video, dữ liệu người tham gia hay model vào git. Thêm `data/` và `models/*.onnx` vào `.gitignore`.
- **Kiểm thử bắt buộc theo module:**

| Module | Test |
|---|---|
| `io` | VFR, rotate, file hỏng, không audio; PTS proxy ↔ nguồn |
| `pose` | SHA sai → từ chối; provider fallback; shape output |
| `quality` | NaN giữ nguyên; gap ngắn có cờ; gap dài không bị điền; lọc từng đoạn không lan qua NaN |
| `metrics` | Golden test với skeleton tổng hợp: biết trước biên độ dao động hông, góc nghiêng, pause |
| `compare` | Hai chuỗi giống nhau → khoảng cách 0; chuỗi bị kéo giãn thời gian → hình dạng giống, tỷ lệ tốc độ đúng; khác action → từ chối |
| `store` | Ghi atomic; chạy lại không mất review; migration từ DB rỗng |
| `report` | Mọi nhận xét có `metric_ids` và `evidence_interval`; nhận xét chưa duyệt không vào bản cuối |

- **Chất lượng code:** `ruff` (lint + format), `mypy` cho `schemas/` và `metrics/`. Docstring ghi đơn vị và quy ước tọa độ.
- **Definition of Done:**
  - Có artifact chạy thật trên video thật.
  - Manifest đủ version.
  - Test pass.
  - Tài liệu điều kiện áp dụng được cập nhật.
  - HLV duyệt mọi nội dung chuyên môn.

---

## 10. Bảo mật, quyền dữ liệu và license

### 10.1 Dữ liệu cá nhân

- Chạy local trên máy có kiểm soát truy cập. Không gửi video ra dịch vụ ngoài.
- ID giả danh. Bảng ánh xạ tên thật ↔ ID để riêng, mã hóa hoặc ngoài máy phân tích.
- `consent_scope` tách riêng phân tích, huấn luyện và chia sẻ. Pipeline kiểm `consent_scope` trước khi đưa recording vào tập train.
- Xóa theo yêu cầu: xóa recording, proxy, audio, mọi run, clip và report liên quan. Ghi `audit_log`.
- Logging thống nhất: log qua thư viện chuẩn, chỉ log ID (run_id, recording_id, pseudonym), không bao giờ log tên file người dùng, đường dẫn nguồn hay văn bản tự do; mọi đường dẫn tuyệt đối dạng Windows (ổ đĩa, UNC, `\\?\`, cả dạng `repr`) bị lọc thành `<path>`, trừ tail tương đối dưới root an toàn (`<data>\…`); đường dẫn không có dấu nháy bị lọc tới hết dòng. Không phát hiện được: tên file tương đối, văn bản tự do, đường dẫn URL-encode — vì vậy quy tắc chỉ log ID là bắt buộc (P0.06, sửa 2026-11-15 theo BUG-0014/0015).
- Đối chiếu Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP, cùng thủ tục với người chưa thành niên (v3 mục 9.2).

### 10.2 An toàn kỹ thuật

- Không tắt SSL. Không tải model hay code lúc chạy.
- Video do người dùng tải lên chỉ xử lý bằng FFmpeg/PyAV trong worker, có giới hạn thời lượng và dung lượng.
- Không chạy code từ repo nghiên cứu ngoài (`repos/`). Chỉ đọc để tham khảo.

### 10.3 Ma trận license của stack

| Thành phần | License | Rủi ro |
|---|---|---|
| rtmlib | Apache-2.0 | Thấp |
| RTMPose / YOLOX weights (body7, HumanArt) | Không ghi rõ cho weights; dữ liệu train gồm bộ chỉ cho nghiên cứu | **Cần audit trước khi thương mại**. MVP nội bộ/nghiên cứu chấp nhận được |
| onnxruntime | MIT | Thấp |
| FFmpeg | LGPL/GPL tùy build | Gọi CLI riêng; kiểm tra build nếu phân phối kèm |
| PyAV | BSD-3 (link FFmpeg) | Thấp |
| FastAPI, uvicorn, NumPy, SciPy, Pydantic, Plotly, Jinja2 | MIT/BSD | Thấp |
| React, Vite, TypeScript, TanStack Query, React Router | MIT/Apache-2.0 | Thấp; dependency npm gián tiếp audit qua `pnpm licenses list` trước khi phân phối |
| Pose2Sim (nếu chép đoạn tracking) | BSD-3 (kiểm tra lại khi chép) | Giữ thông báo bản quyền |
| QAQA (nếu tham khảo thuật toán) | Apache-2.0 | Ghi nguồn |
| OpenWushu content | CC BY-SA 4.0 | Nội dung phái sinh phải cùng license |
| UMONS-TAICHI | CC BY-NC-SA 4.0 | Không thương mại |
| pingouin | GPL-3.0 | Chỉ phân tích offline |

---

## 11. Công nghệ cho các phase mở rộng

| Phase | Công nghệ | Điều kiện / lưu ý |
|---|---|---|
| E01 Nhận diện thức | mmaction2 1.2.0: STGCN++ 2D (`layout` dạng dict cho HALPE_26, `num_person=1`), PoseC3D đối chứng; sliding window + lớp nền; chuyển nhãn qua DTW với bài mẫu (open-begin) làm baseline | Môi trường `env-mmaction` riêng. Chia tập theo người. Báo cả kết quả có và không có prior thứ tự bài |
| E02 Platform | (FastAPI đã có từ MVP) PostgreSQL, hàng đợi (RQ/Celery hoặc Postgres-based), object storage (MinIO/S3), auth theo tổ chức | Khi có nhiều người dùng hoặc nhiều job đồng thời |
| E03 Learned AQA | scikit-learn (Ridge/GBM) trên keyframe × metric sau căn DTW; SHAP để giải thích; calibration | Nhãn đủ và đạt độ thống nhất. Chia theo người. Không lấy trọng số ensemble từ dự đoán test |
| E04 Luật/trọng tài | Ruleset registry có nguồn và trang, test xung đột luật; điểm xuất phát: bảng mã lỗi IWUF 2024 dạng JSON trong `repos/taolu/tpz` (MPL-2.0) | Chuyên gia xác nhận edition luật; đối chiếu JSON với bản luật IWUF chính thức trước khi dùng làm `criterion_id` |
| E05 3D | OpenCV calibration (checkerboard) + triangulation 2 camera; cân nhắc Pose2Sim cho triangulation; GVHMR/SMPL chỉ cho nghiên cứu | License SMPL phi thương mại. Cần ground truth (PSU-TMM100) |
| E06 Theo dõi dài hạn | Lưu metric theo version; trend chỉ trên cùng camera, model và rubric | Không nối chuỗi metric qua các lần đổi model |

---

## 12. Quyết định còn mở

| # | Quyết định | Chốt ở | Phương án mặc định |
|---|---|---|---|
| 1 | Python 3.11 hay 3.12 | **Đã chốt 13/11/2026** | **3.12**, vì PyAV 19 yêu cầu ≥ 3.12 |
| 2 | Phiên bản onnxruntime-gpu theo CUDA/cuDNN máy | **Đã chốt 13/11/2026** | **onnxruntime-gpu 1.32.0 `[cuda,cudnn]`**: CUDA 13 runtime + cuDNN 9 cài qua pip, `ort.preload_dlls()`. Driver 596.49 hỗ trợ CUDA 13.2. Không cần CUDA/cuDNN hệ thống. Xem `Docs/hardware_inventory.md` |
| 3 | τ_kp, ngưỡng gap ngắn, tần số cắt Butterworth | P01 | 0,3 · 150 ms · 6 Hz, ablation trên đoạn mẫu |
| 4 | Biến thể metric độ cao hông (A: scale cố định take; B: so với mắt cá thấp nhất / median thân) | P03.07 | Tính cả hai, chọn theo sai số so với đo tay |
| 5 | Component đánh dấu thời gian: tự viết hay import từ Kinovea/ELAN | P01.05 | Tự viết, có phương án import dự phòng |
| 6 | Công cụ audit keypoint: CVAT hay tool nội bộ | P02 | CVAT nếu cài được trong 0,5 ngày |
| 7 | Có quét checkerboard ngay đợt quay đầu | P00.03 | Có, nếu thêm dưới 5 phút mỗi buổi |

---

## Phụ lục A — Skeleton HALPE_26

| Idx | Khớp | Idx | Khớp | Idx | Khớp |
|---:|---|---:|---|---:|---|
| 0 | Nose | 9 | LWrist | 18 | Neck |
| 1 | LEye | 10 | RWrist | 19 | Hip (giữa) |
| 2 | REye | 11 | LHip | 20 | LBigToe |
| 3 | LEar | 12 | RHip | 21 | RBigToe |
| 4 | REar | 13 | LKnee | 22 | LSmallToe |
| 5 | LShoulder | 14 | RKnee | 23 | RSmallToe |
| 6 | RShoulder | 15 | LAnkle | 24 | LHeel |
| 7 | LElbow | 16 | RAnkle | 25 | RHeel |
| 8 | RElbow | 17 | Head | | |

- Cặp L/R: (1,2) (3,4) (5,6) (7,8) (9,10) (11,12) (13,14) (15,16) (20,21) (22,23) (24,25).
- Thứ tự này phải được kiểm chứng trên output thật ở P01 (task S01 của v3) và lưu thành `skeleton/halpe26/1`.
- Lưu ý: Sports2D/Pose2Sim xuất cột theo thứ tự cây chi, không theo chỉ số HALPE.

## Phụ lục B — Công thức metric

Quy ước: tọa độ pixel, trục y hướng xuống. `p_j(t)` là vị trí khớp j sau lọc. `t` là thời gian thật (giây).

- Mid-hip `H(t) = (p_11 + p_12)/2`. Mid-shoulder `S(t) = (p_5 + p_6)/2`.
- Độ dài thân `L(t) = ‖S(t) − H(t)‖`. Scale đoạn `Λ = median_t L(t)` trên frame hợp lệ.

**B1. Biến thiên độ cao hông**
- Biến thể A (v3): `h_A(t) = y_H(t) / Λ_take`, trong đó `Λ_take` lấy từ đoạn đứng tham chiếu của take.
- Biến thể B: `g(t) = max{y_j(t) : j ∈ {15,16,24,25} hợp lệ}` (điểm thấp nhất trên ảnh, xấp xỉ mặt sàn); `h_B(t) = (g(t) − y_H(t)) / Λ`.
- Kết quả: `range = P95(h) − P5(h)` trên interval hợp lệ, kèm profile, coverage và thời điểm đạt cực trị.
- Điều kiện: camera cố định, đoạn HLV xác nhận là "kỳ vọng độ cao ổn định", không có thay đổi chiều sâu lớn (cờ `perspective_shift`).

**B2. Độ nghiêng thân trong mặt phẳng ảnh**
- `θ(t) = atan2(x_S − x_H, y_H − y_S) − roll_cam` (độ). 0° là thẳng đứng, dấu dương nghiêng về phía phải ảnh.
- `roll_cam` lấy từ một đường thẳng đứng do người dùng vẽ trên frame tham chiếu, mặc định 0.
- Kết quả: median, P95 của `|θ|`, và thời lượng `|θ| > ngưỡng` (chỉ khi có `metric_record`).
- Chỉ hợp lệ ở interval có view phù hợp: front cho nghiêng trái/phải, side cho nghiêng trước/sau.

**B3. Nhịp và độ liên tục**
- `v_j(t_k) = ‖p_j(t_{k+1}) − p_j(t_{k−1})‖ / (t_{k+1} − t_{k−1}) / Λ` (đơn vị: độ dài thân/giây).
- Tốc độ nhóm `V_G(t) = median_{j∈G, hợp lệ} v_j(t)`, với G là tay {9,10}, hông {11,12}, chân {15,16,24,25}.
- Pause: interval có `V_G < τ` kéo dài ≥ `d_min`. `τ` và `d_min` học từ nhãn HLV cho cùng loại động tác, không dùng giá trị chung.
- Kết quả: duration gốc của đoạn, profile `V_G`, số pause và độ dài pause, hệ số biến thiên của `V_G`.
- Bắt buộc: ablation tần số cắt bộ lọc (4/6/8 Hz) để đo độ nhạy của số pause.

## Phụ lục C — So sánh mẫu: masked constrained DTW

1. **Đặc trưng frame:**
   - `f(t) = [(p_j(t) − H(t))/Λ for j ∈ J] ⊕ [sin φ_s, cos φ_s for s ∈ segments]`.
   - J là các khớp thân và chi. Segments gồm cánh tay trên/dưới, đùi, cẳng chân, trục thân.
2. **Chi phí:**
   - `c(i,k) = mean_{j hợp lệ ở cả i và k} w_j · ‖f_j(i) − f_j(k)‖`.
   - Nếu số khớp hợp lệ chung < `min_visible` thì `c = +∞` (ô không dùng được). `w_j` do HLV và A chọn theo động tác.
3. **Ràng buộc:**
   - Sakoe-Chiba band `|i/n − k/m| ≤ r` (đề xuất r = 0,1–0,2).
   - Step pattern đối xứng có giới hạn độ dốc (ví dụ P = 1), không cho đi ngang hoặc dọc quá 2 bước liên tiếp.
   - Tùy chọn open-begin/open-end khi ranh giới đoạn không chắc chắn.
4. **Kết quả:**
   - `D = Σ c(path) / len(path)`.
   - Đường cong lệch từng khớp trên timeline mẫu.
   - Tỷ lệ tốc độ cục bộ `ρ(k) = d t_query / d t_ref` dọc path, làm mượt bằng cửa sổ 0,5 s.
5. **Hiệu chỉnh:**
   - "Dải bình thường" = phân bố `D` giữa các take reference của HLV.
   - Hiển thị `D` của người tập so với dải này. Không chuyển sang điểm 0–100.
6. **Cài đặt:** NumPy, tăng tốc bằng Numba nếu chuỗi dài hơn 2.000 frame. Đối chiếu với `dtaidistance` (Apache-2.0) trên dữ liệu không có mask để kiểm tra đúng.
