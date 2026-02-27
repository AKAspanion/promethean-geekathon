"use client";

import Link from "next/link";
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

      <div className="space-y-4">
        {suppliers.map((supplier) => {
          const riskSummary = supplier.riskSummary;
          const riskLevel = supplier.latestRiskLevel ?? "LOW";
          const riskColor = riskLevelColors[riskLevel] ?? riskLevelColors.LOW;
          const hasScore = supplier.latestRiskScore != null;

          return (
            <Link
              key={supplier.id}
              href={`/suppliers/${supplier.id}`}
              className="block border border-light-gray dark:border-gray-600 rounded-lg p-4 hover:bg-off-white dark:hover:bg-gray-700/50 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <h3 className="heading-3 text-dark-gray dark:text-gray-200 mb-1">
                    {supplier.name}
                  </h3>
                  <div className="flex flex-wrap gap-2 text-xs text-medium-gray dark:text-gray-400">
                    {supplier.city && supplier.country && (
                      <span>
                        {supplier.city}, {supplier.country}
                      </span>
                    )}
                    {!supplier.city && supplier.country && (
                      <span>{supplier.country}</span>
                    )}
                    {supplier.region && <span>{supplier.region}</span>}
                    {supplier.commodities && (
                      <span>{supplier.commodities}</span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-end gap-2 shrink-0">
                  {hasScore && (
                    <div className="flex items-center gap-3">
                      <span
                        className={`px-2 py-1 rounded-lg text-xs font-medium ${riskColor}`}
                      >
                        {riskLevel}
                      </span>
                      <CircularScore score={supplier.latestRiskScore!} size="sm" />
                    </div>
                  )}
                  {riskSummary && riskSummary.count > 0 && (
                    <div className="text-xs text-medium-gray dark:text-gray-400 text-right">
                      <div>{riskSummary.count} risks detected</div>
                      {riskSummary.latest && (
                        <div className="truncate max-w-50">
                          Latest:{" "}
                          <span className="font-medium">
                            {riskSummary.latest.severity.toUpperCase()}
                          </span>{" "}
                          - {riskSummary.latest.title}
                        </div>
                      )}
                    </div>
                  )}
                  {!hasScore && (!riskSummary || riskSummary.count === 0) && (
                    <span className="text-xs text-medium-gray dark:text-gray-400">
                      No analysis yet
                    </span>
                  )}
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
