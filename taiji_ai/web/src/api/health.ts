import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";
import type { HealthResponse } from "./types";

export const healthQueryKey = ["health"] as const;

export function useHealth() {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: ({ signal }) => apiGet<HealthResponse>("/api/health", { signal }),
    refetchInterval: 10_000,
  });
}
