// Types mirroring the FastAPI response models (taiji_ai/src/taiji_ai/api/routers/health.py).
// Hand-written for now; generate from /api/openapi.json once more endpoints exist (follow-up, P8.03).

export interface ApiErrorBody {
  error: { code: string; message: string; details?: { loc: (string | number)[]; msg: string }[] };
}

export interface ModelInfo {
  name: string;
  role: string;
  sha256_prefix: string;
}

export interface ModelStatus {
  ok: boolean;
  verified_at_startup: boolean;
  entries: ModelInfo[];
  error: string | null;
}

export interface DatabaseStatus {
  ok: boolean;
  migrations: number[];
  error: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  models: ModelStatus;
  database: DatabaseStatus;
  web_build: boolean;
}
