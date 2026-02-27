"use client";

import { use, useState, useCallback, useRef } from "react";
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

  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2000);
  }, []);

  const handleCopyUrl = useCallback(() => {
    const base = process.env.NEXT_PUBLIC_MOCK_SERVER_URL ?? "http://localhost:4000";
    const search = new URLSearchParams();
    if (appliedQuery) search.set("q", appliedQuery);
    const qs = search.toString();
    const url = `${base}/mock/${resolvedSlug}${qs ? `?${qs}` : ""}`;
    navigator.clipboard.writeText(url).then(() => showToast("URL copied!"));
  }, [appliedQuery, resolvedSlug, showToast]);

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
          <button
            type="button"
            onClick={handleCopyUrl}
            disabled={!appliedQuery}
            title="Copy API URL"
            className="rounded-lg border border-zinc-300 bg-zinc-50 p-2 text-zinc-700 hover:bg-zinc-100 disabled:opacity-30 disabled:cursor-not-allowed dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-600"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
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
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-fade-in rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white shadow-lg dark:bg-zinc-100 dark:text-zinc-900">
          {toast}
        </div>
      )}
    </main>
  );
}
