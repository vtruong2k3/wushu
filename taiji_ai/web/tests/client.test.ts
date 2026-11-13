// T-WEB-C1: apiGet maps every failure mode to ApiError with a stable code.
import { describe, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "../src/api/client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("apiGet", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, { a: 1 })));
    await expect(apiGet<{ a: number }>("/api/x")).resolves.toEqual({ a: 1 });
  });

  it("maps the backend error format to ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(404, { error: { code: "not_found", message: "Not Found" } })),
    );
    const err = await apiGet("/api/nope").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ code: "not_found", message: "Not Found", status: 404 });
  });

  it("maps a non-JSON error body to http_error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502 })));
    await expect(apiGet("/api/x")).rejects.toMatchObject({ code: "http_error", status: 502 });
  });

  it("maps a network failure to network_error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiGet("/api/x")).rejects.toMatchObject({ code: "network_error", status: null });
  });

  it("refuses paths outside /api/", async () => {
    await expect(apiGet("/other")).rejects.toThrow("/api/");
  });

  // BUG-0005 regression tests
  it("keeps caller headers given as a Headers object and adds Accept", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
    vi.stubGlobal("fetch", fetchMock);
    await apiGet("/api/x", { headers: new Headers({ "X-Trace": "abc" }) });
    const sent = new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers);
    expect(sent.get("X-Trace")).toBe("abc");
    expect(sent.get("Accept")).toBe("application/json");
  });

  it("propagates AbortError unchanged (query cancellation is not a network error)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("The operation was aborted.", "AbortError")));
    const err = await apiGet("/api/x").catch((e: unknown) => e);
    expect(err).not.toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ name: "AbortError" });
  });
});
