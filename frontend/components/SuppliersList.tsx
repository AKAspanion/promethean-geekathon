"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { suppliersApi, Supplier } from "@/lib/api";
import { CircularScore } from "@/components/CircularScore";

const riskLevelColors: Record<string, string> = {
  LOW: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300",
  MEDIUM:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300",
  HIGH: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300",
  CRITICAL: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300",
};

export function SuppliersList() {
  const router = useRouter();
  const { data: suppliers, isLoading } = useQuery<Supplier[]>({
    queryKey: ["suppliers"],
    queryFn: suppliersApi.getAll,
  });

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">
          Suppliers
        </h2>
        <div className="space-y-4">
          {[1, 2].map((item) => (
            <div key={item} className="animate-pulse">
              <div className="h-4 bg-light-gray dark:bg-gray-700 rounded w-1/3 mb-2" />
              <div className="h-3 bg-light-gray dark:bg-gray-700 rounded w-full" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!suppliers || suppliers.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">
          Suppliers
        </h2>
        <p className="body-text text-medium-gray dark:text-gray-400">
          No suppliers available yet.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200">
          Suppliers
        </h2>
        <span className="text-xs text-medium-gray dark:text-gray-400">
          Live updates via agent analysis
        </span>
      </div>

      <div className="-mx-6 overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-700/40 border-y border-light-gray dark:border-gray-700 text-xs text-medium-gray dark:text-gray-400 uppercase tracking-wider">
              <th className="px-6 py-3 font-medium">Supplier</th>
              <th className="px-4 py-3 font-medium">Country</th>
              <th className="px-4 py-3 font-medium">Commodities</th>
              <th className="px-4 py-3 font-medium">Risk Level</th>
              <th className="px-4 py-3 font-medium">Score</th>
              <th className="px-6 py-3 font-medium">Insights</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-light-gray dark:divide-gray-700 [&>tr:last-child]:border-b [&>tr:last-child]:border-light-gray dark:[&>tr:last-child]:border-gray-700">
            {[...suppliers]
              .sort(
                (a, b) =>
                  new Date(b.updatedAt).getTime() -
                  new Date(a.updatedAt).getTime()
              )
              .map((supplier) => {
              const swarm = supplier.swarm;
              const riskLevel = supplier.latestRiskLevel ?? "LOW";
              const riskColor =
                riskLevelColors[riskLevel] ?? riskLevelColors.LOW;
              const hasScore = supplier.latestRiskScore != null;

              const swarmRiskCount = swarm
                ? swarm.agents.reduce(
                    (sum, agent) =>
                      sum +
                      (((agent.metadata as Record<string, unknown>)
                        ?.riskCount as number) ?? 0),
                    0
                  )
                : 0;
              const swarmTopDriver =
                swarm?.topDrivers?.find((d) => d.trim()) ?? null;

              const country = supplier.country ?? "—";

              return (
                <tr
                  key={supplier.id}
                  onClick={() => router.push(`/suppliers/${supplier.id}`)}
                  className="hover:bg-off-white dark:hover:bg-gray-700/50 transition-colors cursor-pointer"
                >
                  <td className="px-6 py-3 font-medium text-dark-gray dark:text-gray-200">
                    {supplier.name}
                  </td>
                  <td className="px-4 py-3 text-medium-gray dark:text-gray-400 whitespace-nowrap">
                    {country}
                  </td>
                  <td className="px-4 py-3 text-medium-gray dark:text-gray-400">
                    {supplier.commodities ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    {hasScore ? (
                      <span
                        className={`px-2 py-1 rounded-lg text-xs font-medium ${riskColor}`}
                      >
                        {riskLevel}
                      </span>
                    ) : (
                      <span className="text-xs text-medium-gray dark:text-gray-400">
                        —
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {hasScore ? (
                      <CircularScore
                        score={supplier.latestRiskScore!}
                        size="sm"
                      />
                    ) : (
                      <span className="text-xs text-medium-gray dark:text-gray-400">
                        —
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-3 text-xs text-medium-gray dark:text-gray-400">
                    {swarmRiskCount > 0 ? (
                      <div>
                        <div>{swarmRiskCount} risks detected</div>
                        {swarmTopDriver && (
                          <div className="truncate max-w-48">
                            Top: <span className="font-medium">{swarmTopDriver}</span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <span>No analysis yet</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
