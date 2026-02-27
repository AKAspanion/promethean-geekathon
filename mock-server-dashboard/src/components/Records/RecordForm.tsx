"use client";

import { useState, useCallback } from "react";
import type { RecordItem } from "@/lib/types";

interface RecordFormProps {
  record?: RecordItem | null;
  onSubmit: (data: Record<string, unknown>) => void;
  onCancel: () => void;
  isPending?: boolean;
  submitLabel?: string;
}

export function RecordForm({
  record,
  onSubmit,
  onCancel,
  isPending = false,
  submitLabel = "Save",
}: RecordFormProps) {
  const [jsonStr, setJsonStr] = useState(
    () => JSON.stringify(record?.data ?? {}, null, 2)
  );
  const [parseError, setParseError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setParseError(null);
      try {
        const data = JSON.parse(jsonStr) as Record<string, unknown>;
        if (typeof data !== "object" || data === null || Array.isArray(data)) {
          setParseError("Data must be a JSON object");
          return;
        }
        onSubmit(data);
      } catch (err) {
        setParseError(err instanceof Error ? err.message : "Invalid JSON");
      }
    },
    [jsonStr, onSubmit]
  );

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div>
        <label htmlFor="record-json" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Data (JSON object)
        </label>
        <textarea
          id="record-json"
          value={jsonStr}
          onChange={(e) => {
            setJsonStr(e.target.value);
            setParseError(null);
          }}
          rows={12}
          className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 font-mono text-sm text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
        />
        {parseError && (
          <p className="mt-1 text-sm text-red-600 dark:text-red-400">
            {parseError}
          </p>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isPending}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {isPending ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
