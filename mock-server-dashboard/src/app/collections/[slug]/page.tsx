"use client";

import { use, useState, useCallback } from "react";
import Link from "next/link";
import { RecordTable } from "@/components/Records/RecordTable";
import { RecordModal } from "@/components/Records/RecordModal";
import {
  useRecordsList,
  useCreateRecord,
  useReplaceRecord,
  useDeleteRecord,
} from "@/lib/queries/records";
import { useCollection as useCollectionQuery } from "@/lib/queries/collections";
import type { RecordItem } from "@/lib/types";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export default function CollectionDetailPage({ params }: PageProps) {
  const { slug: resolvedSlug } = use(params);

  const { data: collectionData, isLoading: collectionLoading } =
    useCollectionQuery(resolvedSlug);
  const collection = collectionData;

  const [queryInput, setQueryInput] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");

  const { data: recordsData, isLoading: recordsLoading } = useRecordsList(
    resolvedSlug,
    { q: appliedQuery || undefined }
  );
  const records = recordsData?.items ?? [];

  const [modalOpen, setModalOpen] = useState(false);
  const [editingRecord, setEditingRecord] = useState<RecordItem | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleApplyQuery = useCallback(() => {
    setAppliedQuery(queryInput.trim());
  }, [queryInput]);

  const handleClearQuery = useCallback(() => {
    setQueryInput("");
    setAppliedQuery("");
  }, []);

  const createMutation = useCreateRecord(resolvedSlug);
  const replaceMutation = useReplaceRecord(
    resolvedSlug,
    editingRecord?.id ?? ""
  );
  const deleteMutation = useDeleteRecord(resolvedSlug);

  const openCreate = useCallback(() => {
    setEditingRecord(null);
    setModalOpen(true);
  }, []);

  const openEdit = useCallback((r: RecordItem) => {
    setEditingRecord(r);
    setModalOpen(true);
  }, []);

  const closeModal = useCallback(() => {
    setModalOpen(false);
    setEditingRecord(null);
  }, []);

  const handleSubmit = useCallback(
    (data: Record<string, unknown>) => {
      if (editingRecord) {
        replaceMutation.mutate(data, { onSuccess: () => closeModal() });
      } else {
        createMutation.mutate(data, { onSuccess: () => closeModal() });
      }
    },
    [editingRecord, createMutation, replaceMutation, closeModal]
  );

  const handleDelete = useCallback(
    (r: RecordItem) => {
      if (!confirm("Delete this record?")) return;
      setDeletingId(r.id);
      deleteMutation.mutate(r.id, {
        onSettled: () => setDeletingId(null),
      });
    },
    [deleteMutation]
  );

  if (collectionLoading || !collection) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-8">
        {collectionLoading ? (
          <p className="text-zinc-500 dark:text-zinc-400">Loading…</p>
        ) : (
          <p className="text-zinc-500 dark:text-zinc-400">
            Collection not found.
          </p>
        )}
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6">
        <Link
          href="/"
          className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          ← Collections
        </Link>
        <h1 className="mt-2 text-2xl font-bold text-zinc-900 dark:text-zinc-100">
          {collection.name}
        </h1>
        {collection.description && (
          <p className="mt-1 text-zinc-600 dark:text-zinc-400">
            {collection.description}
          </p>
        )}
        <p className="mt-1 font-mono text-sm text-zinc-500 dark:text-zinc-500">
          slug: {collection.slug}
        </p>
      </div>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-wrap items-center gap-2">
          <label htmlFor="query-input" className="sr-only">
            Query by key (path:value)
          </label>
          <input
            id="query-input"
            type="text"
            placeholder="e.g. name:detroit, name.city:detroit, cities.0:detroit, tags.*:js, weather.[].result.main:Clouds"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleApplyQuery()}
            className="min-w-[200px] max-w-md rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder-zinc-500 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:placeholder-zinc-400 dark:focus:border-zinc-400 dark:focus:ring-zinc-400"
          />
          <button
            type="button"
            onClick={handleApplyQuery}
            className="rounded-lg border border-zinc-300 bg-zinc-50 px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
          >
            Search
          </button>
          {appliedQuery && (
            <button
              type="button"
              onClick={handleClearQuery}
              className="rounded-lg px-3 py-2 text-sm text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            >
              Clear
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          New record
        </button>
      </div>

      {appliedQuery && (
        <p className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
          Filtering by <code className="rounded bg-zinc-200 px-1 dark:bg-zinc-700">q={appliedQuery}</code>
        </p>
      )}

      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-zinc-800 dark:text-zinc-200">
          Records ({recordsData?.total ?? 0})
        </h2>
      </div>

      {recordsLoading ? (
        <p className="text-zinc-500 dark:text-zinc-400">Loading records…</p>
      ) : (
        <RecordTable
          records={records}
          onEdit={openEdit}
          onDelete={handleDelete}
          isDeletingId={deletingId}
        />
      )}

      {modalOpen && (
        <RecordModal
          key={editingRecord?.id ?? "new"}
          record={editingRecord}
          onClose={closeModal}
          onSubmit={handleSubmit}
          isPending={createMutation.isPending || replaceMutation.isPending}
        />
      )}
    </main>
  );
}
