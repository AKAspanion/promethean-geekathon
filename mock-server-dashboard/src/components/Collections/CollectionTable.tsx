"use client";

import Link from "next/link";
import type { Collection } from "@/lib/types";

interface CollectionTableProps {
  collections: Collection[];
  onEdit: (c: Collection) => void;
  onDelete: (c: Collection) => void;
  isDeletingId: string | null;
}

export function CollectionTable({
  collections,
  onEdit,
  onDelete,
  isDeletingId,
}: CollectionTableProps) {
  if (collections.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-zinc-300 py-12 text-center text-zinc-500 dark:border-zinc-600 dark:text-zinc-400">
        No collections yet. Create one to get started.
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
      <table className="w-full text-left text-sm">
        <thead className="bg-zinc-50 dark:bg-zinc-800">
          <tr>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              Name
            </th>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              Slug
            </th>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              Description
            </th>
            <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-700">
          {collections.map((c) => (
            <tr
              key={c.id}
              className="bg-white hover:bg-zinc-50 dark:bg-zinc-900 dark:hover:bg-zinc-800"
            >
              <td className="px-4 py-3">
                <Link
                  href={`/collections/${c.slug}`}
                  className="font-medium text-zinc-900 hover:underline dark:text-zinc-100"
                >
                  {c.name}
                </Link>
              </td>
              <td className="px-4 py-3 font-mono text-zinc-600 dark:text-zinc-400">
                {c.slug}
              </td>
              <td className="max-w-[200px] truncate px-4 py-3 text-zinc-500 dark:text-zinc-400">
                {c.description ?? "—"}
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => onEdit(c)}
                    className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(c)}
                    disabled={isDeletingId === c.id}
                    className="text-red-600 hover:text-red-700 disabled:opacity-50 dark:text-red-400 dark:hover:text-red-300"
                  >
                    {isDeletingId === c.id ? "Deleting…" : "Delete"}
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
