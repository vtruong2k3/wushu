# Third-Party Notices — taiji_ai

Inventory of third-party components used by this code base, with their license tier (AGENTS.md §9.1).
Update this file in the same change that adds, removes or upgrades a component.
This is a project inventory, not legal advice; a license review is required before any commercial release.

**Last updated:** 2026-11-14 (task P8.02; first version X.03). License strings taken from installed package metadata (`.venv`).

## 1. Direct runtime dependencies (`pyproject.toml`)

| Package | Version (uv.lock) | License | Tier | Used for |
|---|---|---|---|---|
| rtmlib | 0.0.16 | Apache-2.0 | Permissive | YOLOX + RTMPose ONNX inference wrappers |
| onnxruntime-gpu | 1.32.0 | MIT | Permissive | ONNX inference (CUDA) |
| av (PyAV) | 19.0.2 | BSD-3-Clause; the wheel bundles FFmpeg shared libraries whose build license (LGPL vs GPL) is **not yet verified** | Permissive (PyAV) + bundled libs to verify before distribution | Frame decoding with PTS |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Permissive | Arrays |
| scipy | 1.18.1 | BSD-3-Clause | Permissive | Filtering, signal processing |
| pandas | 3.1.1 | BSD-3-Clause | Permissive | Tables |
| pyarrow | 26.0.1 | Apache-2.0 | Permissive | Parquet artifacts |
| pydantic | 2.14.3 | MIT | Permissive | Schemas / manifests |
| opencv-python-headless | 4.14.0.94 | Apache-2.0 | Permissive | Image ops (rotation, resize; used by rtmlib) |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | Weak copyleft (MPL part) | Progress bars (unmodified) |
| fastapi | 0.162.6 | MIT | Permissive | HTTP API (`/api`), serves the web build |
| uvicorn | 0.54.0 | BSD-3-Clause | Permissive | ASGI server (127.0.0.1 only) |
| plotly | 7.1.0 | MIT | Permissive | Charts, HTML report |
| jinja2 | 3.1.6 | BSD-3-Clause | Permissive | HTML report templates |

Transitive dependencies are pinned in `uv.lock`; audit them (`uv tree`, package metadata) before any distribution.
Notable transitive: starlette 1.10.0 (BSD-3, via fastapi); **opentelemetry-api 1.45.2** (Apache-2.0, required by
fastapi ≥ 0.162) — API package only, no SDK/exporter installed, so nothing is collected or sent.

### Proprietary redistributable (installed via `onnxruntime-gpu[cuda,cudnn]`)

| Package | Version | License | Note |
|---|---|---|---|
| nvidia-cuda-runtime | 13.5.37 | NVIDIA proprietary | Local use OK; check NVIDIA redistribution terms before bundling |
| nvidia-cudnn-cu13 | 9.28.1.4 | NVIDIA proprietary | same |
| nvidia-cufft | 12.5.0.14 | NVIDIA proprietary | same |
| nvidia-curand | 10.4.5.25 | NVIDIA proprietary | same |
| nvidia-cuda-nvrtc | 13.5.37 | NVIDIA proprietary | same |
| nvidia-nvjitlink | 13.5.37 | NVIDIA proprietary | same |

## 2. Development-only tools (not shipped)

| Package | License | Used for |
|---|---|---|
| pytest | MIT | Tests |
| ruff | MIT | Lint / format |
| mypy | MIT | Type checking |
| httpx2 (+ httpcore2, truststore) | BSD-3-Clause (truststore MIT) | HTTP client for FastAPI `TestClient` |
| uv | MIT OR Apache-2.0 | Environment / lock management |

## 2b. Web UI (`taiji_ai/web`, pnpm; lockfile `pnpm-lock.yaml`)

Installed with `minimumReleaseAge` = 7 days (`web/pnpm-workspace.yaml`). Licenses from `pnpm licenses list`.

| Package | Version | License | Scope | Used for |
|---|---|---|---|---|
| react, react-dom | 19.3.1 | MIT | runtime | UI |
| react-router | 8.5.1 | MIT | runtime | Client-side routing |
| @tanstack/react-query | 5.106.1 | MIT | runtime | Data fetching / cache |
| vite | 8.3.6 | MIT | dev | Dev server, build |
| @vitejs/plugin-react | 6.2.1 | MIT | dev | React transform |
| typescript | 6.0.3 | Apache-2.0 | dev | Type checking (held < 6.1 by typescript-eslint peer range) |
| vitest | 5.1.0 | MIT | dev | Unit tests |
| jsdom | 29.1.1 | MIT | dev | Test DOM (30/31 need Node ≥ 24.15) |
| @testing-library/react, /dom, /jest-dom | 16.3.3 / 10.4.2 / 7.0.1 | MIT | dev | Component tests |
| eslint, @eslint/js, typescript-eslint, eslint-plugin-react-hooks, eslint-plugin-react-refresh, globals | 10.14.0 / 10.0.1 / 8.72.1 / 7.1.1 / 0.5.7 / 17.14.0 | MIT | dev | Lint |
| @types/react, @types/react-dom, @types/node | 19.3.0 / 19.3.0 / 24.19.2 | MIT | dev | Types |

Totals (2026-11-14): runtime 11 packages, all MIT. All packages: MIT 187, Apache-2.0 17, ISC 10, BSD-2-Clause 8,
BSD-3-Clause 3, MIT-0 2, BlueOak-1.0.0 2, CC0-1.0 1, CC-BY-4.0 1 (data), **MPL-2.0 2** (`lightningcss` + its
win32 binary — build-time CSS tool, used unmodified; weak copyleft tier).

Known advisory (accepted, dev-only): **GHSA-g3hv-75wg-m249** — `minimatch` < 11.0.1 (moderate, DoS via crafted
glob patterns) pulled by eslint. Not reachable from untrusted input (eslint only expands our own config globs);
forcing minimatch 11 (major) could break eslint. Revisit when eslint updates. `pnpm audit --prod`: no known
vulnerabilities.

## 3. External programs (called as separate processes, not linked)

| Program | Version | License | Note |
|---|---|---|---|
| FFmpeg / ffprobe | 9.0.1 (Gyan "essentials" Windows build) | GPL build (FFmpeg itself LGPL/GPL depending on configuration) | Invoked via CLI only. Do not bundle a GPL build with the product without review |

## 4. Model weights (`models/registry.json`)

| Model | Source | Code license | Weights / training data | Tier |
|---|---|---|---|---|
| YOLOX-m HumanArt (`yolox_m_8xb8-300e_humanart-c2c7a14a.onnx`) | OpenMMLab ONNX SDK export (via rtmlib 0.0.16 URL list) | Apache-2.0 (YOLOX / MMDetection) | Trained on HumanArt; weights terms not stated | Research-only or unclear |
| RTMPose-m body7 HALPE_26 (`rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.onnx`) | OpenMMLab ONNX SDK export (via rtmlib 0.0.16 URL list) | Apache-2.0 (MMPose) | Trained on body7 (includes research-only datasets); weights terms not stated | Research-only or unclear |

Both are acceptable for the internal MVP; a weights/data license audit is required before commercial use.

## 5. Code copied or adapted from third parties

| Source (repo, commit, file) | License | Our file(s) | Decision |
|---|---|---|---|
| — | — | — | *(none so far)* |

Planned candidates (copy only if needed, keep notices): Pose2Sim `sort_people_sports2d` (BSD-3, task P3.05);
QAQA FastDTW windowing / ACDTW step penalty as algorithm references (Apache-2.0, task P6.03).

## 6. Reference-only sources (ideas, no code or data copied)

| Source | License | What we take |
|---|---|---|
| Motion Embedding 24-form (Charl0tte19) | none | Torso-scale normalisation, confidence-masked per-joint similarity, per-second feedback, partial forms as hard negatives |
| Pang et al. 2025 (Long Fist scoring) | none | DTW alignment then keyframe × metric grid; SHAP explanations (with our own correct implementation) |
| Zhang et al. 2022 (Long Fist localization) | none | Label transfer through the DTW warping path; temporal IoU + boundary error reporting |
| OpenWushu | code AGPL-3.0, content CC BY-SA 4.0 | Routine data schema and movement lists as ontology input (content use requires attribution + share-alike) |
| TaiForm deduction criteria | CC BY 4.0 (Zenodo metadata; peer-review sample) | Structure of measurable deduction criteria |
