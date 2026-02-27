"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function BackendStatus() {
  const { data, isPending, isError } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
    refetchInterval: 30_000,
    retry: 1,
  });

  if (isPending) {
    return (
      <span className="text-xs text-zinc-500 dark:text-zinc-400">
        Checking backend…
      </span>
    );
  }

  if (isError || !data) {
    return (
      <span className="text-xs text-amber-600 dark:text-amber-400" title="Set NEXT_PUBLIC_MOCK_SERVER_URL if mock-server runs elsewhere">
        Backend unreachable
      </span>
    );
  }

  return (
    <span className="text-xs text-emerald-600 dark:text-emerald-400" title={data.db}>
      Backend connected
    </span>
  );
}
