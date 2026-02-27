"use client";

import type { RecordItem } from "@/lib/types";

interface RecordTableProps {
  records: RecordItem[];
  onEdit: (r: RecordItem) => void;
  onDelete: (r: RecordItem) => void;
  isDeletingId: string | null;
}

export function RecordTable({
  records,
  onEdit,
  onDelete,
  isDeletingId,
}: RecordTableProps) {
  if (records.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-zinc-300 py-12 text-center text-zinc-500 dark:border-zinc-600 dark:text-zinc-400">
        No records yet. Create one to get started.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
      <table className="w-full text-left text-sm">
        <thead className="bg-zinc-50 dark:bg-zinc-800">
          <tr>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              ID
            </th>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              Data (preview)
            </th>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              Updated
            </th>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-700">
          {records.map((r) => (
            <tr
              key={r.id}
              className="bg-white hover:bg-zinc-50 dark:bg-zinc-900 dark:hover:bg-zinc-800"
            >
              <td className="max-w-[120px] truncate px-4 py-3 font-mono text-zinc-600 dark:text-zinc-400">
                {r.id}
              </td>
              <td className="max-w-[300px] truncate px-4 py-3 font-mono text-zinc-700 dark:text-zinc-300">
                {JSON.stringify(r.data)}
              </td>
              <td className="px-4 py-3 text-zinc-500 dark:text-zinc-400">
                {new Date(r.updatedAt).toLocaleString()}
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => onEdit(r)}
                    className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(r)}
                    disabled={isDeletingId === r.id}
                    className="text-red-600 hover:text-red-700 disabled:opacity-50 dark:text-red-400 dark:hover:text-red-300"
                  >
                    {isDeletingId === r.id ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
