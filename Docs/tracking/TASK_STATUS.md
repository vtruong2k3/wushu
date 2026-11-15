# Task Status

Live status of every task. Rules: `AGENTS.md` §2. Task definitions: `Docs/IMPLEMENTATION_PLAN_V1.md`.
Update this file whenever a task changes status. Statuses: `TODO`, `ANALYZING`, `PLAN_READY`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `BLOCKED`, `CANCELLED`.

**Last updated:** 2026-11-15

## Summary

| Phase                                                    |   Tasks |  DONE | In progress | BLOCKED |   TODO |
| -------------------------------------------------------- | ------: | ----: | ----------: | ------: | -----: |
| P0 Nền tảng code (còn lại)                               |       7 |     6 |           1 |       0 |      0 |
| P1 Discovery, ontology, protocol (v3 P00)                |      10 |     0 |           0 |       0 |     10 |
| P2 Ingest và đồng bộ camera (W1, W2)                     |       7 |     0 |           0 |       0 |      7 |
| P3 Pose và khóa người tập (W4, W5)                       |       9 |     0 |           0 |       0 |      9 |
| P4 Quality mask và lọc (W6)                              |       8 |     0 |           0 |       0 |      8 |
| P5 Ba metric (W7)                                        |      10 |     0 |           0 |       0 |     10 |
| P6 So sánh với mẫu (W8)                                  |       7 |     0 |           0 |       0 |      7 |
| P7 Pipeline, worker, run manifest                        |       5 |     0 |           0 |       0 |      5 |
| P8 Giao diện, review, báo cáo (W3, W9) — React + FastAPI |      16 |     2 |           0 |       0 |     14 |
| P9 Thu dữ liệu pilot và gán nhãn (v3 P02)                |       9 |     0 |           0 |       0 |      9 |
| P10 Kiểm chứng metric và so sánh (v3 P03 / G03)          |       7 |     0 |           0 |       0 |      7 |
| P11 Pilot giá trị và quyết định (v3 P05 / G05)           |       5 |     0 |           0 |       0 |      5 |
| **Total**                                                | **100** | **8** |       **1** |   **0** | **91** |

## Ad-hoc tasks (`X.NN`)

| ID   | Task                                                                       | Reason                                                           | Owner | Status | Plan                 | Updated    | Evidence / notes                                                                                                         |
| ---- | -------------------------------------------------------------------------- | ---------------------------------------------------------------- | ----- | ------ | -------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------ |
| X.01 | Repository working rules + tracking files                                  | Maintainer request 2026-11-13                                    | agent | DONE   | —                    | 2026-11-13 | `AGENTS.md`, `CLAUDE.md`, `Docs/tracking/*`; CHANGELOG 2026-11-13                                                        |
| X.06 | Record usable repos from X.05 in docs, commit and push                     | Maintainer request 2026-11-14                                    | agent | DONE   | `Docs/tasks/X.06.md` | 2026-11-14 | REPOS.md summary (E04 row), TECH_WORKFLOW §11 E04, THIRD_PARTY_NOTICES §6; pushed in ce859b4                             |
| X.05 | Survey additional Wushu / martial-arts repositories                        | Maintainer list 2026-11-14                                       | agent | DONE   | `Docs/tasks/X.05.md` | 2026-11-14 | 20 items reviewed; cloned tpz (MPL-2.0) + wushu_vision (reference); dataset D14 registered                               |
| X.04 | Switch UI stack Streamlit → React + Vite + FastAPI (decision + re-plan P8) | Maintainer chose React + Vite + FastAPI 2026-11-14               | agent | DONE   | `Docs/tasks/X.04.md` | 2026-11-14 | DEC-0008; TECH_WORKFLOW v1.1; P8 re-planned (16 tasks, 13.75 d; total ≈ 54 d); T-API/T-WEB/T-E2E tests; BUG-0002 closed  |
| X.03 | Rules for third-party code, models and datasets                            | Maintainer approved 2026-11-13; AGENTS.md only had 3 short rules | agent | DONE   | `Docs/tasks/X.03.md` | 2026-11-14 | AGENTS.md §9, `taiji_ai/THIRD_PARTY_NOTICES.md`, registry allowed-use column, `dataset` marker; BUG-0001 fixed; DEC-0007 |
| X.02 | Move git repository root to workspace (`wushu/`)                           | Maintainer approved 2026-11-13; docs/rules were outside git      | agent | DONE   | `Docs/tasks/X.02.md` | 2026-11-13 | 52 files staged in dry run (≈ 484 KB), no forbidden files, no personal data; 12 tests pass; DEC-0006                     |

## P0 — Nền tảng code (còn lại)

| ID    | Task                                                                                                            | Owner | Est. (d)   | Depends on | Status | Plan                  | Updated    | Evidence / notes                                                                                                |
| ----- | --------------------------------------------------------------------------------------------------------------- | ----- | ---------- | ---------- | ------ | --------------------- | ---------- | --------------------------------------------------------------------------------------------------------------- |
| P0.01 | Dựng cấu trúc package, `pyproject.toml`, `uv.lock`                                                              | A     | —          | —          | DONE   | —                     | 2026-11-13 | Recorded retroactively; see CHANGELOG 2026-11-13                                                                |
| P0.02 | Tải và đăng ký model, GPU smoke test                                                                            | A     | —          | —          | DONE   | —                     | 2026-11-13 | Recorded retroactively; see CHANGELOG 2026-11-13                                                                |
| P0.03 | `io/probe`, `io/frames`, `store/*`, migration 0001                                                              | A     | —          | —          | DONE   | —                     | 2026-11-13 | Recorded retroactively; see CHANGELOG 2026-11-13                                                                |
| P0.04 | Commit đầu tiên; quy ước nhánh và PR; file `CONTRIBUTING.md` ngắn                                               | B     | 0,25       | —          | DONE   | `Docs/tasks/P0.04.md` | 2026-11-14 | Initial commit 8fae211 pushed to origin/main (github.com/vtruong2k3/wushu); CONTRIBUTING.md, .gitattributes     |
| P0.05 | Script kiểm tra một lệnh `tools/check.ps1`: ruff check + format check + pytest (bỏ qua test `gpu` nếu `-NoGpu`) | B     | 0,25 → 0,5 | P0.04      | DONE | `Docs/tasks/P0.05.md` | 2026-11-15 | Reopened by the re-review (§9), closed after rework 2: BUG-0008/0009/0010 CLOSED, F-1..F-11 resolved (§9.4); gate 10/10 PASS (91 pytest, 11 Vitest), regression tests red-first, guard mutation-checked. Phase P0 acceptance still needs a run on machine B (maintainer). 2026-11-15: two P0.05 test files and history entries were overwritten after close; restored in the P0.06 rework (BUG-0012 / BUG-0013 CLOSED) |
| P0.06 | Logging thống nhất (`logging` + file log theo run), không log đường dẫn chứa tên thật                           | A     | 0,5 → 0,75 | —          | DONE   | `Docs/tasks/P0.06.md` | 2026-11-15 | Reopened by review, closed after rework: BUG-0011..BUG-0018 CLOSED; unified logging, 1-pass PathRedactor, per-run `run.log`, uvicorn integration, gate 10/10 PASS |
| P0.07 | Bộ sinh skeleton tổng hợp cho test (mục 14.3)                                                                   | A     | 1 → 1,5    | —          | PLAN_READY | `Docs/tasks/P0.07.md` | 2026-11-15 | Plan written 2026-11-15; awaiting maintainer confirmation (≥ 1 day: Q1–Q6, tolerance table §2.5) |

## P1 — Discovery, ontology, protocol (v3 P00)

| ID    | Task                                                                                                                    | Owner | Est. (d) | Depends on | Status | Plan | Updated | Evidence / notes |
| ----- | ----------------------------------------------------------------------------------------------------------------------- | ----- | -------- | ---------- | ------ | ---- | ------- | ---------------- |
| P1.01 | Soạn kịch bản phỏng vấn: hỏi câu mở trước, rồi mới cho xem 3 bản phác metric                                            | O     | 0,5      | —          | TODO   | —    |         |                  |
| P1.02 | Phỏng vấn 3–5 HLV, ghi workflow hiện tại và thời gian                                                                   | O+H   | (giờ H)  | P1.01      | TODO   | —    |         |                  |
| P1.03 | Tổng hợp nhu cầu: top 3 vấn đề, metric nào giữ hoặc thay                                                                | O     | 0,5      | P1.02      | TODO   | —    |         |                  |
| P1.04 | Ontology v0: bài 24 thức (variant HLV xác nhận), action, side, occurrence, view_category, cờ                            | A+H   | 1        | P1.02      | TODO   | —    |         |                  |
| P1.05 | Protocol quay 2 camera: vị trí theo trục bài, app khóa FPS, vỗ tay + flash đầu/cuối, đoạn đứng tham chiếu, checkerboard | A     | 0,5      | —          | TODO   | —    |         |                  |
| P1.06 | Mẫu consent: phân tích / huấn luyện / chia sẻ, thời hạn lưu, rút lại; quy trình cho người chưa thành niên               | O     | 0,5      | —          | TODO   | —    |         |                  |
| P1.07 | Định nghĩa sơ bộ 3 metric và điều kiện view (từ Phụ lục B của TECH_WORKFLOW), H góp ý                                   | A+H   | 0,5      | P1.03      | TODO   | —    |         |                  |
| P1.08 | Điền nhân sự thật, lịch HLV, đơn giá; khóa mục tiêu pilot (thời gian / chất lượng review)                               | O     | 0,5      | P1.03      | TODO   | —    |         |                  |
| P1.09 | Quay thử 1 take trọn bài bằng 2 camera theo protocol                                                                    | A+H   | 0,5      | P1.05      | TODO   | —    |         |                  |
| P1.10 | Gửi yêu cầu dữ liệu PSU-TMM100, TaiChi-AQA, TaiChi-24 (do O quyết định gửi)                                             | O     | 0,25     | —          | TODO   | —    |         |                  |

## P2 — Ingest và đồng bộ camera (W1, W2)

| ID    | Task                                                                                                   | Owner | Est. (d) | Depends on          | Status | Plan | Updated | Evidence / notes |
| ----- | ------------------------------------------------------------------------------------------------------ | ----- | -------- | ------------------- | ------ | ---- | ------- | ---------------- |
| P2.01 | Schema Pydantic `RecordingManifest`, `SyncManifest` (`schemas/`)                                       | B     | 0,5      | P0                  | TODO   | —    |         |                  |
| P2.02 | `ingest_recording(path, meta)`: copy read-only, SHA-256, probe, `pts.parquet`, cờ VFR, ghi DB          | B     | 1        | P2.01               | TODO   | —    |         |                  |
| P2.03 | Tạo proxy H.264 720p, giữ timestamp nguồn; kiểm tra sai lệch proxy ↔ nguồn ≤ 1 frame tại 10 điểm       | B     | 0,5      | P2.02               | TODO   | —    |         |                  |
| P2.04 | Tách audio mono 16 kHz; tìm offset bằng tương quan chéo envelope ở cửa sổ đầu và cuối take; tính drift | A     | 1        | P2.02               | TODO   | —    |         |                  |
| P2.05 | Kiểm chứng bằng mốc flash: dò frame có độ sáng nhảy vọt; tính residual (ms, frame)                     | A     | 0,5      | P2.04               | TODO   | —    |         |                  |
| P2.06 | Quy tắc dùng sync: residual ≤ 1 frame thì cho ghép metric, lớn hơn thì chỉ hiển thị song song          | A     | 0,25     | P2.05               | TODO   | —    |         |                  |
| P2.07 | Chạy ingest + sync trên 2 video thử của P1.09; ghi báo cáo ngắn                                        | A+B   | 0,25     | P2.03, P2.06, P1.09 | TODO   | —    |         |                  |

## P3 — Pose và khóa người tập (W4, W5)

| ID    | Task                                                                                                                                                         | Owner | Est. (d) | Depends on   | Status | Plan | Updated | Evidence / notes |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- | -------- | ------------ | ------ | ---- | ------- | ---------------- |
| P3.01 | Kiểm chứng thứ tự 26 khớp trên output thật: vẽ chỉ số lên 5 frame, đối chiếu tên                                                                             | A     | 0,25     | P0           | TODO   | —    |         |                  |
| P3.02 | `run_pose(segment)`: đọc frame theo PTS trong `[start−1s, end+1s]`, detector chạy mỗi N frame, giữa các lần đó lấy bbox từ keypoint frame trước (nới 10–15%) | A     | 1        | P3.01, P2.02 | TODO   | —    |         |                  |
| P3.03 | Lưu `pose_raw.npz`: mọi người phát hiện được (bbox, kp, score, t_sec, frame_index)                                                                           | A     | 0,5      | P3.02        | TODO   | —    |         |                  |
| P3.04 | Chọn người mục tiêu ở frame đầu: mặc định bbox lớn nhất gần tâm, cho phép chỉ định bbox                                                                      | A     | 0,5      | P3.03        | TODO   | —    |         |                  |
| P3.05 | Ghép frame-to-frame bằng Hungarian (`1−IoU` + khoảng cách keypoint chuẩn hóa)                                                                                | A     | 1        | P3.04        | TODO   | —    |         |                  |
| P3.06 | Trạng thái mất dấu: quá `max_lost` thì `target_lost`, không nhảy sang người khác; nối lại có ngưỡng                                                          | A     | 0,5      | P3.05        | TODO   | —    |         |                  |
| P3.07 | Benchmark trên 5 clip thật (P1.09): RTF, peak VRAM, N = 1/5/10, ảnh hưởng của N tới keypoint                                                                 | A     | 0,5      | P3.06        | TODO   | —    |         |                  |
| P3.08 | Rà lỗi pose trên clip thật: tay che thân, xoay thân, đứng một chân, quay lưng; ghi failure cases                                                             | A+H   | 0,5      | P3.07        | TODO   | —    |         |                  |
| P3.09 | So sánh nhanh detector YOLOX vs YOLO11 (chỉ đo, không đổi stack): recall, độ ổn định bbox, tốc độ                                                            | A     | 0,5      | P3.07        | TODO   | —    |         |                  |

## P4 — Quality mask và lọc (W6)

| ID    | Task                                                                                                           | Owner | Est. (d) | Depends on | Status | Plan | Updated | Evidence / notes |
| ----- | -------------------------------------------------------------------------------------------------------------- | ----- | -------- | ---------- | ------ | ---- | ------- | ---------------- |
| P4.01 | `apply_mask`: score < τ thì NaN, lý do `low_conf`; frame thiếu khớp thiết yếu thì `frame_invalid`              | A     | 0,5      | P3.06      | TODO   | —    |         |                  |
| P4.02 | Nội suy gap ngắn (≤ 150 ms theo thời gian thật, không theo số frame), cờ `interpolated`; gap dài giữ NaN       | A     | 0,5      | P4.01      | TODO   | —    |         |                  |
| P4.03 | Hampel (cửa sổ 7, 3·MAD), cờ `outlier`                                                                         | A     | 0,5      | P4.01      | TODO   | —    |         |                  |
| P4.04 | Resample lưới đều cho video VFR (để lọc), giữ ánh xạ về timestamp gốc                                          | A     | 0,5      | P4.02      | TODO   | —    |         |                  |
| P4.05 | Butterworth bậc 4 zero-phase, chạy riêng từng đoạn liên tục hợp lệ; đoạn ngắn hơn padlen thì không lọc, gắn cờ | A     | 0,5      | P4.04      | TODO   | —    |         |                  |
| P4.06 | Phát hiện nghi tráo trái/phải (cặp L/R nhảy chéo đồng thời), cờ `lr_swap_suspect`                              | A     | 0,5      | P4.01      | TODO   | —    |         |                  |
| P4.07 | Coverage theo khớp, theo segment và theo lý do loại; `quality.json`                                            | A     | 0,5      | P4.05      | TODO   | —    |         |                  |
| P4.08 | Kiểm thử trên UMONS Kinect (dữ liệu thật 30 Hz): mask, gap và lọc không vỡ trên chuỗi dài                      | A     | 0,5      | P4.07      | TODO   | —    |         |                  |

## P5 — Ba metric (W7)

| ID    | Task                                                                                                        | Owner | Est. (d) | Depends on   | Status | Plan | Updated | Evidence / notes |
| ----- | ----------------------------------------------------------------------------------------------------------- | ----- | -------- | ------------ | ------ | ---- | ------- | ---------------- |
| P5.01 | Kiểu dữ liệu `MetricSeries` / `MetricSummary` (version, units, valid_intervals, coverage, missing_reason)   | A     | 0,5      | P4           | TODO   | —    |         |                  |
| P5.02 | Hỗ trợ hình học: mid-hip, mid-shoulder, độ dài thân, scale Λ (median), sửa roll camera                      | A     | 0,5      | P5.01        | TODO   | —    |         |                  |
| P5.03 | Độ cao hông, biến thể A (scale cố định từ đoạn đứng tham chiếu)                                             | A     | 0,5      | P5.02        | TODO   | —    |         |                  |
| P5.04 | Độ cao hông, biến thể B (so với điểm thấp nhất mắt cá/gót, chia Λ)                                          | A     | 0,5      | P5.03        | TODO   | —    |         |                  |
| P5.05 | Độ nghiêng thân trong mặt phẳng ảnh; chỉ tính trong interval có view phù hợp                                | A     | 0,5      | P5.02        | TODO   | —    |         |                  |
| P5.06 | Tốc độ nhóm khớp theo thời gian thật (sai phân trung tâm), đơn vị thân/giây                                 | A     | 0,5      | P5.02        | TODO   | —    |         |                  |
| P5.07 | Pause: `V < τ` kéo dài ≥ `d_min`; τ và d_min nhận từ config (chưa có thì chỉ xuất profile)                  | A     | 0,5      | P5.06        | TODO   | —    |         |                  |
| P5.08 | Ablation tần số cắt 4/6/8 Hz cho số pause và biên độ hông                                                   | A     | 0,5      | P5.07        | TODO   | —    |         |                  |
| P5.09 | Bảng `metric_record` và hàm tải record; metric chưa có record thì trạng thái `experimental`, không kết luận | A     | 0,5      | P5.01        | TODO   | —    |         |                  |
| P5.10 | Chạy 3 metric trên đoạn thật của P1.09, H xem có hợp lý không (sơ bộ cho G01)                               | A+H   | 0,5      | P5.08, P3.08 | TODO   | —    |         |                  |

## P6 — So sánh với mẫu (W8)

| ID    | Task                                                                                                  | Owner | Est. (d) | Depends on   | Status | Plan | Updated | Evidence / notes |
| ----- | ----------------------------------------------------------------------------------------------------- | ----- | -------- | ------------ | ------ | ---- | ------- | ---------------- |
| P6.01 | Đặc trưng frame: tọa độ chuẩn hóa (mid-hip, Λ) + sin/cos góc đoạn chi; mask theo khớp                 | A     | 0,5      | P5.02        | TODO   | —    |         |                  |
| P6.02 | Ma trận chi phí có mask (`min_visible`, trọng số khớp)                                                | A     | 0,5      | P6.01        | TODO   | —    |         |                  |
| P6.03 | DTW có band Sakoe-Chiba và step pattern giới hạn độ dốc; trả path, khoảng cách chuẩn hóa              | A     | 1        | P6.02        | TODO   | —    |         |                  |
| P6.04 | Tốc độ cục bộ dọc path so với thời gian thật; đường cong lệch từng khớp trên timeline mẫu             | A     | 0,5      | P6.03        | TODO   | —    |         |                  |
| P6.05 | Quy tắc từ chối: khác action/side/view, coverage thấp                                                 | A     | 0,25     | P6.03        | TODO   | —    |         |                  |
| P6.06 | "Dải bình thường" từ nhiều take reference; báo vị trí của người tập so với dải này                    | A     | 0,5      | P6.04        | TODO   | —    |         |                  |
| P6.07 | Kiểm tra trên UMONS: cùng lớp gần hơn khác lớp; chuyển ranh giới đoạn qua warping path, so với `.lab` | A     | 0,75     | P6.03, P4.08 | TODO   | —    |         |                  |

## P7 — Pipeline, worker, run manifest

| ID    | Task                                                                                                | Owner | Est. (d) | Depends on   | Status | Plan | Updated | Evidence / notes |
| ----- | --------------------------------------------------------------------------------------------------- | ----- | -------- | ------------ | ------ | ---- | ------- | ---------------- |
| P7.01 | Schema `RunManifest`, cache key (TECH_WORKFLOW §4.3)                                                | B     | 0,5      | P0           | TODO   | —    |         |                  |
| P7.02 | Stage runner: mỗi stage nhận manifest vào, trả manifest ra; bỏ qua stage đã xong (checksum hợp lệ)  | B     | 1        | P7.01, P3–P6 | TODO   | —    |         |                  |
| P7.03 | Worker subprocess `python -m taiji_ai.pipeline.worker job.json`; file lock một job GPU; ghi tiến độ | B     | 0,5      | P7.02        | TODO   | —    |         |                  |
| P7.04 | Xử lý lỗi: stage fail thì `failed` + thông báo; chạy lại từ stage hỏng; hủy job an toàn             | B     | 0,5      | P7.03        | TODO   | —    |         |                  |
| P7.05 | Test tích hợp end-to-end trên fixture: ingest → pose → quality → metric → compare                   | A+B   | 0,5      | P7.04        | TODO   | —    |         |                  |

## P8 — Giao diện, review, báo cáo (W3, W9)

| ID     | Task                                                                                                                                                                              | Owner | Est. (d) | Depends on   | Status | Plan                  | Updated    | Evidence / notes                                                                                                      |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | -------- | ------------ | ------ | --------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------- |
| P8.01  | Khung FastAPI: app factory, settings, `/api/health`, định dạng lỗi, phục vụ `web/dist`, `python -m taiji_ai.api` (chỉ `127.0.0.1`); bỏ Streamlit                                  | B     | 0,5      | P0           | DONE   | `Docs/tasks/P8.01.md` | 2026-11-14 | FastAPI app, /api/health, errors, SPA serving; Streamlit removed; 13 API tests; BUG-0004 closed                       |
| P8.02  | Khung web: Vite + React + TS, React Router, TanStack Query, client API có kiểu, proxy `/api` khi dev, layout, trang trạng thái; ESLint + `tsc` + Vitest; `check.ps1` gọi thêm web | B     | 0,75     | P8.01        | DONE   | `Docs/tasks/P8.02.md` | 2026-11-14 | React + Vite + TS scaffold, status page; Vitest 11, build served by FastAPI, headless Edge render OK; BUG-0005 closed |
| P8.03  | API + trang participants/recordings: danh sách, nạp video (gọi `io.ingest`), hiển thị cảnh báo VFR/rotation/thiếu audio                                                           | B     | 1        | P8.02, P2.02 | TODO   | —                     |            |                                                                                                                       |
| P8.04  | Media API: phục vụ `proxy.mp4` với HTTP Range, bảng PTS dạng JSON; chặn path traversal                                                                                            | B     | 0,5      | P8.01, P2.03 | TODO   | —                     |            |                                                                                                                       |
| P8.05  | Video player: `requestVideoFrameCallback`, ±1 frame theo bảng PTS, đổi thời gian proxy ↔ PTS nguồn                                                                                | B     | 1,5      | P8.04        | TODO   | —                     |            |                                                                                                                       |
| P8.05b | Phương án dự phòng: import đoạn từ CSV Kinovea/ELAN                                                                                                                               | B     | 0,5      | P8.03        | TODO   | —                     |            |                                                                                                                       |
| P8.06  | Form đoạn + API: action/side/occurrence/view/cờ, chọn reference; mỗi lần sửa là một revision                                                                                      | B     | 1        | P8.05        | TODO   | —                     |            |                                                                                                                       |
| P8.07  | Runs API: tạo job, tiến độ (polling hoặc SSE), hủy; nối với worker; giao diện tiến độ và lỗi                                                                                      | B     | 1        | P7.03, P8.06 | TODO   | —                     |            |                                                                                                                       |
| P8.08  | Trang Số đo: biểu đồ time-series đồng bộ con trỏ video (chọn thư viện, ứng viên uPlot), vùng NaN và vùng không hợp lệ, coverage                                                   | B     | 1,5      | P8.07, P5    | TODO   | —                     |            |                                                                                                                       |
| P8.09  | Video overlay skeleton render sẵn bằng FFmpeg/OpenCV (proxy + skeleton)                                                                                                           | A     | 0,5      | P3           | TODO   | —                     |            |                                                                                                                       |
| P8.10  | Template nhận xét từ metric đủ điều kiện; H duyệt câu chữ                                                                                                                         | B+H   | 0,5      | P5.09        | TODO   | —                     |            |                                                                                                                       |
| P8.11  | Trang Báo cáo + API review: xác nhận / bác bỏ / sửa / `insufficient_evidence`, lưu revision và audit log                                                                          | B     | 1        | P8.10        | TODO   | —                     |            |                                                                                                                       |
| P8.12  | Export JSON/CSV/HTML (Jinja2 + Plotly offline) và clip bằng chứng; snapshot bất biến                                                                                              | B     | 1        | P8.11        | TODO   | —                     |            |                                                                                                                       |
| P8.13  | So sánh cạnh nhau: 2 video đồng bộ và đường cong lệch theo timeline mẫu                                                                                                           | B     | 1        | P6, P8.08    | TODO   | —                     |            |                                                                                                                       |
| P8.14  | Backup/restore DB và artifact; xóa dữ liệu một participant                                                                                                                        | B     | 0,5      | P8.12        | TODO   | —                     |            |                                                                                                                       |
| P8.15  | E2E Playwright cho luồng G04 (nạp → chọn đoạn → chạy → xem → xác nhận → xuất; mở lại)                                                                                             | B     | 1        | P8.03–P8.14  | TODO   | —                     |            |                                                                                                                       |

## P9 — Thu dữ liệu pilot và gán nhãn (v3 P02)

| ID    | Task                                                                                            | Owner         | Est. (d)          | Depends on   | Status | Plan | Updated | Evidence / notes |
| ----- | ----------------------------------------------------------------------------------------------- | ------------- | ----------------- | ------------ | ------ | ---- | ------- | ---------------- |
| P9.01 | Tuyển 6 người tập, lấy consent, gán ID giả danh                                                 | O             | (lịch)            | P1.06        | TODO   | —    |         |                  |
| P9.02 | 6 buổi nhóm: 36 performance, 72 file (2 camera) theo protocol                                   | A+O+H         | (lịch)            | P9.01        | TODO   | —    |         |                  |
| P9.03 | Ingest hàng loạt, kiểm tra hash, consent, sync                                                  | A             | 0,5               | P2, P9.02    | TODO   | —    |         |                  |
| P9.04 | HLV chia 120 đoạn (20 đoạn đầu do 2 HLV chia độc lập)                                           | H             | (giờ H)           | P8.04        | TODO   | —    |         |                  |
| P9.05 | Chọn 200 frame audit phân tầng (view × occlusion × động tác); xuất cho CVAT                     | A             | 0,5               | P9.03, P3    | TODO   | —    |         |                  |
| P9.06 | Cài CVAT (Docker) hoặc tool nội bộ; template HALPE_26; gán 200 frame, 50 frame gán đôi          | A + annotator | 1 + giờ annotator | P9.05        | TODO   | —    |         |                  |
| P9.07 | Hai HLV chấm độc lập theo rubric (ẩn kết quả hệ thống và người kia)                             | H             | (giờ H)           | P9.04        | TODO   | —    |         |                  |
| P9.08 | Script đo độ thống nhất: ranh giới, kappa, weighted kappa, ICC, Bland–Altman, sai lệch keypoint | A             | 1                 | P9.06, P9.07 | TODO   | —    |         |                  |
| P9.09 | Adjudication; chốt error budget; khóa holdout theo participant + `split_manifest.csv` (hash)    | A+H           | 0,5               | P9.08        | TODO   | —    |         |                  |

## P10 — Kiểm chứng metric và so sánh (v3 P03 / G03)

| ID     | Task                                                                                     | Owner | Est. (d) | Depends on  | Status | Plan | Updated | Evidence / notes |
| ------ | ---------------------------------------------------------------------------------------- | ----- | -------- | ----------- | ------ | ---- | ------- | ---------------- |
| P10.01 | Pose: PCK@0,1 so với audit, theo khớp × view; so với độ lệch giữa 2 annotator            | A     | 0,5      | P9.08       | TODO   | —    |         |                  |
| P10.02 | Metric vs đo tay trên 20–30 đoạn (hông A/B, nghiêng thân)                                | A     | 1        | P5, P9      | TODO   | —    |         |                  |
| P10.03 | Độ lặp lại: cùng người, nhiều take; trong người so với giữa người                        | A     | 0,5      | P10.02      | TODO   | —    |         |                  |
| P10.04 | Coverage 3 tỷ lệ cho từng metric × camera; trên các đoạn HLV cần sửa                     | A     | 0,5      | P4.07       | TODO   | —    |         |                  |
| P10.05 | So sánh mẫu: Spearman giữa khoảng cách DTW và xếp hạng HLV, leave-one-person-out         | A     | 0,5      | P6, P9.07   | TODO   | —    |         |                  |
| P10.06 | Chọn biến thể hông A/B; ký `metric_record` cho từng metric (bật hoặc giữ `experimental`) | A+H   | 0,5      | P10.02–05   | TODO   | —    |         |                  |
| P10.07 | (Nếu có PSU-TMM100) Chiếu 3D Vicon vào camera, so với metric 2D                          | A     | 1–2      | dữ liệu PSU | TODO   | —    |         |                  |

## P11 — Pilot giá trị và quyết định (v3 P05 / G05)

| ID     | Task                                                                                        | Owner | Est. (d) | Depends on | Status | Plan | Updated | Evidence / notes |
| ------ | ------------------------------------------------------------------------------------------- | ----- | -------- | ---------- | ------ | ---- | ------- | ---------------- |
| P11.01 | Thiết kế phiên pilot: cặp clip tương đương, đảo thứ tự công cụ, kịch bản cho HLV            | O+A   | 0,5      | G04, G03   | TODO   | —    |         |                  |
| P11.02 | Chạy pilot: 2 HLV × ≥ 6 đoạn; ghi thời gian, nhận xét hữu ích, lỗi phải sửa, độ tin cậy     | O+H   | (giờ H)  | P11.01     | TODO   | —    |         |                  |
| P11.03 | Đo lỗi kỹ thuật trong pilot: error, coverage, nhận xét sai theo người/view; thời gian xử lý | A+B   | 0,5      | P11.02     | TODO   | —    |         |                  |
| P11.04 | Sửa 3 vấn đề gây mất giá trị lớn nhất                                                       | A+B   | 1,5      | P11.03     | TODO   | —    |         |                  |
| P11.05 | Báo cáo quyết định: tiếp tục, sửa phạm vi hay dừng một metric; đề xuất extension E01–E07    | O     | 0,5      | P11.04     | TODO   | —    |         |                  |
