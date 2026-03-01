"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AnalysisReportError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();

  useEffect(() => {
    console.error("[AnalysisReportError]", error);
  }, [error]);

  return (
    <div className="min-h-screen bg-off-white dark:bg-gray-900 flex items-center justify-center p-6">
      <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-light-gray dark:border-gray-700 p-8 text-center">
        <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
          <svg
            className="w-6 h-6 text-red-600 dark:text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-dark-gray dark:text-gray-200 mb-2">
          Failed to load analysis report
        </h2>
        <p className="text-sm text-medium-gray dark:text-gray-400 mb-6">
          {error.message || "Could not load the analysis report. The data may be temporarily unavailable."}
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={reset}
            className="inline-flex items-center px-4 py-2 rounded-lg bg-primary-dark text-white text-sm font-medium hover:bg-primary-dark/90 transition-colors"
          >
            Try again
          </button>
          <button
            onClick={() => router.back()}
            className="inline-flex items-center px-4 py-2 rounded-lg border border-light-gray dark:border-gray-600 text-sm font-medium text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700 transition-colors"
          >
            Go back
          </button>
        </div>
      </div>
    </div>
  );
}
