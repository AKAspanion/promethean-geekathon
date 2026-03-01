"use client";

import { useEffect } from "react";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[AppError]", error);
  }, [error]);

  return (
    <div className="flex items-center justify-center py-20">
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
          Something went wrong
        </h2>
        <p className="text-sm text-medium-gray dark:text-gray-400 mb-6">
          {error.message || "An unexpected error occurred while loading this page."}
        </p>
        <button
          onClick={reset}
          className="inline-flex items-center px-4 py-2 rounded-lg bg-primary-dark text-white text-sm font-medium hover:bg-primary-dark/90 transition-colors"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
