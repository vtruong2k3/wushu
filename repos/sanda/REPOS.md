# Repo tham khảo cho phân tích Sanda

> **Ngoài phạm vi dự án.** Dự án làm Wushu Taolu (quyền), không phải Sanda. Repo dùng cho Taolu nằm ở `../taolu/`; mmaction2 đã được clone lại ở đó.

Clone ngày 13/11/2026, `--depth 1`. Chưa cài đặt hay chạy thử repo nào.

| Repo | URL | Commit | Ngày commit | License code | Phân loại |
|---|---|---|---|---|---|
| mmaction2 | https://github.com/open-mmlab/mmaction2 | `a5a167dff2399e2d182a60332325f9c0d4663517` | 2026-03-18 | Apache-2.0 | adopt: train nhận diện đòn |
| RTM-FASS | https://github.com/asaravanabavan/RTM-FASS | `3b8f39dbb27afe315061113998a4520ce4718f42` | 2026-01-28 | MIT | adapt: tham khảo pipeline + dữ liệu keypoint Muay Thai |
| fight-judge | https://github.com/hasanfaesal/fight-judge | `78f068ff9e7200169b6f4b7a94b76057782ebb7b` | 2026-03-02 | MIT (code), CC BY-NC-SA 4.0 (dataset) | adapt: detection/pose võ sĩ |

## Ghi chú từng repo

**mmaction2.** Có PoseC3D, ST-GCN/STGCN++ và VideoMAE trong model zoo. Checkpoint được tải theo link trong từng config, không nằm trong repo.

**RTM-FASS.** Đề tài tốt nghiệp về Muay Thai. Có code CNN-LSTM, pose YOLOv8, tracking 2 võ sĩ và engine chấm 10-point must.
- **Không có checkpoint.** `models/` chỉ có README, link Releases là placeholder `yourusername`, repo không có release nào. Muốn dùng phải tự train lại từ `Copy of MAIN.ipynb`.
- Có sẵn dữ liệu keypoint và nhãn padwork (`data/strike_dataset/`, `data/annotations/*.zip`). Video gốc không có.
- 8 lớp Muay Thai: jab, cross, hook, uppercut, roundhouse, teep, elbow, knee. Sanda cấm chỏ và gối, nhưng có quật ngã. Phải làm lại toàn bộ ontology và luật.
- Accuracy chỉ do tác giả tự báo (val khoảng 80–85%), không có test set độc lập.

**fight-judge.** Có 2 weights trên Hugging Face, MIT, chưa tải về:
- `hasanfaesal/fight-judge-yolov8s`: phát hiện võ sĩ, dữ liệu từ 20 trận UFC.
- `hasanfaesal/fight-judge-yolov11x-pose`: pose 17 điểm.

Lưu ý: nhãn pose được **tự sinh bằng YOLO11x-pose pretrained** rồi fine-tune lại trên chính nhãn đó. Vì vậy con số mAP 0.920 đo độ khớp với nhãn giả, chưa phải độ chính xác thật. Nhận diện đòn và chấm điểm vẫn ở trạng thái *Planned*. Dataset có điều khoản **NC (phi thương mại)**.

## Đánh giá code (13/11/2026, đọc tĩnh, chưa chạy)

### RTM-FASS: chỉ tái dùng từng mảnh

- **Model:** là MLP theo frame + BiLSTM + attention, không có CNN (`src/strike_model.py`). Khoảng 2,75M tham số, nên con số "~145MB" không hợp lý. Fighter embedding không được truyền vào lúc inference.
- **Accuracy:**
  - Padwork: val **40,84%** (output notebook), không phải 80–85% như README.
  - Combined: 94,18% trên tập chia ngẫu nhiên theo cửa sổ. Khoảng 60 cửa sổ gần trùng nhau cho mỗi đòn (170 đòn), có cả bản lật gương, augment cả tập val, không có tập test. Con số này bị rò rỉ nặng.
- **Phát hiện đòn:**
  - Không có lớp "không phải đòn", nên mọi cửa sổ có softmax > 0,6 đều bị tính là đòn. Thực tế bắn gần như liên tục.
  - Hit/miss chỉ nhìn tư thế người đánh, không nhìn đối thủ.
- **Chấm điểm:**
  - Trọng số do tác giả tự đặt. Điểm mỗi võ sĩ bị kẹp riêng trong khoảng 7–10, không phải 10-point must thật.
  - `'kick' in strike_type` không bao giờ khớp `roundhouse`/`teep`, nên đá bị tính như đấm (`src/fight_analyzer.py:117,195,221`).
  - Fatigue và dự đoán thắng là hằng số bịa.
- **Tracking:** ID của Ultralytics gán cho fighter 0/1 theo thứ tự xuất hiện. Không lọc trọng tài. Chế độ batch không tracking.
- **Notebook:** phụ thuộc Colab/Drive và có lỗi đường dẫn. `src/` không có entry point chạy end-to-end.
- **Dữ liệu:** `metadata.json` có 957 chuỗi keypoint (15×17×3). Thực chất chỉ khoảng 472 clip, vì còn lại là bản lật gương. Tất cả từ 7 video điện thoại quay trong một buổi. Lớp đòn trùng với video nguồn. Khoảng 516 chuỗi bị nhảy pose giữa người đánh và người cầm đích.
- **Đáng giữ:**
  - Wrapper YOLO + backoff OOM (`pose_detector.py:80-223`) và phần vẽ skeleton.
  - Vòng train và augment, sau khi sửa class weight và chia tập theo video.
  - `visualization.py`.
  - Schema track của CVAT.
  - Ý tưởng chia vùng đầu/thân/chân (`strike_detector.py:47-72`).

### fight-judge: dùng được cho detector, nhưng metric bị thổi phồng

- **Rò rỉ dữ liệu:** train/valid/test chia ngẫu nhiên theo **frame**. Cả 19 video nguồn đều có mặt ở cả 3 tập, frame liền kề rơi vào tập khác nhau (ví dụ `…-0000/0002/0003` ở train, `…-0001` ở valid). Vì vậy mAP 0,984 (detection) và 0,920 (pose) không đo khả năng tổng quát sang trận mới.
- **Nhãn pose:** do YOLO11x-pose tự sinh rồi fine-tune lại trên chính nhãn đó, nên mAP pose đo độ khớp với nhãn giả.
- **Lỗi phụ thuộc:** `pyproject.toml` khai báo `mmpose>=1.0`, nhưng `run-inference-batch.py` dùng API mmpose 0.x (`inference_top_down_pose_model`, `init_pose_model`, `DatasetInfo`). Cài theo khai báo thì script không chạy.
- **Annotation:** COCO JSON trong `annotations/` chỉ có bbox, không có keypoint.
- **Nhận diện đòn và chấm điểm:** chỉ có kế hoạch trong METHODOLOGY.md, không có code.

### mmaction2: dùng được, là nền chính để train

- **Phiên bản:** v1.2.0. Yêu cầu `mmcv>=2.0.0rc4,<2.2.0` và `mmengine<1.0`. Trên Windows nên dùng torch 2.1 + CUDA 12.1 để có wheel mmcv 2.1.0 dựng sẵn, tránh phải tự build.
- **STGCN++ 2D:** dùng `layout='coco'` (17 khớp, khớp YOLO-pose) và `num_person=2`, hợp với 2 võ sĩ Sanda. Graph còn hỗ trợ `nturgb+d` (25 khớp Kinect V2, dùng được cho UMONS) và layout tùy biến dạng dict (HALPE_26).
- **Format dữ liệu:** file pkl, mỗi mẫu gồm `frame_dir`, `total_frames`, `img_shape`, `label`, `keypoint [M×T×V×C]`, `keypoint_score`. Có thể tự xuất từ YOLO/RTMPose, không bắt buộc dùng `ntu_pose_extraction.py`. Script đó cần mmdet + mmpose và Faster R-CNN/HRNet.
- **Giới hạn:**
  - Chỉ là clip classification. Muốn phát hiện đòn trên trận liên tục phải tự làm sliding window, cộng lớp nền/không đòn.
  - Các config localization (BMN/BSN…) dành cho feature RGB.
  - Pretrained NTU/Kinetics có điều khoản dữ liệu riêng, cần kiểm tra khi thương mại hóa.

## Lưu ý license chung

- RTM-FASS, fight-judge và Boxing đều dựa trên **Ultralytics YOLO, license AGPL-3.0**. Nếu thương mại hóa hoặc chạy làm dịch vụ, cần license Ultralytics Enterprise hoặc thay bằng pose model khác (ví dụ RTMPose/MMPose, Apache-2.0).
- Dataset của fight-judge là CC BY-NC-SA, chỉ dùng cho nghiên cứu.

## Chưa clone

| Repo | Lý do |
|---|---|
| akhellad/combat-sport-analyser | **Không có file LICENSE**, nên không được phép tái sử dụng code. README có ý tưởng đáng đọc: gán ID theo màu áo, lọc trọng tài, xử lý cắt cảnh. Tác giả cũng xác nhận phát hiện từng đòn từ một camera 2D vẫn là bài toán mở. |
| ACM40960/Boxing | MIT, nhưng chỉ có quyền anh (đấm và đỡ, không có đá hay quật). Repo nặng khoảng 120 MB, phần lớn là file YOLO `.pt` có thể tải công khai, kèm file `.pyc` đã biên dịch. |
