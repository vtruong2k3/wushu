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

Không lật gương ảnh. Người quay lưng vẫn giữ nhãn trái/phải do model trả về và được kiểm tra ở W6.

### W5 — Khóa người tập

1. Ở frame đầu segment (hoặc frame do người dùng chọn), hiển thị bbox các người phát hiện được. Người dùng chọn người tập. Mặc định chọn bbox lớn nhất gần tâm.
2. Ghép frame-to-frame bằng Hungarian trên chi phí kết hợp `1 − IoU(bbox)` và khoảng cách keypoint trung bình (chuẩn hóa theo chiều cao bbox).
   - Tham khảo `sort_people_sports2d` (Pose2Sim, BSD-3; giữ thông báo bản quyền nếu chép).
3. Mất dấu quá `max_lost` (đề xuất 0,5 s): đánh dấu `target_lost`, không tự nhảy sang người khác. Khi thấy lại, chỉ nối nếu chi phí dưới ngưỡng; nếu không thì báo người dùng chọn lại.
4. Ghi `track.parquet` (`t_sec`, `frame_index`, keypoint, score, `match_cost`, `status`).

### W6 — Quality mask, nội suy, lọc

Lưu **ba lớp riêng**: `raw` (từ W5), `mask` và `filtered`.

| Quy tắc | Giá trị đề xuất | Ghi chú |
|---|---|---|
| Keypoint score < τ_kp | τ_kp = 0,3 (chốt ở P01) | Đặt NaN, ghi lý do `low_conf` |
| Frame có < 50% khớp thiết yếu hợp lệ | Khớp thiết yếu: vai, hông, gối, mắt cá, gót | Cả frame `frame_invalid` |
| Nội suy gap ngắn | ≤ 150 ms, tuyến tính | Cờ `interpolated`. Không nội suy qua điểm đổi hướng nghi ngờ |
| Gap dài | > 150 ms | Giữ NaN. **Không** ffill, không điền 0 |
| Outlier | Hampel, cửa sổ 7, 3σ (MAD) | Cờ `outlier`, đặt NaN trước khi lọc |
| Lọc | Butterworth bậc 4, 6 Hz, `filtfilt`, chạy riêng từng đoạn liên tục hợp lệ | Ablation 4/6/8 Hz cho metric nhịp |
| Tráo trái/phải | Phát hiện bước nhảy đồng thời của cặp L/R | Cờ `lr_swap_suspect`. MVP không tự sửa, chỉ cảnh báo |

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
│   ├── track/target.py      # khóa người tập, Hungarian, trạng thái mất dấu
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
