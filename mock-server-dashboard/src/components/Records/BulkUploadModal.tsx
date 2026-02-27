"use client";

import { useState, useCallback } from "react";

interface BulkUploadModalProps {
  onClose: () => void;
  onSubmit: (data: Record<string, unknown>[]) => void;
  isPending?: boolean;
}

export function BulkUploadModal({
  onClose,
  onSubmit,
  isPending = false,
}: BulkUploadModalProps) {
  const [jsonStr, setJsonStr] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [recordCount, setRecordCount] = useState<number | null>(null);

  const validate = useCallback((value: string): Record<string, unknown>[] | null => {
    if (!value.trim()) {
      setParseError(null);
      setRecordCount(null);
      return null;
    }
    try {
      const parsed = JSON.parse(value) as unknown;
      if (!Array.isArray(parsed)) {
        setParseError("Input must be a JSON array");
        setRecordCount(null);
        return null;
      }
      if (parsed.length === 0) {
        setParseError("Array must not be empty");
        setRecordCount(null);
        return null;
      }
      for (let i = 0; i < parsed.length; i++) {
        const item = parsed[i];
        if (typeof item !== "object" || item === null || Array.isArray(item)) {
          setParseError(`Item at index ${i} must be a JSON object`);
          setRecordCount(null);
          return null;
        }
      }
      setParseError(null);
      setRecordCount(parsed.length);
      return parsed as Record<string, unknown>[];
    } catch (err) {
      setParseError(err instanceof Error ? err.message : "Invalid JSON");
      setRecordCount(null);
      return null;
    }
  }, []);

  const handleChange = useCallback(
    (value: string) => {
      setJsonStr(value);
      validate(value);
    },
    [validate]
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const data = validate(jsonStr);
      if (!data) return;
      onSubmit(data);
    },
    [jsonStr, validate, onSubmit]
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="bulk-upload-modal-title"
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl dark:bg-zinc-900"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="bulk-upload-modal-title"
          className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100"
        >
          Bulk upload records
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label
              htmlFor="bulk-json"
              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
            >
              Data (JSON array of objects)
            </label>
            <textarea
              id="bulk-json"
              value={jsonStr}
              onChange={(e) => handleChange(e.target.value)}
              rows={14}
              placeholder={'[\n  { "name": "Alice", "age": 30 },\n  { "name": "Bob", "age": 25 }\n]'}
              className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 font-mono text-sm text-zinc-900 shadow-sm focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100"
            />
            {parseError && (
              <p className="mt-1 text-sm text-red-600 dark:text-red-400">
                {parseError}
              </p>
            )}
            {recordCount !== null && !parseError && (
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                {recordCount} record{recordCount !== 1 ? "s" : ""} will be created
              </p>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending || !recordCount}
              className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              {isPending ? "Uploading…" : "Upload"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
