// T-WEB-01: the app renders and the status page shows /api/health data (fetch mocked).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { routes } from "../src/routes";
import type { HealthResponse } from "../src/api/types";

const healthy: HealthResponse = {
  status: "ok",
  version: "0.1.0",
  models: {
    ok: true,
    verified_at_startup: true,
    entries: [
      { name: "yolox_m_humanart", role: "det", sha256_prefix: "3dea65133888" },
      { name: "rtmpose_m_body7_halpe26", role: "pose", sha256_prefix: "26f3a19e6130" },
    ],
    error: null,
  },
  database: { ok: true, migrations: [1], error: null },
  web_build: true,
};

function renderAt(path: string, body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("StatusPage", () => {
  it("shows a healthy system with both models and migrations", async () => {
    renderAt("/", healthy);
    expect(await screen.findByTestId("overall")).toHaveTextContent("Hoạt động bình thường");
    expect(screen.getByText("yolox_m_humanart")).toBeInTheDocument();
    expect(screen.getByText("rtmpose_m_body7_halpe26")).toBeInTheDocument();
    expect(screen.getByText(/Migration đã áp dụng: 1/)).toBeInTheDocument();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("shows the problem when the system is degraded", async () => {
    const degraded: HealthResponse = {
      ...healthy,
      status: "degraded",
      models: { ok: false, verified_at_startup: true, entries: [], error: "sha256 mismatch for pose" },
    };
    renderAt("/", degraded);
    expect(await screen.findByTestId("overall")).toHaveTextContent("Có vấn đề cần xử lý");
    expect(screen.getByText(/sha256 mismatch for pose/)).toBeInTheDocument();
  });

  it("shows the API error code when the request fails", async () => {
    renderAt("/", { error: { code: "internal_error", message: "Internal server error" } }, 500);
    expect(await screen.findByRole("alert")).toHaveTextContent("internal_error");
  });

  it("renders the not-found page for unknown client routes", async () => {
    renderAt("/khong-ton-tai", healthy);
    expect(await screen.findByText("Không tìm thấy trang")).toBeInTheDocument();
  });
});
