load D:\workspaces\wushu\taiji_ai\models\yolox_m_8xb8-300e_humanart-c2c7a14a.onnx with onnxruntime backend
load D:\workspaces\wushu\taiji_ai\models\rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.onnx with onnxruntime backend
# Environment inventory

## System

- OS: Windows-11-10.0.26200-SP0
- Python: 3.12.10 (D:\workspaces\wushu\taiji_ai\.venv\Scripts\python.exe)
- GPU: NVIDIA GeForce RTX 3060, 596.49, 12288 MiB
- FFmpeg: ffmpeg version 9.0.1-essentials_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers
- ffprobe: ffprobe version 9.0.1-essentials_build-www.gyan.dev Copyright (c) 2007-2026 the FFmpeg developers

## Python packages

- numpy: 2.5.4
- scipy: 1.18.1
- pandas: 3.1.1
- pyarrow: 26.0.1
- pydantic: 2.14.3
- av: 19.0.2
- cv2: 4.14.0
- onnxruntime: 1.32.0
- rtmlib: installed
- fastapi: 0.162.6
- uvicorn: 0.54.0
- plotly: 7.1.0
- jinja2: 3.1.6

- onnxruntime providers: ['TensorrtExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']

## Models

- det: yolox_m_humanart `yolox_m_8xb8-300e_humanart-c2c7a14a.onnx` sha256 `3dea6513388889f0` OK
- pose: rtmpose_m_body7_halpe26 `rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.onnx` sha256 `26f3a19e61304a60` OK

## GPU smoke test (1080p frame, synthetic)

- providers: {'det': 'CUDAExecutionProvider', 'pose': 'CUDAExecutionProvider'}
- detector: 29.1 ms/frame; pose: 4.5 ms/person
